import asyncio
from gc import get_stats
import discord
import config
import os
import requests
import aiohttp
from datetime import datetime
from enum import Enum
from emoji import demojize
#from collections import deque
import logging
#import subprocess
import traceback

HELP_STR = """
$help:           You're already here.
$check <user>:   Checks if Twitch user is currently live       
$hello:          The bot responds with Hello
$start <user>:   Bot begins logging user's twitch chat
$stop: <arg>     Bot stops logging a specified user's twitch chat.  Specifying "all" instead of a user, stops all chat loggers
$logs:           Returns list of .txt log files
$upload <*.txt>: Uploads .txt file if exists
$autolog <user>: Starts logging when a user goes live
"""
background_tasks = set()

class TwitchStatus(Enum):
    ONLINE = 0
    OFFLINE = 1
    NOT_FOUND = 2
    UNAUTHORIZED = 3
    ERROR = 4

class Logger():
    def __init__(self):
        self.server = config.SERVER
        self.port = config.PORT
        self.nickname = config.NICKNAME
        self.token = config.TWITCH_TOKEN
        self.channel = "#xqcow"
        self.filename = "chat.txt"
        self.is_on = True
        self.is_printing_chat = False
        #self.last_hundred_messages = []
    
    def __str__(self) -> str:
        return "Server: {}, Port: {}, Channel: {}, Filename: {}, is_on: {}, is_printing_chat: {}".format(self.server, self.port, self.channel, self.filename, self.is_on, self.is_printing_chat)

        
    async def on_pubmsg(self):
        reader, writer = await asyncio.open_connection(self.server, self.port)
        writer.write(f"PASS {self.token}\n".encode("utf-8"))
        writer.write(f"NICK {self.nickname}\n".encode("utf-8"))
        writer.write(f"JOIN {self.channel}\n".encode("utf-8"))
        await writer.drain()
        file = open(self.filename, "w", encoding = "utf-8")
        while self.is_on:
            try:
                resp = (await reader.read(2048)).decode("utf-8")
            except ConnectionResetError:
                file.write("ConnectionResetError probably, see log file")
                file.write("Reopening Chat Connection")
                traceback.print_exc(file = "log_exceptions.txt")
                reader, writer = await asyncio.open_connection(self.server, self.port)
                writer.write(f"PASS {self.token}\n".encode("utf-8"))
                writer.write(f"NICK {self.nickname}\n".encode("utf-8"))
                writer.write(f"JOIN {self.channel}\n".encode("utf-8"))
            now = datetime.now()
            if resp.startswith("PING"):
                writer.write("Pong\n".encode("utf-8"))
                await writer.drain()
            elif len(resp) > 0:
                date_time = now.strftime("[%Y/%m/%d %H:%M:%S UTC]")
                clean_str = date_time + demojize(resp)
                file.write(clean_str)
                if self.is_printing_chat:
                    print(clean_str)
        file.close()
        writer.close()
        await writer.wait_closed()

