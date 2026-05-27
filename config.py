"""Central configuration for the YouTube music bot — all from env vars."""
import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
# Public (non-secret) Application/Client ID — used to build the invite link.
APPLICATION_ID = os.getenv("APPLICATION_ID", "")

# Permissions: View Channels + Send Messages + Embed Links + Read History +
# Connect + Speak.  (1024+2048+16384+65536+1048576+2097152)
INVITE_PERMISSIONS = os.getenv("INVITE_PERMISSIONS", "3228720")

# Optional: set to your test server's ID to sync slash commands instantly.
DEV_GUILD_ID = os.getenv("DEV_GUILD_ID", "")

# Disconnect after this many seconds with an empty queue / nobody listening.
IDLE_TIMEOUT = int(os.getenv("IDLE_TIMEOUT", "300"))

# Default playback volume (0.0–2.0). 1.0 = 100%.
DEFAULT_VOLUME = float(os.getenv("DEFAULT_VOLUME", "0.5"))


def invite_url() -> str:
    if not APPLICATION_ID:
        return ""
    return (
        "https://discord.com/oauth2/authorize"
        f"?client_id={APPLICATION_ID}"
        f"&permissions={INVITE_PERMISSIONS}"
        "&scope=bot%20applications.commands"
    )
