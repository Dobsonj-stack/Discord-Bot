# Discord YouTube Queue Bot

A simple Discord music bot that works with **@mentions** instead of slash commands.

## Features

- Mention-based controls (example: `@MyBot lo-fi hip hop`)
- Adds songs from YouTube URLs or search text
- Per-server queue
- Skip/stop controls
- Save and load per-server playlists
- Works without login by default
- Optional YouTube cookies support for accounts with premium/private access

## How premium/login works

By default, the bot runs without any account login.

If you need access to content only available to your YouTube account (for example age-gated or premium-only content), you can export your own browser cookies and set:

- `YTDLP_COOKIES_FILE=/path/to/cookies.txt`

This is optional and only used when provided.

## Setup

1. Create a Discord bot in the Discord Developer Portal.
2. Enable **Message Content Intent** and **Server Members Intent** (if needed).
3. Invite the bot to your server with permissions for:
   - Send Messages
   - Connect / Speak in Voice Channels
4. Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

5. Configure env vars:

```bash
cp .env.example .env
# edit .env and set DISCORD_TOKEN
```

6. Run:

```bash
python bot.py
```

## Usage

Replace `@MyBot` with your bot mention.

- Add song by search:
  - `@MyBot never gonna give you up`
- Add song by URL:
  - `@MyBot https://www.youtube.com/watch?v=dQw4w9WgXcQ`
- Show queue:
  - `@MyBot queue`
- Skip current song:
  - `@MyBot skip`
- Stop and clear queue:
  - `@MyBot stop`
- Save queue as playlist:
  - `@MyBot playlist save party`
- Load playlist:
  - `@MyBot playlist load party`
- List playlists:
  - `@MyBot playlist list`

## Notes

- Requires FFmpeg installed on the host.
- `playlists.json` is created automatically.
- Keep your bot token private.
