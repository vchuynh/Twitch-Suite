CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    twitch_id INTEGER NOT NULL UNIQUE,--as returned by twitch api
    login TEXT NOT NULL UNIQUE,
    display_name TEXT,
    broadcaster_type TEXT,
    description TEXT,
    view_count INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS livestreams (
    id INTEGER PRIMARY KEY,
    twitch_id INTEGER NOT NULL UNIQUE,--twitch stream id
    user_twitch_id INTEGER NOT NULL,--twitch user id (superkey for users table)
    title TEXT,
    started_at TEXT,
    FOREIGN KEY(user_twitch_id) REFERENCES users(twitch_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY,
    twitch_id INTEGER NOT NULL UNIQUE,--as returned by twitch api
    stream_id INTEGER, --probably unique, but wont enforce
    user_id INTEGER NOT NULL,
    created_at TEXT,
    published_at TEXT,
    title TEXT,
    FOREIGN KEY(stream_id) REFERENCES livestreams(twitch_id) ON DELETE CASCADE,
    FOREIGN KEY(user_id) REFERENCES users(twitch_id) ON DELETE CASCADE 
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    stream_id INTEGER,--livestreams(id) not twitch stream id
    chatter TEXT NOT NULL,--users(username)
    channel TEXT NOT NULL,--users(username)
    message TEXT NOT NULL,
    datetime TEXT NOT NULL,--pre 0.1 logs incompatible
    FOREIGN KEY(stream_id) REFERENCES livestreams(twitch_id) ON DELETE CASCADE
    --to be enforced in a later update
    --FOREIGN KEY(chatter) REFERENCES users(login) ON DELETE CASCADE
    --FOREIGN KEY(channel) REFERENCES users(login) ON DELETE CASCADE
);