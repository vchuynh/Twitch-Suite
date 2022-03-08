import asyncio
import discord
import config
import os
#import datetime
import requests
from enum import Enum
from emoji import demojize

HELP_STR = """
$help:           You're already here.
$check <user>:   Checks if Twitch user is currently live       
$hello:          The bot responds with Hello
$start <user>:   Bot begins logging user's twitch chat
$stop:           Bot stops logging user's twitch chat
$logs:           Returns list of .txt log files
$upload <*.txt>: Uploads .txt file if exists
"""

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
        self.channel = config.CHANNEL
        self.filename = "log.txt"
        self.is_on = True
        
    async def on_pubmsg(self):
        reader, writer = await asyncio.open_connection(self.server, self.port)
        writer.write(f"PASS {self.token}\n".encode("utf-8"))
        writer.write(f"NICK {self.nickname}\n".encode("utf-8"))
        writer.write(f"JOIN {self.channel}\n".encode("utf-8"))
        await writer.drain()
        file = open(self.filename, "w", encoding = "utf-8")
        while self.is_on:
            resp = (await reader.read(2048)).decode("utf-8")
            if resp.startswith("PING"):
                writer.write("Pong\n".encode("utf-8"))
                await writer.drain()
            elif len(resp) > 0:
                clean_str = demojize(resp)
                file.write(clean_str)
                print(clean_str)
        file.close()
        writer.close()
        await writer.wait_closed()

class LogBot(discord.Client):
    def __init__(self, *args, **kwargs):

        self.num_logging = 0

        self.files = []

        #self.twitch_token = config.TWITCH_TOKEN
        
        #channel_dict = {}

        self.is_logging = False
        self.chat_logger = Logger()
        super().__init__(*args, **kwargs)

    def update_filelist(self):
        for file in os.listdir():
            if file.endswith(".txt"):
                self.files.append(file)
                #TODO: intialize dictionaries for future filtering and access
                #file.split("_")
    def check_status(self, user):
        info = None
        status = TwitchStatus.ERROR
        try:
            headers = {"Client-ID": config.CLIENT_ID, "Authorization": "Bearer " + config.TWITCH_TOKEN}
            r = requests.get("https://api.twitch.tv/helix/streams?user_login=" + user, headers = headers, timeout = 15)
            r.raise_for_status()
            info = r.json()
            if info is None or not info["data"]:
                status = TwitchStatus.OFFLINE
            else:
                status = TwitchStatus.ONLINE
        except requests.exceptions.RequestException as err:
            if err.response.status_code == 401:
                status = TwitchStatus.UNAUTHORIZED
            if err.response.status_code == 404:
                status = TwitchStatus.NOT_FOUND
        return info, status
    
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
            elif not config.CLIENT_ID or not config.CLIENT_SECRET:
                await message.channel.send("Client id and secret not registered")
            else:
                info, status = self.check_status(words[1])
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
        elif message.content.startswith("$start"):
            words = message.content.split()
            if self.is_logging:
                await message.channel.send("Already logging")
            elif len(words) > 2:
                await message.channel.send("Invalid usage of start command")
            elif self.is_logging:
                await message.channel.send("Already logging {}'s channel".format(self.chat_logger.channel))
            else:
                self.chat_logger.channel = "#" + words[1]
                self.num_logging += 1
                self.chat_logger.is_on = True
                self.is_logging = True
                #TODO: Implement naming system that accounts for multiple logs in one day
                self.chat_logger.filename = "log{}.txt".format(len(self.files) + 1)
                await message.channel.send("Logger for {} is running".format(self.chat_logger.channel))
                loop = asyncio.get_event_loop()
                loop.create_task(self.chat_logger.on_pubmsg())
        elif message.content.startswith("$stop"):
            if not self.is_logging:
                await message.channel.send("Logger is already stopped")
                return
            self.update_filelist()
            self.chat_logger.is_on = False    
            self.is_logging = False
            await message.channel.send("Logger for {} is stopped".format(self.chat_logger.channel))
        elif message.content.startswith("$logs"):
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
def main():
    client = LogBot()
    client.update_filelist()
    client.run(config.DISCORD_TOKEN)

if __name__ == "__main__":
    main()