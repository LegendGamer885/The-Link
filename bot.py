import os
import discord
import asyncpg
import requests
import random
import string
from discord.ext import commands
from fastapi import FastAPI, Request
from discord import app_commands
import threading

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents, help_command=None)
DB_URL = os.getenv("DATABASE_URL")

app = FastAPI()

# Utility function to get Roblox ID from username
async def get_roblox_id(username):
    url = "https://users.roblox.com/v1/usernames/users"
    try:
        response = requests.post(url, json={"usernames": [username], "excludeBannedUsers": True})
        data = response.json()
        if "data" in data and len(data["data"]) > 0:
            return data["data"][0]["id"]
    except Exception:
        return None
    return None

def generate_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

@bot.event
async def on_ready():
    async with asyncpg.create_pool(DB_URL) as pool:
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_links (
                    discord_id TEXT PRIMARY KEY,
                    roblox_id TEXT,
                    roblox_username TEXT
                );
                CREATE TABLE IF NOT EXISTS pending_verifications (
                    discord_id TEXT PRIMARY KEY,
                    roblox_id TEXT,
                    roblox_username TEXT,
                    code TEXT
                );
                CREATE TABLE IF NOT EXISTS verified_users (
                    discord_id TEXT PRIMARY KEY,
                    roblox_id TEXT,
                    roblox_username TEXT
                );
            """)

    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"❌ Failed to sync slash commands: {e}")

    print(f"🟢 Bot is ready. Logged in as {bot.user.name}")

@app.post("/verify")
async def verify_user(request: Request):
    data = await request.json()
    print(f"Received verification data: {data}")
    return {"status": "received"}
    
def run_api():
    uvicorn.run(app, host="0.0.0.0", port=8000)

threading.Thread(target=run_api).start()


@bot.tree.command(name="verify", description="Start verification with your Roblox account")
async def verify(interaction: discord.Interaction, roblox_username: str):
    await interaction.response.defer(ephemeral=True)
    roblox_id = await get_roblox_id(roblox_username)

    if not roblox_id:
        await interaction.followup.send("❌ Roblox username not found.", ephemeral=True)
        return

    code = generate_code()

    async with asyncpg.create_pool(DB_URL) as pool:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO pending_verifications (discord_id, roblox_username, roblox_id, code)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (discord_id) DO UPDATE SET
                    roblox_username = EXCLUDED.roblox_username,
                    roblox_id = EXCLUDED.roblox_id,
                    code = EXCLUDED.code
            """, str(interaction.user.id), roblox_username, str(roblox_id), code)
    game_link = ""

    await interaction.followup.send(
        f"✅ Please join the Roblox verification game {game_link} and enter this code: **`{code}`**.", ephemeral=True
    )

@bot.tree.command(name="confirmverify", description="Complete verification after using code in-game")
async def confirmverify(interaction: discord.Interaction):
    discord_id = str(interaction.user.id)

    async with asyncpg.create_pool(DB_URL) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT roblox_id, roblox_username FROM verified_users WHERE discord_id = $1", discord_id)
            if row:
                await conn.execute("""
                    INSERT INTO user_links (discord_id, roblox_id, roblox_username)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (discord_id) DO UPDATE SET
                        roblox_id = EXCLUDED.roblox_id,
                        roblox_username = EXCLUDED.roblox_username
                """, discord_id, row["roblox_id"], row["roblox_username"])
                await interaction.response.send_message(f"🎉 Verified as `{row['roblox_username']}`!", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Could not verify. Please ensure you completed in-game verification.", ephemeral=True)

@bot.tree.command(name="getdiscord", description="(Admin) Get Discord user linked to Roblox username")
@app_commands.checks.has_permissions(administrator=True)
async def getdiscord(interaction: discord.Interaction, roblox_username: str):
    await interaction.response.defer()
    async with asyncpg.create_pool(DB_URL) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT discord_id FROM user_links WHERE roblox_username = $1", roblox_username)
            if row:
                user = await bot.fetch_user(int(row["discord_id"]))
                await interaction.followup.send(f"🔍 Discord user for `{roblox_username}` is {user.mention}")
            else:
                await interaction.followup.send("❌ No user found.")

@bot.tree.command(name="unlink", description="(Admin) Unlink a user's Roblox account")
@app_commands.checks.has_permissions(administrator=True)
async def unlink(interaction: discord.Interaction, discord_user: discord.User):
    await interaction.response.defer()
    async with asyncpg.create_pool(DB_URL) as pool:
        async with pool.acquire() as conn:
            result = await conn.execute("DELETE FROM user_links WHERE discord_id = $1", str(discord_user.id))
            if result.endswith("0"):
                await interaction.followup.send("❌ No link found to delete.")
            else:
                await interaction.followup.send(f"✅ Unlinked Roblox account for {discord_user.mention}")

@bot.tree.command(name="listlinked", description="(Admin) List all linked users")
@app_commands.checks.has_permissions(administrator=True)
async def listlinked(interaction: discord.Interaction):
    await interaction.response.defer()
    async with asyncpg.create_pool(DB_URL) as pool:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT discord_id, roblox_username FROM user_links")
            if not rows:
                await interaction.followup.send("📭 No linked accounts.")
                return
            msg = "**Linked Users:**\n"
            msg += "\n".join(f"<@{row['discord_id']}> ↔️ `{row['roblox_username']}`" for row in rows)
            await interaction.followup.send(msg[:2000])

# Optional: Handle command errors
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("🚫 You don't have permission to use this command.")
    else:
        await ctx.send(f"⚠️ Error: {error}")

# --- Run Bot ---
bot.run(os.getenv("TOKEN"))
