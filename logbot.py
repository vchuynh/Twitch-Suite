import asyncio
from gc import get_stats
import sqlite3
import discord
import config
import os
import requests
import aiohttp
import datetime
from enum import Enum
from emoji import demojize
#from collections import deque
import logging
import aiosqlite


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
        self.session = aiohttp.ClientSession()
        self.websocket = None
        self.server = config.WS_IRC_SERVER
        self.port = config.WSS_IRC_SERVER_PORT
        self.nickname = config.NICKNAME
        self.token = config.TWITCH_TOKEN
        self.channel = "xqcow"
        self.filename = "chat.txt"
        self.is_on = True
        self.is_printing_chat = False
        #self.vod_id = ""
    
    def __str__(self) -> str:
        return "Server: {}, Port: {}, Channel: {}, Filename: {}, is_on: {}, is_printing_chat: {}".format(self.server, self.port, self.channel, self.filename, self.is_on, self.is_printing_chat)

    #Connects to Twitch Chat IRC, reads messages, writes to a txt file
    async def listen(self, stream_id):
        discord_logger.debug("THIS WORKS AND SHOULD BE LOGGING")
        print("THIS WORKS AND SHOULD BE LOGGING")
        self.websocket = await self.session.ws_connect(f"{self.server}:{self.port}")
        await self.websocket.send_str(f"PASS {self.token}\n")
        await self.websocket.send_str(f"NICK {self.nickname}\n")
        await self.websocket.send_str(f"JOIN #{self.channel}\n")
        cursor = await conn.cursor()
        file = open(self.filename, "w", encoding = "utf-8")
        while self.is_on:
            discord_logger.debug(f"Custom: Entering {self.channel}'s listen Loop")
            try:
                resp = await self.websocket.receive_str()
                now = datetime.datetime.now(datetime.timezone.utc)
                date_time = now.strftime("%Y-%m-%d %H:%M:%S")
                messages_list = filter(None, resp.split("\n"))
                for message in messages_list:
                    if "PRIVMSG" in message:
                        chatter = (message.split('!')[0])[1:]
                        msg = message.split(f"#{self.channel}", 1)[1][2:]
                        await cursor.execute("INSERT INTO messages \
                                            (stream_id, chatter, channel, \
                                             message, datetime) VALUES(?, ?, ?, ?, ?);", \
                                            (stream_id, chatter, self.channel, msg, date_time))
                        await conn.commit()

                    clean_str = f"[{date_time} UTC]{message}"
                    file.write(clean_str)
                    discord_logger.debug("Custom: After file write")
                    if self.is_printing_chat:
                        print(clean_str)  
            except Exception as e:
                #writer.write("CAP REQ :twitch.tv/membership twitch.tv/tags twitch.tv/commands\n".encode("utf-8"))
                discord_logger.debug(f"Exception type = {str(type(e))} ::: {str(e)}")
                await self.websocket.close()
                await cursor.close()
                file.close()
                return

        await self.websocket.close()
        await cursor.close()
        file.close()
        discord_logger.debug(f"CUSTOM: {self.channel}'s listen() task finished")

    async def record_stream(self, user, quality, file_name):
        proc = await asyncio.create_subprocess_exec(
            ["streamlink", 
            "--twitch-disable-ads", 
            "twitch.tv/" + user, 
            quality, "-o", 
            file_name + ".mp4"]
        )
        await proc.wait()