class LogBot(discord.Client):
    def __init__(self, *args, **kwargs):

        self.num_logging = 0

        self.files = []

        self.watchlist = []

        #self.twitch_token = config.TWITCH_TOKEN
        self.oauth_url = "https://id.twitch.tv/oauth2/token?client_id=" + config.TWITCH_CLIENT_ID + "&client_secret=" \
                         + config.TWITCH_CLIENT_SECRET + "&grant_type=client_credentials"
        self.access_token = None
        #channel_dict = {}

        self.is_logging = False
        self.is_auto_logging = False

        self.chat_logger = Logger()

        self.logger_dict = {}
        self.channel_printing_logger = None
        self.quality = "best"
        super().__init__(*args, **kwargs)
        
    def initialize(self):
        self.set_access_token()
        self.update_filelist()

    #might be an issue, idk, if it is disruptive
    #do it once on startup, append the logs inside autolog() after finished
    def update_filelist(self):
        for file in os.listdir():
            if file.endswith(".txt") and file not in self.files:
                self.files.append(file)
            elif file == "watchlist.txt":
                with open("watchlist.txt") as file_obj:
                    for line in file_obj:
                        self.watchlist.append(line)

    def set_access_token(self):
        resp = requests.post(self.oauth_url, timeout=15)
        resp.raise_for_status()
        token = resp.json()
        self.access_token = token["access_token"]

    async def set_access_token_async(self):
        async with aiohttp.ClientSession() as session:
            async with session.post(self.oauth_url) as resp:
                self.access_token = (resp.json())["access_token"]

    async def get_user(self, user):
        user_data = None
        try:
            headers = {"Client-ID": config.TWITCH_CLIENT_ID, "Authorization": "Bearer " + self.access_token}
            async with aiohttp.ClientSession(headers = headers) as session:
                async with session.get("https://api.twitch.tv/helix/users?login=" + user, raise_for_status = True) as resp:
                    print("{}".format(resp.status))
                    user_data = await resp.json()
                    print(user_data)
        except aiohttp.ClientResponseError as err:
            print("{}".format(err.status))
            print("GET_USER IS BROKE YO")
        return user_data

    async def get_status(self, user):
        status = TwitchStatus.ERROR
        stream_data = None
        try:
            headers = {"Client-ID": config.TWITCH_CLIENT_ID, "Authorization": "Bearer " + self.access_token}
            async with aiohttp.ClientSession(headers = headers) as session:
                async with session.get("https://api.twitch.tv/helix/streams?user_login=" + user, raise_for_status = True) as resp:
                    stream_data = await resp.json()
            if stream_data is None or not stream_data["data"]:
                status = TwitchStatus.OFFLINE
                print("{} is offline".format(user)) #test
            else:
                status = TwitchStatus.ONLINE
                print("{} is online".format(user)) #test
        except aiohttp.ClientResponseError as err:
            if err.status == 401:
                status = TwitchStatus.UNAUTHORIZED
                await self.set_access_token_async()
                print("unauthorized for {}".format(user)) #test
            # doesn't work, but keep it here for now i guess
            elif err.status == 404:
                status = TwitchStatus.NOT_FOUND
                print("{} not found".format(user)) #test
        except aiohttp.ClientConnectorError as err:
            print("Connection Error", str(err))
        return status, stream_data

    #REQUIRES type in ["id", "user_id", "game_id"]
    #INPUT id(video), user_id, game_id
    #EFFECTS Returns Get Videos Response JSON
    async def get_videos(self, id, type):
        video_data = None
        try:
            headers = {"Client-ID": config.TWITCH_CLIENT_ID, "Authorization": "Bearer " + self.access_token}
            async with aiohttp.ClientSession(headers = headers) as session:
                async with session.get("https://api.twitch.tv/helix/videos?" + type + "=" + id, raise_for_status = True) as resp:
                    video_data = await resp.json()
            if video_data is None or not video_data["data"]:
                status = TwitchStatus.OFFLINE
                print("{} is invalid or wrong type".format(id)) #test
            else:
                status = TwitchStatus.ONLINE
                print("{}".format(video_data)) #test
        except aiohttp.ClientResponseError as err:
            if err.status == 401:
                status = TwitchStatus.UNAUTHORIZED
                await self.set_access_token_async()
            # doesn't work, but keep it here for now i guess
            elif err.status == 404:
                status = TwitchStatus.NOT_FOUND
        except aiohttp.ClientConnectorError as err:
            print("Connection Error", str(err))
        return video_data

    async def get_box_art_url(self, game_id, game_name):
        stream_data = None
        box_art_url = None
        try:
            headers = {"Client-ID": config.TWITCH_CLIENT_ID, "Authorization": "Bearer " + self.access_token}
            async with aiohttp.ClientSession(headers = headers) as session:
                async with session.get("https://api.twitch.tv/helix/games?id=" + game_id + "&name=" + game_name) as r:
                    r.raise_for_status()
                    stream_data = await r.json()
                    print(stream_data)
                    box_art_url = stream_data["data"][0]["box_art_url"]
                    print(box_art_url)
        except aiohttp.ClientResponseError:
            print("Game box art not found")
        return box_art_url
    
    async def autolog(self, message, user, is_recording):
        if not await self.get_user(user):
            await message.channel.send("{} not found. Autolog execution prevented".format(user))
            return
        status = TwitchStatus.OFFLINE
        #self.is_logging = True
        self.is_auto_logging = True

        #maybe a future bug cuz append a reference idk i hate dynamic typing
        self.watchlist.append(user)

        current = Logger()
        current.channel = "#" + user
        current.is_on = False
        self.num_logging += 1


        self.logger_dict[user] = current
        
        #shouldnt be a slowdown since max 10 bots
        while user in self.watchlist:
            status, stream_data = await self.get_status(user)
            if status == TwitchStatus.ONLINE and not current.is_on:
                print(stream_data)
                current.is_on = True
                file_name = user + " " + datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")
                current.filename = file_name + ".txt"
                await message.channel.send("Auto Logger for {} is running".format(user))
                #TODO: CASE WHERE SOMEONE STREAMS NO CATEGORY
                try: 
                    box_art_url = await self.get_box_art_url(stream_data["data"][0]["game_id"], stream_data["data"][0]["game_name"])
                    embed = discord.Embed(url = "https://twitch.tv/" + user, title = stream_data["data"][0]["title"])
                    embed.set_thumbnail(url = box_art_url.format(width = 600, height = 800))
                    embed.add_field(name = "Title", value = stream_data["data"][0]["title"], inline = False)
                    if stream_data["data"][0]["game_name"]:
                        embed.add_field(name = "Game", value = stream_data["data"][0]["game_name"], inline = False) 
                    embed.add_field(name = "Status", value = "Live with {} viewers".format(stream_data["data"][0]["viewer_count"]), inline = True)
                    embed.set_image(url = stream_data["data"][0]["thumbnail_url"].format(width = 1280, height = 720))
                    await message.channel.send(embed = embed)
                except:
                    print("get_box_art_url() failed probably")
                current_task = asyncio.create_task(current.on_pubmsg())
                background_tasks.add(current_task)
                current_task.add_done_callback(background_tasks.discard)
                await asyncio.sleep(15)
            elif status == TwitchStatus.OFFLINE and current.is_on:
                #this stops the chat logger
                current.is_on = False
                await asyncio.sleep(5)
                embed = discord.Embed(title = "{} is offline and {} is available for download".format(user, current.filename))
                await message.channel.send(embed = embed)
            #5 minute grace period for stream crash/restarts and lower api calls
            elif current.is_on:
                await asyncio.sleep(300)
            else:
                await asyncio.sleep(15)
        
        #if this is reached, stop command invoked on this logger/channel
        if current.is_on:
            current.is_on = False
            await asyncio.sleep(5)
            embed = discord.Embed(title = "{} is offline and {} is available for download".format(user, current.filename))
            self.files.append(current.filename)
            await message.channel.send(embed = embed)

        try:
            del self.logger_dict[user]
            self.num_logging -= 1
        except KeyError:
            await message.channel.send("this shouldn't be happening")
        
        return
    
    async def on_ready(self):
        print('We have logged in as {0.user}'.format(self))

    async def on_message(self, message):
        if message.author == self.user:
            return
        elif message.content.startswith("$help"):
            await message.channel.send(HELP_STR)
        elif message.content.startswith("$hello"):
            await message.channel.send("Hello!")
        elif message.content.startswith("$check"):
            words = message.content.split()
            if len(words) > 2:
                await message.channel.send("Invalid usage of check command")
            elif not config.TWITCH_CLIENT_ID or not config.TWITCH_CLIENT_SECRET:
                await message.channel.send("Client id and secret not registered")
            else:
                #makesure to cleanup and demojize words[1]
                status, stream_data = self.get_status(words[1])
                if status == 0:
                    await message.channel.send("{} is live".format(words[1]))
                elif status == 1:
                    await message.channel.send("{} is offline".format(words[1]))
                elif status == 2:
                    await message.channel.send("{} was not found".format(words[1]))
                elif status == 3:
                    await message.channel.send("Unauthorized")
                elif status == 4:
                    await message.channel.send("Error")
        #probably should remove this below
        elif message.content.startswith("$start"):
            words = message.content.split()
            if self.is_logging:
                await message.channel.send("Already logging {}'s channel".format(self.chat_logger.channel))
            elif len(words) > 2:
                await message.channel.send("Invalid usage of start command")
            else:
                self.chat_logger.channel = "#" + words[1]
                self.num_logging += 1
                self.chat_logger.is_on = True
                self.is_logging = True
                #TODO: Implement naming system that accounts for multiple logs in one day
                self.chat_logger.filename = "log{}.txt".format(len(self.files) + 1)
                await message.channel.send("Logger for {} is running".format(self.chat_logger.channel))
                
                current_task = asyncio.create_task(self.chat_logger.on_pubmsg())
                background_tasks.add(current_task)
                current_task.add_done_callback(background_tasks.discard)
        elif message.content.startswith("$stop"):
            words = message.content.split()
            #specifying a logger means its an autologger
            if len(words) == 2:
                if words[1].lower() == "all":
                    self.watchlist.clear()
                    #self.update_filelist()
                    self.chat_logger.is_on = False    
                    self.is_logging = False
                    self.is_auto_logging = False
                    #self.can_continue = False
                    await message.channel.send("Any active loggers are stopping")
                else:
                    try:
                        self.watchlist.remove(words[1])
                        await message.channel.send("Autologger for {} stopped".format(words[1]))
                        self.update_filelist()
                    except ValueError:
                        await message.channel.send("User was not being logged")
            #for single use autologger
            elif not self.is_logging:
                await message.channel.send("Logger is already stopped")
                return
            else:
                self.update_filelist()
                self.chat_logger.is_on = False    
                self.is_logging = False
                self.is_auto_logging = False
                await message.channel.send("Logger for {} is stopped".format(self.chat_logger.channel))
        elif message.content.startswith("$logs"):
            self.update_filelist()
            await message.channel.send(self.files)
        elif message.content.startswith("$upload"):
            words = message.content.split()
            if len(words) > 2:
                await message.channel.send("Invalid usage of upload command")
            elif words[1] not in os.listdir():
                await message.channel.send("Log does not exist")
            elif not words[1].endswith(".txt"):
                await message.channel.send("Only .txt files are allowed")
            else:
                await message.channel.send("Uploading Log {}".format(words[1]))
                await message.channel.send(file = discord.File(words[1]))
        elif message.content.startswith("$add"):
            words = message.content.split()
            if len(words) != 2:
                await message.channel.send("Invalid usage of upload command")
            elif words[1] in self.watchlist:
                await message.channel.send("Channel already in watchlist")
            else:
                self.watchlist.append(words[1])
                await message.channel.send("{} added to watchlist".format(words[1]))
        #elif message.content.startswith("$remove"):
        #    words = message.content.split()
        #    if len(words) != 2:
        #        await message.channel.send("Invalid usage of remove command")
        #    elif words[1] not in self.watchlist:
        #        await message.channel.send("Channel not in watchlist")
        #    else:
        #        self.watchlist.remove(words[1])
        #        await message.channel.send("{} removed from watchlist".format(words[1]))
        elif message.content.startswith("$autolog"):
            words = message.content.split()
            if words[1] in self.watchlist:
                await message.channel.send("Already logging {}'s channel".format(words[1]))
            elif len(words) > 2:
                await message.channel.send("Invalid usage of start command")
            elif len(self.logger_dict) >= config.NUM_MAX_LOGGERS:
                await message.channel.send("All {} loggers are being used".format(config.NUM_MAX_LOGGERS))
            else:
                #we should clean words[1] up with demojize and isalnum
                autolog_task = asyncio.create_task(self.autolog(message, words[1], False))
                background_tasks.add(autolog_task)
                autolog_task.add_done_callback(background_tasks.discard)
        elif message.content.startswith("$focus"):
            words = message.content.split()
            await message.channel.send("This is only for users with access to this " \
                + "bot's console and would like to change which channel messages are" \
                + " being displayed on console.")
            # Case:  No logger is actively printing chat to console
            if self.channel_printing_logger == None and len(words) >= 2:
                try:
                    #index = None
                    #for i, logger in enumerate(self.logger_list):
                    #    if words[1] == logger.channel[1:]:
                    #        index = i
                    self.logger_dict[words[1]].is_printing_chat = True
                    #self.index_printing_logger = index
                    self.channel_printing_logger = words[1]
                except KeyError:
                    await message.channel.send("Channel not being logged")

            # Case:  A logger is or was printing chat to console
            else:
                # If logger is still active, stop printing chat to console
                try:
                    #its either failing here or at another function call
                    self.logger_dict[self.channel_printing_logger].is_printing_chat = False
                    await message.channel.send("{} not in focus".format(self.channel_printing_logger))
                # Logger was removed sometime after printing
                except KeyError:
                    await message.channel.send("{} was already stopped".format(words[1]))
                if len(words) >= 2:
                    # Finds channel in current loggers and starts printing
                    try:
                        #this operation actually takes like a second to do
                        #possibly not good
                        #index = None
                        #for i, logger in enumerate(self.logger_list):
                        #    if words[1] == logger.channel[1:]:
                        #        index = i
                        self.logger_dict[words[1]].is_printing_chat = True
                        self.channel_printing_logger = words[1]
                        await message.channel.send("{} is in focus".format(words[1]))
                    #  Case:  Channel was not being logged
                    except KeyError:
                        await message.channel.send("Channel not being logged")

        elif message.content.startswith("$exists"):
            words = message.content.split()
            await self.get_user(words[1])
        elif message.content.startswith("$watchlist"):
            await message.channel.send("{}".format(self.watchlist))
        elif message.content.startswith("$update"):
            pass
            #words = message.content.split()
        elif message.content.startswith("$debug"):
            words = message.content.split()
            if len(words) == 2:
                try:
                    print(self.logger_dict[words[1]])
                except KeyError:
                    print("Channel not being logged")
            elif len(words) == 3 and words[2] == "on":
                try:
                    self.logger_dict[words[1]].is_printing_chat = True
                    print("{} is now printing".format(words[1]))
                except KeyError:
                    print("Channel not being logged")

def main():

    client = LogBot()
    client.initialize()
    logger = logging.getLogger('discord')
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(filename='discordlog.log', encoding='utf-8', mode='w')
    handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    logger.addHandler(handler)
    logging.basicConfig(filename = "logfile.txt", encoding='utf-8', level=logging.DEBUG)
    client.run(config.DISCORD_TOKEN)

if __name__ == "__main__":
    main()