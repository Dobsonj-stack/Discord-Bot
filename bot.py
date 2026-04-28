import asyncio
import json
import os
from collections import deque
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Deque, Dict, List, Optional

import discord
from discord.ext import commands
from dotenv import load_dotenv
from yt_dlp import YoutubeDL

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
COOKIES_FILE = os.getenv("YTDLP_COOKIES_FILE")

PLAYLISTS_PATH = Path("playlists.json")

YTDLP_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "ytsearch",
}

if COOKIES_FILE:
    YTDLP_OPTIONS["cookiefile"] = COOKIES_FILE

FFMPEG_OPTIONS = {
    "options": "-vn",
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
}


@dataclass
class QueueItem:
    title: str
    webpage_url: str
    stream_url: str
    requested_by: str


class GuildPlayer:
    def __init__(self) -> None:
        self.queue: Deque[QueueItem] = deque()
        self.lock = asyncio.Lock()


players: Dict[int, GuildPlayer] = {}

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)


def get_player(guild_id: int) -> GuildPlayer:
    if guild_id not in players:
        players[guild_id] = GuildPlayer()
    return players[guild_id]


def load_playlists() -> Dict[str, List[dict]]:
    if not PLAYLISTS_PATH.exists():
        return {}
    with PLAYLISTS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_playlists(data: Dict[str, List[dict]]) -> None:
    with PLAYLISTS_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def extract_track(search: str) -> QueueItem:
    with YoutubeDL(YTDLP_OPTIONS) as ydl:
        info = ydl.extract_info(search, download=False)
        if info is None:
            raise ValueError("No results found.")

        if "entries" in info:
            entry = info["entries"][0]
        else:
            entry = info

        if not entry:
            raise ValueError("No playable entry found.")

        return QueueItem(
            title=entry.get("title", "Unknown title"),
            webpage_url=entry.get("webpage_url") or entry.get("url", ""),
            stream_url=entry["url"],
            requested_by="",
        )


async def ensure_voice(message: discord.Message) -> Optional[discord.VoiceClient]:
    if not message.guild:
        return None

    if not message.author.voice or not message.author.voice.channel:
        await message.channel.send("Join a voice channel first.")
        return None

    voice_client = message.guild.voice_client
    if voice_client and voice_client.channel != message.author.voice.channel:
        await voice_client.move_to(message.author.voice.channel)
    elif not voice_client:
        voice_client = await message.author.voice.channel.connect()

    return message.guild.voice_client


async def play_next(guild: discord.Guild, text_channel: discord.abc.Messageable) -> None:
    player = get_player(guild.id)
    voice_client = guild.voice_client

    if not voice_client:
        return

    async with player.lock:
        if not player.queue:
            await text_channel.send("Queue is empty.")
            return

        item = player.queue[0]

    def after_playback(error: Optional[Exception]) -> None:
        if error:
            print(f"Playback error: {error}")

        async def _continue() -> None:
            async with player.lock:
                if player.queue:
                    player.queue.popleft()
            await play_next(guild, text_channel)

        asyncio.run_coroutine_threadsafe(_continue(), bot.loop)

    source = await discord.FFmpegOpusAudio.from_probe(item.stream_url, **FFMPEG_OPTIONS)
    voice_client.play(source, after=after_playback)
    await text_channel.send(f"▶️ Now playing: **{item.title}** (requested by {item.requested_by})")


@bot.event
async def on_ready() -> None:
    print(f"Logged in as {bot.user}")


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot or not message.guild:
        return

    if bot.user in message.mentions:
        content = message.content
        mention_forms = [f"<@{bot.user.id}>", f"<@!{bot.user.id}>"]
        for mention in mention_forms:
            content = content.replace(mention, "")
        command_text = content.strip()

        if not command_text:
            await message.channel.send(
                "Mention me with a song URL/search, or use: `queue`, `skip`, `stop`, "
                "`playlist save <name>`, `playlist load <name>`, `playlist list`."
            )
            return

        player = get_player(message.guild.id)
        lower = command_text.lower()

        if lower == "queue":
            async with player.lock:
                if not player.queue:
                    await message.channel.send("Queue is empty.")
                    return
                lines = [f"{idx + 1}. {item.title}" for idx, item in enumerate(list(player.queue)[:10])]
            await message.channel.send("\n".join(["Current queue:", *lines]))
            return

        if lower == "skip":
            vc = message.guild.voice_client
            if vc and vc.is_playing():
                vc.stop()
                await message.channel.send("⏭️ Skipped.")
            else:
                await message.channel.send("Nothing is currently playing.")
            return

        if lower == "stop":
            vc = message.guild.voice_client
            if vc:
                async with player.lock:
                    player.queue.clear()
                await vc.disconnect()
                await message.channel.send("⏹️ Stopped and cleared queue.")
            else:
                await message.channel.send("I am not in a voice channel.")
            return

        if lower.startswith("playlist "):
            parts = command_text.split(maxsplit=2)
            if len(parts) < 2:
                await message.channel.send("Usage: playlist <save|load|list> [name]")
                return

            action = parts[1].lower()
            playlists = load_playlists()
            guild_key = str(message.guild.id)
            guild_playlists = playlists.setdefault(guild_key, {})

            if action == "list":
                names = sorted(guild_playlists.keys())
                if not names:
                    await message.channel.send("No saved playlists for this server yet.")
                else:
                    await message.channel.send("Saved playlists: " + ", ".join(names))
                return

            if len(parts) < 3:
                await message.channel.send("Please provide a playlist name.")
                return

            name = parts[2].strip().lower()

            if action == "save":
                async with player.lock:
                    if not player.queue:
                        await message.channel.send("Queue is empty, nothing to save.")
                        return
                    guild_playlists[name] = [asdict(item) for item in player.queue]
                save_playlists(playlists)
                await message.channel.send(f"Saved queue as playlist `{name}`.")
                return

            if action == "load":
                if name not in guild_playlists:
                    await message.channel.send(f"Playlist `{name}` not found.")
                    return

                vc = await ensure_voice(message)
                if not vc:
                    return

                async with player.lock:
                    for raw in guild_playlists[name]:
                        player.queue.append(QueueItem(**raw))
                    should_start = not vc.is_playing()

                await message.channel.send(f"Loaded playlist `{name}` into queue.")
                if should_start:
                    await play_next(message.guild, message.channel)
                return

            await message.channel.send("Unknown playlist action. Use save, load, or list.")
            return

        vc = await ensure_voice(message)
        if not vc:
            return

        await message.channel.trigger_typing()
        try:
            item = await asyncio.to_thread(extract_track, command_text)
            item.requested_by = message.author.display_name
        except Exception as exc:
            await message.channel.send(f"Could not load track: {exc}")
            return

        async with player.lock:
            player.queue.append(item)
            should_start = not vc.is_playing()

        await message.channel.send(f"➕ Added to queue: **{item.title}**")
        if should_start:
            await play_next(message.guild, message.channel)
        return

    await bot.process_commands(message)


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is required. Set it in your environment or .env file.")
    bot.run(TOKEN)
