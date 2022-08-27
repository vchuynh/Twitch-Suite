# 0.1.0 Changelog
* Switched from irc to websockets for chat logging
* Implemented fully functional sqlite database
  * Tables are users, livestreams, videos, and messages
  * All livestreaming users that were logged when live will be captured in the users table
  * Only the latest video is captured for each live channel in database.  This table is mainly to associate livestreams with their corresponding VOD and is not meant to be exhaustive
  *	Messages relate to the livestream table with the stream_id
  * Usernames captured in messages are not inserted into the user table.  To be implemented in a future update
* Some debug commands that probably should have been taken out  
* Logging enabled by default. 
