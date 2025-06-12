from discord.ext import commands
import discord
import aiosqlite
import requests

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

DB_FILE = "links.db"

# Initialize the database
@bot.event
async def on_ready():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS user_links (
            discord_id TEXT PRIMARY KEY,
            roblox_id TEXT,
            roblox_username TEXT
        )
        """)
        await db.commit()
    print(f'Logged in as {bot.user.name}')

# Get Roblox user ID from username using Roblox API
async def get_roblox_id(username):
    url = f"https://users.roblox.com/v1/usernames/users"
    response = requests.post(url, json={"usernames": [username], "excludeBannedUsers": True})
    data = response.json()
    if "data" in data and len(data["data"]) > 0:
        return data["data"][0]["id"]
    return None

# User verifies their Roblox account
@bot.command()
async def verify(ctx, roblox_username):
    roblox_id = await get_roblox_id(roblox_username)
    if roblox_id:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("REPLACE INTO user_links (discord_id, roblox_id, roblox_username) VALUES (?, ?, ?)",
                             (str(ctx.author.id), str(roblox_id), roblox_username))
            await db.commit()
        await ctx.send(f"✅ Successfully linked `{roblox_username}` to your Discord account.")
    else:
        await ctx.send("❌ Roblox username not found.")

# Admin command to get Discord user by Roblox username
@bot.command()
@commands.has_permissions(administrator=True)
async def getdiscord(ctx, roblox_username):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT discord_id FROM user_links WHERE roblox_username = ?", (roblox_username,)) as cursor:
            row = await cursor.fetchone()
            if row:
                user = await bot.fetch_user(int(row[0]))
                await ctx.send(f"🔍 Discord user for `{roblox_username}`: {user.mention}")
            else:
                await ctx.send("❌ No linked Discord account found.")

# Run the bot
bot.run(os.getenv("TOKEN"))
