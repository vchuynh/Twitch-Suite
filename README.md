# Twitch-Suite
Discord bot that has integrated functionality with Twitch.  This provides the ability to log livestream messages and relevant information into an SQL database among other features.  
# Requirements
- Python 3.x  
- asyncio
- discord  
- requests 
- aiohttp 
- emoji  
- sqlite3
- aiosqlite
# Setup
Edit these variables in the config.py file.  Do not remove quotes when inputting information   
NICKNAME = "your twitch username"  
DISCORD_TOKEN = "bot token"  
TWITCH_TOKEN = "oauth token"  
TWITCH_CLIENT_ID = "application client id"
TWITCH_CLIENT_SECRET = "application secret"
# How To Use
Run logbot.py with python and you should be all set.   
# Commands
$help:           You're already here.          
$hello:          The bot responds with Hello  
$autolog "user"  Automatically logs chat each time user goes live and offline. (Per VOD logs)  
$start "user"    Bot begins logging user's twitch chat. (WIP command)  
$stop: "arg"     Bot stops logging a specified user's twitch chat.  Specifying "all" instead of a user, stops all chat loggers  
$logs:           Returns list of .txt log files    
$upload "{}.txt"  Uploads .txt file to chat if exists     
$focus "user"    For dev use only, prints actively logged user's chat to console.  

# Example
- "$autolog xqcow" will automatically check every 15 seconds if xqcow is online.  When xqcow is detected live, the bot will automatically start logging xqcow's chat to a file.  The bot will notify in Discord when a user is live.  When xqcow goes offline, the file is completed and the bot goes back to checking if xqcow goes live again.  Once the log file is finalized, the bot will notify that xqcow has gone offline and will include the filename of the log.
- "$stop xqcow" will signal to the bot to stop logging xqcow's chat.  This may take up to 3 minutes.  If the bot was actively logging chat, any further messages will not be saved and the current log's filename will be notified in Discord.  

# Features
- Automatically log Twitch chats of up to 10 channels
- Discord notfication when a channel goes live
- User, stream, and message data saved in SQLITE database
- Ability to upload completed logs to a discord channel
- Ability to read chat from python console

# TODO
- Insert Twitch messages into a searchable SQL database that can export filterable datasets.  
- Capture non-user related notifications/messages in Twitch Chats e.g, bit donations  
- Implement livestream recording