class LogBot(discord.Client):
    def __init__(self, *args, **kwargs):

        self.num_logging = 0

        self.files = []

        self.watchlist = []

        self.oauth_url = "https://id.twitch.tv/oauth2/token?client_id=" + config.TWITCH_CLIENT_ID + "&client_secret=" \
                         + config.TWITCH_CLIENT_SECRET + "&grant_type=client_credentials"
        self.access_token = None

        self.is_logging = False
        self.is_auto_logging = False
        
        self. logger_dict= {}
        self.channel_printing_logger = None
        self.quality = "best"
        super().__init__(*args, **kwargs)
        
    def initialize(self):
        self.set_access_token()
        self.update_filelist()

    def update_filelist(self):
        self.files = [file for file in os.listdir() if file.endswith(".txt")]

    def set_access_token(self):
        resp = requests.post(self.oauth_url, timeout=15)
        resp.raise_for_status()
        token = resp.json()
        self.access_token = token["access_token"]

    async def set_access_token_async(self):
        async with aiohttp.ClientSession() as session:
            async with session.post(self.oauth_url) as resp:
                self.access_token = (await resp.json())["access_token"]

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
        return user_data["data"]

    #Returns get_streams json from API
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
                async with session.get(f"https://api.twitch.tv/helix/videos?{type}={id}&first=1&type=archive", raise_for_status = True) as resp:
                    video_data = await resp.json()
            if video_data is None or not video_data["data"]:
                print("I'm not sure yet get_videos") #test
            else:
                print(f"{video_data}") #test
        except aiohttp.ClientResponseError as err:
            if err.status == 401:
                await self.set_access_token_async()
            # doesn't work, but keep it here for now i guess
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
        #feels wrong to hold on to this data afterwards
        user_data = await self.get_user(user)
        if not user_data:
            await message.channel.send("{} not found. Autolog execution prevented".format(user))
            return
        await conn.execute("INSERT OR IGNORE INTO users(twitch_id, login, \
                            display_name, broadcaster_type, description, \
                            view_count, created_at) VALUES(?, ?, ?, ?, ?, ?, ?);", \
                            [user_data[0]["id"], user_data[0]["login"], \
                            user_data[0]["display_name"], user_data[0]["broadcaster_type"], \
                            user_data[0]["description"], user_data[0]["view_count"], \
                            user_data[0]["created_at"]])
        status = TwitchStatus.OFFLINE
        self.is_auto_logging = True

        self.watchlist.append(user)

        current = Logger()
        current.channel = user
        current.is_on = False
        self.num_logging += 1

        self.logger_dict[user] = current

        discord_logger.debug("CUSTOM: Entering Autolog Loop")
        print("Entering Autolog Loop")
        while user in self.watchlist:
            status, stream_data = await self.get_status(user)
            if status == TwitchStatus.ONLINE and not current.is_on:
                print(stream_data)
                video_data = await self.get_videos(stream_data["data"][0]["user_id"], "user_id")
                await conn.execute("INSERT OR IGNORE INTO livestreams(twitch_id, \
                              user_twitch_id, title, started_at) VALUES(?, ?, ?, ?);", \
                              [stream_data["data"][0]["id"], \
                               stream_data["data"][0]["user_id"], \
                               stream_data["data"][0]["title"], \
                               stream_data["data"][0]["started_at"]])
                await conn.commit()
                await conn.execute("INSERT OR IGNORE INTO videos(twitch_id, \
                              stream_id, user_id, created_at, published_at, title) VALUES(?, ?, ?, ?, ?, ?);", \
                              [video_data["data"][0]["id"], \
                               video_data["data"][0]["stream_id"], \
                               video_data["data"][0]["user_id"], \
                               video_data["data"][0]["created_at"], \
                               video_data["data"][0]["published_at"], \
                               video_data["data"][0]["title"]])
                await conn.commit()
                current.is_on = True
                file_name = user + " " + datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")
                current.filename = file_name + ".txt"
                await message.channel.send("Auto Logger for {} is running".format(user))
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
                    #TODO: CASE WHERE SOMEONE STREAMS NO CATEGORY
                    print("get_box_art_url() failed probably")
                discord_logger.debug("CUSTOM: CREATING listen TASK FOR {}".format(user))
                print("CREATING listen TASK FOR {}".format(user))
                current_task = asyncio.create_task(current.listen(stream_data["data"][0]["id"]))
                background_tasks.add(current_task)
                current_task.add_done_callback(background_tasks.discard)
                #if is_recording:
                #    loop = asyncio.get_event_loop()
                #    record_task = loop.create_task(current.record_stream(user, self.quality, file_name))
                await asyncio.sleep(15)
                discord_logger.debug("CUSTOM: PRINTING BACKGROUND TASKS: ")
                print("PRINTING BACKGROUND TASKS: ")
                discord_logger.debug(background_tasks)
                print(background_tasks)
            elif status == TwitchStatus.OFFLINE and current.is_on:
                #this stops the chat logger
                current.is_on = False
                self.update_filelist()
                await asyncio.sleep(5)
                embed = discord.Embed(title = "{} is offline and {} is available for download".format(user, current.filename))
                await message.channel.send(embed = embed)
            #5 minute grace period for stream crash/restarts and lower api calls
            elif current.is_on:
                discord_logger.debug("CUSTOM: {}'s autolog loop in current.is_on".format(user))
                await asyncio.sleep(300)
            else:
                discord_logger.debug("CUSTOM: {}'s autolog loop in else".format(user))
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
        print("{} autolog task has ended".format(user))
        discord_logger.debug("CUSTOM: {} autolog task has ended".format(user))
        return
    
    async def on_ready(self):
        global conn
        conn = await aiosqlite.connect("suite.db")
        await conn.execute('pragma foreign_keys=1')
        print('We have logged in as {0.user}'.format(self))

    async def cmd_check(self, message):
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

    async def cmd_stop(self, message):
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
                    self.watchlist.remove(words[1].lower())
                    await message.channel.send("Autologger for {} stopped".format(words[1]))
                    #self.update_filelist()
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
            
    async def cmd_upload(self, message):
        words = message.content.split()
        if len(words) > 2:
            await message.channel.send("Invalid usage of upload command")
        elif words[1] not in self.files:
            await message.channel.send("Log does not exist")
        elif not words[1].endswith(".txt"):
            await message.channel.send("Only .txt files are allowed")
        else:
            await message.channel.send("Uploading Log {}".format(words[1]))
            await message.channel.send(file = discord.File(words[1]))

    async def cmd_autolog(self, message):
        words = message.content.split()
        if words[1] in self.watchlist:
            await message.channel.send("Already logging {}'s channel".format(words[1]))
        elif len(words) > 2:
            await message.channel.send("Invalid usage of start command")
        elif len(self.logger_dict) >= config.NUM_MAX_LOGGERS:
            await message.channel.send("All {} loggers are being used".format(config.NUM_MAX_LOGGERS))
        else:
            print("CREATING AUTOLOG TASK")
            discord_logger.debug("CUSTOM: CREATING AUTOLOG TASK")
            autolog_task = asyncio.create_task(self.autolog(message, words[1], False))
            background_tasks.add(autolog_task)
            autolog_task.add_done_callback(background_tasks.discard)
            await autolog_task

    async def cmd_focus(self, message):
        words = message.content.split()
        await message.channel.send("This is only for users with access to this " \
            + "bot's console and would like to change which channel messages are" \
            + " being displayed on console.")
        # Case:  No logger is actively printing chat to console
        if self.channel_printing_logger == None and len(words) >= 2:
            try:
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
                    self.logger_dict[words[1]].is_printing_chat = True
                    self.channel_printing_logger = words[1]
                    await message.channel.send("{} is in focus".format(words[1]))
                #  Case:  Channel was not being logged
                except KeyError:
                    await message.channel.send("Channel not being logged")

    async def on_message(self, message):
        if message.author == self.user:
            return
        elif message.content.startswith("$help"):
            await message.channel.send(HELP_STR)
        elif message.content.startswith("$hello"):
            await message.channel.send("Hello!")
        elif message.content.startswith("$check"):
            await self.cmd_check(message)
        elif message.content.startswith("$start"):
            await message.channels.end("Currently deactivated until further code work")
        elif message.content.startswith("$stop"):
            await self.cmd_stop(message)
        elif message.content.startswith("$logs"):
            self.update_filelist()
            await message.channel.send(self.files)
        elif message.content.startswith("$upload"):
            await self.cmd_upload(message)
        #elif message.content.startswith("$add"):
        #    words = message.content.split()
        #    if len(words) != 2:
        #        await message.channel.send("Invalid usage of upload command")
        #    elif words[1] in self.watchlist:
        #        await message.channel.send("Channel already in watchlist")
        #    else:
        #        self.watchlist.append(words[1])
        #        await message.channel.send("{} added to watchlist".format(words[1]))
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
            await self.cmd_autolog(message)
        elif message.content.startswith("$focus"):
            await self.cmd_focus(message)
        elif message.content.startswith("$exists"):
            words = message.content.split()
            user_data = await self.get_user(words[1])
            await message.channel.send("{} returned {}".format(words[1], bool(user_data["data"])))
        elif message.content.startswith("$watchlist"):
            await message.channel.send(f"{self.watchlist}")
        elif message.content.startswith("$update"):
            pass
            #words = message.content.split()
        elif message.content.startswith("$debug"):
            words = message.content.split()
            if len(words) == 2:
                try:
                    print(self.logger_dict[words[1]])
                    print(self.watchlist)
                except KeyError:
                    print("Channel not being logged")
            elif len(words) == 1:
                discord_logger.debug("CUSTOM: PRINTING BACKGROUND TESTS ON $DEBUG COMMAND")
                print("PRINTING BACKGROUND TESTS ON $DEBUG COMMAND")
                discord_logger.debug(background_tasks)
                print(background_tasks)
            elif len(words) == 3 and words[2] == "on":
                try:
                    self.logger_dict[words[1]].is_printing_chat = True
                    print("{} is now printing".format(words[1]))
                except KeyError:
                    print("Channel not being logged")
            #case: debug background tasks -> print(background_tasks)
        #TODO SAFELY query the database
        elif message.content.startswith("$query"):
            pass
        elif message.content.startswith("$video"):
            words = message.content.split()
            if len(words) == 2:
                status, stream_data = await self.get_status("MOONMOON")
                video_data = await self.get_videos(stream_data["data"][0]["user_id"], "user_id")
                #print(video_data)

def get_new_log_name():
    log_files = [file for file in os.listdir() if file.startswith("discord")]
    str = "discord{}.log".format(len(log_files))
    return str

def setup_database():
    conn = sqlite3.connect("suite.db")
    cursor = conn.cursor()
    sql_file = open("createTables.sql")
    sql_file_str = sql_file.read()
    cursor.executescript(sql_file_str)
    conn.commit()

def main():
    client = LogBot()
    client.initialize()
    global discord_logger
    discord_logger = logging.getLogger('discord')
    discord_logger.setLevel(logging.DEBUG)
    str = get_new_log_name()
    handler = logging.FileHandler(filename=str, encoding='utf-8', mode='w')
    del str
    handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    discord_logger.addHandler(handler)
    setup_database()
    print("Opened database successfully!")
    client.run(config.DISCORD_TOKEN)

if __name__ == "__main__":
    main()