import os
import discord
import asyncpg
import requests
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)
DB_URL = os.getenv("DATABASE_URL")

@bot.event
async def on_ready():
    # Connect to database and create table
    conn = await asyncpg.connect(DB_URL)
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS user_links (
        discord_id TEXT PRIMARY KEY,
        roblox_id TEXT,
        roblox_username TEXT
    )
    """)
    await conn.close()

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"❌ Failed to sync slash commands: {e}")

    print(f"🟢 Bot is ready. Logged in as {bot.user.name}")

# --- Utility Function ---
async def get_roblox_id(username):
    url = "https://users.roblox.com/v1/usernames/users"
    response = requests.post(url, json={"usernames": [username], "excludeBannedUsers": True})
    data = response.json()
    if "data" in data and len(data["data"]) > 0:
        return data["data"][0]["id"]
    return None

# --- SLASH COMMANDS ---
@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="🤖 Bot Command Guide",
        description="Here are the commands you can use with this bot:",
        color=discord.Color.blue()
    )

    # Regular user commands
    embed.add_field(
        name="🔗 /verify `<roblox_username>`",
        value="Links your Roblox account to your Discord.",
        inline=False
    )

    # Admin commands
    embed.add_field(
        name="🕵️ /getdiscord `<roblox_username>`",
        value="(Admin) Fetches the Discord account linked to a Roblox username.",
        inline=False
    )
    embed.add_field(
        name="🚫 /unlink `<@discord_user>`",
        value="(Admin) Unlinks a Discord user's Roblox connection.",
        inline=False
    )
    embed.add_field(
        name="📋 /listlinked",
        value="(Admin) Lists all linked Discord–Roblox pairs.",
        inline=False
    )

    # Help command info
    embed.add_field(
        name="📘 !help",
        value="Displays this help message.",
        inline=False
    )

    embed.set_footer(text="Bot powered by Railway + PostgreSQL")

    await ctx.send(embed=embed)


@bot.tree.command(name="verify", description="Link your Roblox account to your Discord")
async def verify(interaction: discord.Interaction, roblox_username: str):
    await interaction.response.defer()
    roblox_id = await get_roblox_id(roblox_username)
    if roblox_id:
        conn = await asyncpg.connect(DB_URL)
        await conn.execute("""
            INSERT INTO user_links (discord_id, roblox_id, roblox_username)
            VALUES ($1, $2, $3)
            ON CONFLICT (discord_id) DO UPDATE SET
                roblox_id = EXCLUDED.roblox_id,
                roblox_username = EXCLUDED.roblox_username
        """, str(interaction.user.id), str(roblox_id), roblox_username)
        await conn.close()
        await interaction.followup.send(f"✅ Linked Roblox user `{roblox_username}` successfully.")
    else:
        await interaction.followup.send("❌ Roblox username not found.")

@bot.tree.command(name="getdiscord", description="(Admin) Get the Discord user linked to a Roblox username")
@commands.has_permissions(administrator=True)
async def getdiscord(interaction: discord.Interaction, roblox_username: str):
    await interaction.response.defer()
    conn = await asyncpg.connect(DB_URL)
    row = await conn.fetchrow("SELECT discord_id FROM user_links WHERE roblox_username = $1", roblox_username)
    await conn.close()
    if row:
        user = await bot.fetch_user(int(row["discord_id"]))
        await interaction.followup.send(f"🔍 Discord user for `{roblox_username}` is {user.mention}")
    else:
        await interaction.followup.send("❌ No user found.")

@bot.tree.command(name="unlink", description="(Admin) Unlink a user’s Roblox account")
@commands.has_permissions(administrator=True)
async def unlink(interaction: discord.Interaction, discord_user: discord.User):
    await interaction.response.defer()
    conn = await asyncpg.connect(DB_URL)
    result = await conn.execute("DELETE FROM user_links WHERE discord_id = $1", str(discord_user.id))
    await conn.close()
    if result.endswith("0"):
        await interaction.followup.send("❌ No link found to delete.")
    else:
        await interaction.followup.send(f"✅ Unlinked Roblox account for {discord_user.mention}")

@bot.tree.command(name="listlinked", description="(Admin) List all linked users")
@commands.has_permissions(administrator=True)
async def listlinked(interaction: discord.Interaction):
    await interaction.response.defer()
    conn = await asyncpg.connect(DB_URL)
    rows = await conn.fetch("SELECT discord_id, roblox_username FROM user_links")
    await conn.close()

    if not rows:
        await interaction.followup.send("📭 No linked accounts.")
        return

    message = "**Linked Users:**\n"
    for row in rows:
        user_id = row["discord_id"]
        roblox_user = row["roblox_username"]
        message += f"<@{user_id}> ↔️ `{roblox_user}`\n"

    await interaction.followup.send(message[:2000])  # Discord message limit

# --- Error Logging ---
@bot.event
async def on_command_error(ctx, error):
    await ctx.send(f"⚠️ Error: {str(error)}")
    raise error

# --- Run Bot ---
bot.run(os.getenv("TOKEN"))
