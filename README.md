# Twitch-Suite
Discord bot that has integrated functionality with Twitch.  Currently, the main feature the bot has is the ability to log a Twitch chat and export it to a discord channel.  More features are planned to incorporate greater functionalities from the Twitch API.  
# Requirements
Python 3.x  
discord  
requests  
emoji  
# Setup
Edit these variables in the config.py file.  Do not remove quotes when inputting information  
NICKNAME = "your twitch username"  
DISCORD_TOKEN = "bot token"  
TWITCH_TOKEN = "oauth token"  
CHANNEL = "channel that you want to log"  
# How To Use
Run logbot.py with python and you should be all set.   
# Commands
$help:           You're already here.  
$check <user>:   Checks if Twitch user is currently live         
$hello:          The bot responds with Hello  
$start <user>:   Bot begins logging user's twitch chat  
$stop:           Bot stops logging user's twitch chat  
$logs:           Returns list of .txt log files  
$upload <*.txt>: Uploads .txt file if exists  
