import discord
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput
import os
import math
import json
import random
import asyncio
from typing import Dict, List, Any  # Import Any for type hinting
from supabase import create_client, Client
from cachetools import TTLCache
import re
from collections import deque
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
# --- Supabase Setup ---
url: str = os.getenv("SUPABASE_URL")
print("Supabase URL:", url)  # Print the URL for debugging
key: str = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(url, key)


# --- Important ---
# Load authorized users from environment variable
auth_users_str = os.getenv("AUTHORIZED_USERS", "")
AUTHORIZED_USERS = [int(user_id) for user_id in auth_users_str.split(",") if user_id]

AUTHORIZED_MEMBER = []

# Load role ID from environment variable
ROLE_ID = int(os.getenv("ROLE_ID", 0))

# --- Discord Bot Setup ---
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', 
                   intents=intents,
                   case_insensitive=True,
                   help_command=None)

bot.remove_command('help') 

# --- Custom get_context Function ---
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    # Process all messages through the regular command system
    await bot.process_commands(message)
# --- Allowed Channel IDs ---
INFINITY_THRESHOLD = 9999999999999
NEGATIVE_INFINITY_THRESHOLD = -9999999999999

# Load channel IDs from environment variables
ALLOWED_CHANNEL_IDS = [int(os.getenv("ALLOWED_CHANNEL_IDS", 0))]
HUNT_CHANNEL_ID = int(os.getenv("HUNT_CHANNEL_ID", 0))
NOTIFICATION_CHANNEL_ID = int(os.getenv("NOTIFICATION_CHANNEL_ID", 0))
ITEMS_PER_PAGE = 10
# --- Admin Role ID ---
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", 0))

hunt_cooldown = commands.CooldownMapping.from_cooldown(
    1, 10, commands.BucketType.user)  

# --- Weather and Storm System Variables ---
REGULAR_WEATHER_DURATION = 900  # 15 minutes for regular weather
CHAOS_DURATION = 1800  # 30 minutes for chaotic weather
CHAOS_SUB_WEATHER_DURATION = 300  # 5 minutes for each sub-weather during Chaos 
STORM_WARNING_DURATION = 10  
BLIZZARD_DURATION = 180  
BLIZZARD_BREAK = 300  
MANUAL_WEATHER_DURATION = 900
STORM_DAMAGE = {
    "Stormy": 20,
    "Super Storm": 40
}
# Camp degradation per storm type
CAMP_DEGRADATION = {
    "Stormy": 40,
    "Super Storm": 60
}
STORM_WARNING_DURATION_CHAOS = 0
STORM_DAMAGE_CHAOS = {
    "Stormy": 60,
    "Super Storm": 90
}
CAMP_DEGRADATION_CHAOS = {
    "Stormy": 80,
    "Super Storm": 200
}
WEATHER_COLORS = {
    "Sunny": [discord.Color.from_rgb(255, 255, 0), discord.Color.from_rgb(255, 215, 0), discord.Color.from_rgb(255, 165, 0)],
    "Rainy": [discord.Color.from_rgb(135, 206, 250), discord.Color.from_rgb(70, 130, 180), discord.Color.from_rgb(176, 224, 230)],
    "Snowy": [discord.Color.from_rgb(230, 230, 250), discord.Color.from_rgb(240, 255, 240), discord.Color.from_rgb(255, 250, 250)],
    "Stormy": [discord.Color.from_rgb(105, 105, 105), discord.Color.from_rgb(169, 169, 169), discord.Color.from_rgb(0, 0, 128)],
    "Super Storm": [discord.Color.from_rgb(47, 79, 79), discord.Color.from_rgb(0, 0, 0), discord.Color.from_rgb(75, 0, 130)]
}
WEATHER_THUMBNAILS = {
    "Sunny": "https://ucarecdn.com/1ec0bb38-7539-45f8-b91c-b76863ba3734/-/preview/960x540/",
    "Rainy": "https://ucarecdn.com/5144d624-246a-4873-ab7d-bcf3dd849d11/-/preview/1000x562/",
    "Snowy": "https://ucarecdn.com/a9c171b7-e424-446a-a5e6-34f7a5a991ee/-/preview/1000x562/",
    "Stormy": "https://ucarecdn.com/28af7a4c-e8e3-484c-80ee-36bb758042a9/-/preview/900x506/",
    "Super Storm": "https://ucarecdn.com/8e8c9caf-0fd7-47f6-9385-e9b330a65b87/-/preview/900x506/",
    "Chaos": "https://ucarecdn.com/bf6054f1-e16b-40ec-b9b9-51499b5eb3b5/-/preview/960x540/"  
}

# --- Emojis ---
WEATHER_EMOJIS = {
    "Sunny": "☀️",
    "Snowy": "❄️",
    "Rainy": "🌧️",
    "Stormy": "⛈️",
    "Super Storm": "🌪️",
    "Blizzard": "🧊"  
}
current_weather = "Sunny"  # Initial weather
weather_end_time = asyncio.get_event_loop().time() + REGULAR_WEATHER_DURATION
weather_task = None  # Task for managing the current weather cycle
blizzard_task = None # Task for managing blizzard cycles
storm_active = False
storm_warning_active = False
storm_warned_users: Dict[int, float] = {}
camp_users_lock = asyncio.Lock()
camp_users: Dict[str, Any] = {}
last_weathers = [] 
bioweather_uses = 0
bioweather_lock = asyncio.Lock() 
chaos_active = False
blizzard_event = asyncio.Event()
blizzard_active = asyncio.Event() 
manual_weather_active = False 
current_chaos_task: asyncio.Task = None
current_sub_weather = None
last_weathers = deque(maxlen=5)
markets = []
player_data: Dict[str, Any] = {} 
coin_data: Dict[str, int] = {}  
user_cache = TTLCache(maxsize=100, ttl=600) 
stats_messages: Dict[int, discord.Message] = {}
def log_admin_command(user, command):
    with open('admin_logs.txt', 'a') as f:
        f.write(f"[{user}] : {command}\n")

# Save and Load data
async def load_data(table_name: str) -> List[Dict[str, Any]]:
    try:
        response = supabase.table(table_name).select("*").execute()
        return response.data
    except Exception as e:
        print(f"Error loading data from {table_name}: {e}")
        return [] 

# --- Modified save_data to send all columns ---
async def save_data(table_name: str, data: Dict[str, Any], upsert=False) -> None:
    try:
        # Create complete data dictionaries for each table
        if table_name == 'player_data':
            user_id = data.get('user_id')
            # Always get the complete data from player_data 
            complete_data = player_data.get(str(user_id), {}).copy()
            complete_data.update(data)  # Update with provided changes
        elif table_name == 'coin_data':
            complete_data = {
                'user_id': data.get('user_id'),
                'coins': data.get('coins', 10)  # Default coins to 10
            }
        elif table_name == 'markets':
            complete_data = {
                'id': data.get('id'),
                'name': data.get('name'),
                'description': data.get('description'),
                'cost': data.get('cost'),
                'seller': data.get('seller')
            }
        elif table_name == 'transactions':
            complete_data = {
                'id': data.get('id'),
                'buyer': data.get('buyer'),
                'seller': data.get('seller'),
                'market_id': data.get('market_id'),
                'status': data.get('status', 'pending') # Default status
            }
        else:
            complete_data = data  # For any other tables, use the provided data

        if upsert:
            response = supabase.table(table_name).update(complete_data).eq('user_id', data.get('user_id')).execute()
        else:
            response = supabase.table(table_name).insert(complete_data).execute()
        print(f"Data saved to {table_name}: {response}")
    except Exception as e:
        print(f"Error saving data to {table_name}: {e}")

def handle_infinity(value):
    if value >= INFINITY_THRESHOLD:
        return '∞'
    elif value <= NEGATIVE_INFINITY_THRESHOLD:
        return '-∞'
    else:
        return f'{value:,}'

def add_with_infinity(current_value, amount_to_add):
    if current_value >= INFINITY_THRESHOLD: 
        return current_value  
    else:
        new_value = current_value + amount_to_add
        return max(min(new_value, INFINITY_THRESHOLD), NEGATIVE_INFINITY_THRESHOLD)

def subtract_with_infinity(current_value, amount_to_subtract):
    if current_value >= INFINITY_THRESHOLD and amount_to_subtract > 0:
        return current_value
    elif current_value <= NEGATIVE_INFINITY_THRESHOLD and amount_to_subtract < 0:  
        return current_value
    else:
        new_value = current_value - amount_to_subtract
        return max(min(new_value, INFINITY_THRESHOLD), NEGATIVE_INFINITY_THRESHOLD)

async def get_user_with_cache(user_id):
    if user_id in user_cache:
        return user_cache[user_id]
    else:
        user = await bot.fetch_user(user_id)
        user_cache[user_id] = user 
        return user

# --- Decorators ---
def in_allowed_channels():

    def predicate(ctx):
        if any(role.id == ADMIN_ROLE_ID for role in ctx.author.roles):
            return True
        return ctx.channel.id in ALLOWED_CHANNEL_IDS

    return commands.check(predicate)

def in_hunt_channel():

    def predicate(ctx):
        if any(role.id == ADMIN_ROLE_ID for role in ctx.author.roles):
            return True
        return ctx.channel.id == HUNT_CHANNEL_ID

    return commands.check(predicate)

def in_hunt_or_allowed_channels():
    
    def predicate(ctx):
        if any(role.id == ADMIN_ROLE_ID for role in ctx.author.roles):
            return True
        return ctx.channel.id == HUNT_CHANNEL_ID or ctx.channel.id in ALLOWED_CHANNEL_IDS

    return commands.check(predicate)

def check_no_role(role_id: int):

    def predicate(ctx):
        role = discord.utils.get(ctx.author.roles, id=role_id)
        return role is None

    return commands.check(predicate)
# -- Initialize --
async def initialize_player_data(user_id: str):
    global player_data
    existing_data = supabase.table('player_data').select("*").eq('user_id', int(user_id)).execute()
    if not existing_data.data:
        player_data[user_id] = {
            "user_id": int(user_id),
            "gun_durability": 30,
            "ammo": 30,
            "health": 100,
            "camp_durability": 100,
            "healing_potions": 1
        }
        await save_data('player_data', player_data[user_id])
    else:
        player_data[user_id] = existing_data.data[0]
        # Apply infinity logic to player_data on load
        for key in ["gun_durability", "ammo", "camp_durability", "healing_potions"]:
            if player_data[user_id][key] >= INFINITY_THRESHOLD:
                player_data[user_id][key] = INFINITY_THRESHOLD

# --- Unified Weather Control Loop ---
@tasks.loop(seconds=1)
async def weather_manager():
    global current_weather, weather_end_time, weather_task, storm_warned_users, blizzard_task
    channel = bot.get_channel(HUNT_CHANNEL_ID)

    if asyncio.get_event_loop().time() >= weather_end_time:
        if current_weather == "Chaos":
            await end_chaos_weather(channel)
        else:
            await change_weather(channel) 

# --- Change Weather Function (Regular or Manual) ---
async def change_weather(channel, new_weather=None, duration=REGULAR_WEATHER_DURATION):
    global current_weather, weather_end_time, weather_task, last_weathers, blizzard_task 

    # Cancel existing weather and blizzard tasks
    if weather_task and not weather_task.done():
        weather_task.cancel()
    if blizzard_task and not blizzard_task.done():
        blizzard_task.cancel()

    # If new_weather is not provided, determine it automatically
    if new_weather is None:
        valid_weathers = ["Sunny", "Snowy", "Rainy", "Stormy"]
        new_weather = random.choices(valid_weathers, weights=[43, 43, 43, 35], k=1)[0]
        if new_weather == "Stormy" and random.random() <= 0.1:
            new_weather = "Super Storm"

    # ------------------------ CHAOS TRIGGER ------------------------
    print(f"last_weathers before append: {last_weathers}")

# Always append the new weather
    last_weathers.append(new_weather) 

    print(f"Added {new_weather} to last_weathers: {last_weathers}")

    # Check for Chaos AFTER appending the new weather
    if len(last_weathers) >= 5 and len(set(last_weathers)) == 5:
        new_weather = "Chaos"
        duration = CHAOS_DURATION
        last_weathers.clear()  #s
        print("Chaos triggered!")

    # ----------------------- Update current_weather---------------------- 
    current_weather = new_weather  

    # ----------------------- CHAOS TRIGGER----------------------

    current_weather = new_weather  # Update the current weather 
    weather_end_time = asyncio.get_event_loop().time() + duration

    # --- Create a new weather task based on the current weather ---
    if current_weather == "Snowy": 
        weather_task = asyncio.create_task(handle_snowy_weather(channel)) 
        blizzard_task = asyncio.create_task(blizzard_cycle(channel))
    
    elif current_weather == "Chaos":  # Start Chaos task here!
        weather_task = asyncio.create_task(handle_chaos_weather(channel))
    else:  
        weather_task = asyncio.create_task(handle_regular_weather(channel))

    # --- Send weather update embed ---
    embed = discord.Embed(
        title="Weather Update",
        color=random.choice(WEATHER_COLORS.get(current_weather, [discord.Color.dark_teal()]))
    )
    embed.set_thumbnail(url=WEATHER_THUMBNAILS.get(current_weather)) 

    # --- Determine the message based on the weather ---
    if current_weather == "Sunny":
        embed.description = f"The **Sun** is shining brightly! last for {duration // 60} mins."
    elif current_weather == "Snowy":
        embed.description = f"The **Snow** begins to fall!  last for {duration // 60} mins."
    elif current_weather == "Rainy":
        embed.description = f"The **Rain** begins to fall! last for {duration // 60} mins."
    elif current_weather == "Stormy":
        embed.description = f"The **Stormy** overhead! last for {duration // 60} mins."
    elif current_weather == "Super Storm":
        embed.description = f"A **Super Storm** raging! last for {duration // 60} mins."

    # --- Send the weather update embed ---
    await channel.send(embed=embed)

    # --- Check if the weather is actually changing ---
    if current_weather != new_weather:  
        weather_end_time = asyncio.get_event_loop().time() + duration
    else: 
        # The weather is not actually changing, so do nothing! 
        await channel.send(f"The weather is already {current_weather}.")
        return
# --- End Chaos Weather ---
async def end_chaos_weather(channel):
    """Resets the weather after Chaos ends."""
    global current_weather, weather_end_time, chaos_triggered_naturally, weather_task

    await channel.send(
        embed=discord.Embed(
            title="**𝕮𝖍𝖆𝖔𝖘 𝕰𝖓𝖉𝖘!**",
            description="**𝓣𝓱𝓮 𝓬𝓱𝓪𝓸𝓽𝓲𝓬 𝔀𝓮𝓪𝓽𝓱𝓮𝓻 𝓼𝓾𝓫𝓼𝓲𝓭𝓮𝓼, 𝓻𝓮𝓽𝓾𝓻𝓷𝓲𝓷𝓰 𝓽𝓸 𝓪 𝓶𝓸𝓻𝓮 𝓹𝓻𝓮𝓭𝓲𝓬𝓽𝓪𝓫𝓵𝓮 𝓹𝓪𝓽𝓽𝓮𝓻𝓷...**",
            color=discord.Color.purple()
        )
    )

    chaos_triggered_naturally = False
    await change_weather(channel)
# --- Handle Regular Weather (Sunny, Rainy, Stormy, Super Storm) ---
async def handle_regular_weather(channel):
    """Manages regular weather cycles (not Chaos)."""
    global current_weather, weather_end_time 
    await asyncio.sleep(weather_end_time - asyncio.get_event_loop().time())  

# --- Handle Snowy Weather and Potential Blizzards ---
async def handle_snowy_weather(channel): 
    """Handles Snowy weather, allowing blizzards to start."""
    global current_weather, weather_end_time
    await asyncio.sleep(weather_end_time - asyncio.get_event_loop().time())

# --- Handle Chaos Weather ---
async def handle_chaos_weather(channel):
    """Manages sub-weather changes during Chaos."""
    global current_weather, weather_end_time, current_sub_weather
    start_time = asyncio.get_event_loop().time()
    previous_sub_weather = None
    first_transition = True
    current_blizzard_task = None 
    # Set weather_end_time ONCE at the beginning of Chaos
    weather_end_time = start_time + CHAOS_DURATION  

    while asyncio.get_event_loop().time() < weather_end_time:
        current_sub_weather = random.choice(["Sunny", "Snowy", "Rainy", "Stormy", "Super Storm"])
        print(f"Current sub-weather during Chaos: {current_sub_weather}") 

        if current_sub_weather == "Snowy":
            # Cancel existing blizzard task (if any)
            if current_blizzard_task and not current_blizzard_task.done():
                current_blizzard_task.cancel()

            current_blizzard_task = asyncio.create_task(chaos_blizzard_cycle(channel)) 

        if current_sub_weather != previous_sub_weather:
            # Perform the transition only once
            if first_transition:
                await chaos_transition(channel, current_sub_weather)
                first_transition = False

            # Send the announcement
            embed = discord.Embed(
                title=f"🌪️ 𝕮𝖍𝖆𝖔𝖘 𝕽𝖊𝖎𝖌𝖓𝖘! 🌪️",
                description=f"The chaotic weather shifts to {current_sub_weather}!", 
                color=random.choice(WEATHER_COLORS.get(current_sub_weather, [discord.Color.dark_teal()]))
            )
            embed.set_thumbnail(url=WEATHER_THUMBNAILS.get("Chaos"))  # Add thumbnail for sub-weather
            await channel.send(embed=embed)
            await asyncio.sleep(CHAOS_SUB_WEATHER_DURATION) 
        previous_sub_weather = current_sub_weather

# --- Normal Blizzard Cycle Logic ---
async def blizzard_cycle(ctx):
    global blizzard_event, current_weather, blizzard_active, weather_end_time
    blizzard_active.set()

    if current_weather == "Snowy":
        start_time = asyncio.get_event_loop().time()
        duration = REGULAR_WEATHER_DURATION  # 15 minutes (900 seconds)
        cycle_count = 0

        while asyncio.get_event_loop().time() < (start_time + duration) and blizzard_active.is_set():
            # 1 & 2: Random Blizzard Duration (1-3 minutes) BUT ensure it's less than remaining time
            time_remaining = start_time + duration - asyncio.get_event_loop().time()
            blizzard_duration = random.randint(60, min(180, int(max(0, time_remaining - 60)))) # <-- Ensure blizzard_duration is at least 60 seconds less than time_remaining 

            # 3: Force 2nd Cycle if Time is Running Out (no changes needed here)
            if time_remaining <= 300 and cycle_count < 1: 
                blizzard_duration = int(time_remaining - 5) 
             # Use almost all remaining time (leave 5 seconds)

            blizzard_event.set()
            blizzard_embed = discord.Embed(
                title=f"{WEATHER_EMOJIS['Blizzard']} Blizzard Warning!",
                color=random.choice(WEATHER_COLORS["Snowy"])
            )
            blizzard_embed.description = f"A blizzard has descended! It will last for {blizzard_duration} seconds."
            await ctx.send(embed=blizzard_embed)
            await asyncio.sleep(blizzard_duration)
            blizzard_event.clear()

            cycle_count += 1

            # 4: Calculate Rest Time
            time_remaining = start_time + duration - asyncio.get_event_loop().time()
            if time_remaining > blizzard_duration:  # Enough time for another cycle
                break_duration = random.randint(60, max(60, int(time_remaining - blizzard_duration)))
                break_embed = discord.Embed(
                    title=f"The blizzard has subsided for now...",
                    color=random.choice(WEATHER_COLORS["Snowy"])
                )
                await ctx.send(embed=break_embed)
                await asyncio.sleep(break_duration)
            else:  # Not enough time, end the cycle
                break

    blizzard_active.clear()
# --- Chaos Blizzard Cycle Logic ---
async def chaos_blizzard_cycle(ctx):
    global blizzard_event, current_sub_weather, blizzard_active
    blizzard_active.set()  

    if current_sub_weather == "Snowy":
        start_time = asyncio.get_event_loop().time()
        duration = CHAOS_SUB_WEATHER_DURATION  # 5 minutes 
        cycle_count = 0

        while asyncio.get_event_loop().time() < (start_time + duration) and blizzard_active.is_set():
            # 1 & 2: Random Blizzard Duration (20-40 seconds)
            blizzard_duration = random.randint(20, 40)

            # 3: Force 2nd Cycle if Time is Running Out
            time_remaining = start_time + duration - asyncio.get_event_loop().time()
            if time_remaining <= 60 and cycle_count < 1:  # 1 minute left & only 1 cycle done
                blizzard_duration = int(time_remaining - 5)  # Use almost all remaining time (leave 5 seconds)

            blizzard_event.set()
            blizzard_embed = discord.Embed(
                title=f"{WEATHER_EMOJIS['Blizzard']} ₵Ⱨ₳Ø₴ Blizzard Warning!",
                color=random.choice(WEATHER_COLORS["Snowy"])
            )
            blizzard_embed.description = f"₳ ₵Ⱨ₳Ø₴ blizzard has descended! It will last for {blizzard_duration} seconds."
            await ctx.send(embed=blizzard_embed)
            await asyncio.sleep(blizzard_duration)
            blizzard_event.clear()

            cycle_count += 1

            # 4: Calculate Rest Time
            time_remaining = start_time + duration - asyncio.get_event_loop().time()
            if time_remaining > blizzard_duration:  # Enough time for another cycle
                break_duration = random.randint(10, int(time_remaining - blizzard_duration))
                break_embed = discord.Embed(
                    title=f"The ₵Ⱨ₳Ø₴ blizzard has subsided for now...",
                    color=random.choice(WEATHER_COLORS["Snowy"])
                )
                await ctx.send(embed=break_embed)
                await asyncio.sleep(break_duration)
            else:
                break  # Not enough time, end the cycle

    blizzard_active.clear()

async def chaos_transition(ctx, next_weather): 
    global current_weather

    chaos_colors = [
        discord.Color.purple(),
        discord.Color.dark_purple(),
        discord.Color.magenta(),
        discord.Color.dark_magenta(),
        discord.Color.dark_red()
    ]

    for color in chaos_colors:
        embed = discord.Embed(
            title="𝖳𝖍𝖊 𝖂𝖊𝖆𝖙𝖍𝖊𝖗 𝖎𝖘 𝕾𝖍𝖎𝖋𝖙𝖎𝖓𝖌...", 
            color=color
        )
        await ctx.send(embed=embed)
        await asyncio.sleep(0.5)  


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

    # 1. LOAD ALL DATA FIRST
    global coin_data, player_data, market_view, markets, transactions
    coin_data_temp = await load_data('coin_data')
    player_data_temp = await load_data('player_data')
    markets = await load_data('markets')
    transactions = await load_data('transactions')

    # Update coin_data 
    for item in coin_data_temp:
        user_id = str(item['user_id'])
        coin_data[user_id] = item['coins']

    # Update player_data 
    for item in player_data_temp:
        user_id = str(item['user_id']) if item['user_id'] is not None else str(item['id'])
        player_data[user_id] = {
            'gun_durability': item['gun_durability'],
            'ammo': item['ammo'],
            'health': item.get('health', 100),
            'camp_durability': item.get('camp_durability'),
            'healing_potions': item.get('healing_potions')
        } 

    # 2. INITIALIZE ONLY MISSING PLAYERS
    for guild in bot.guilds:
        for member in guild.members:
            user_id = str(member.id)
            if user_id not in player_data:  # Check if player data exists
                await initialize_player_data(user_id)  

            if user_id not in coin_data:
                coin_data[user_id] = 0
                await save_data('coin_data', {'user_id': int(user_id), 'coins': 0})

    # Start your tasks 
    weather_manager.start()
    check_player_health.start()

    weather_end_time = asyncio.get_running_loop().time() + REGULAR_WEATHER_DURATION
    market_view = View(timeout=180) 

    print("Coin Data:", coin_data)
    print("Player Data:", player_data)
    print("Markets:", markets)
    print("Transactions:", transactions)




@bot.event
async def on_command_error(ctx, error):
    await ctx.send(f'An error occurred: {error}')


@bot.event
async def on_guild_available(guild):
    """Update coin_data and player_data when a guild becomes available."""
    global coin_data, player_data
    print(f"Guild available: {guild.name}")

    # Load coin_data 
    coin_data_temp = await load_data('coin_data')
    # Update coin_data 
    for item in coin_data_temp:
        user_id = str(item['user_id'])
        coin_data[user_id] = item['coins']

    # Load player_data
    player_data_temp = await load_data('player_data')
    # Update player_data
    for item in player_data_temp:
        user_id = str(item['user_id']) if item['user_id'] is not None else str(item['id'])
        player_data[user_id] = {}

        # Update existing player data or add new keys if needed
        player_data[user_id].update({
            'gun_durability': item['gun_durability'],
            'ammo': item['ammo'],
            'health': item.get('health', 100),
            'camp_durability': item.get('camp_durability', 100),
            'healing_potions': item.get('healing_potions', 1)
        })

@bot.event
async def on_member_join(member):
    user_id = str(member.id)
    # Initialize player data first
    await initialize_player_data(user_id) 
    # Then check and update coin_data
    existing_user = supabase.table('coin_data').select("*").eq('user_id', int(user_id)).execute()
    if not existing_user.data:
        await save_data('coin_data', {'user_id': int(user_id), 'coins': 0})
    # Give the new member a healing potion
    async with camp_users_lock:
        if user_id in player_data:
            player_data[user_id]["healing_potions"] += 1 
            await save_data('player_data', 
                            {'user_id': int(user_id), 'healing_potions': player_data[user_id]['healing_potions']}, 
                            upsert=True) 

@bot.command(name='stop')
async def stop_command(ctx):
    if ctx.author.id in AUTHORIZED_USERS:
        await ctx.send("Shutting down immediately!")
        await bot.logout()
    else:
        await ctx.send("You are not authorized to use this command.")

@bot.command(name='set_reminder_1')
async def set_reminder(ctx):
    global reminder_task

    # Delete the command message
    await ctx.message.delete()

    # Create an embed for the confirmation message
    embed = discord.Embed(
        title="Reminder Set!",
        description="Reminder has been set.",
        color=discord.Color.blue()
    )
    embed.set_footer(text="please remember this")

    # Send the embed as a confirmation message
    confirmation_msg = await ctx.send(embed=embed)

    async def send_saturday_reminder(user):
        while True:
            current_day = datetime.datetime.now().weekday()
            if current_day == 5:
                await user.send("<@1041613194382286878> please, im dying, get the coins in the web please")
                await asyncio.sleep(86400)  # Wait 24 hours before checking again
            await asyncio.sleep(3600)  # Wait 1 hour before checking again

    # Fetch the user and start the reminder loop
    user = await bot.fetch_user(1041613194382286878)
    reminder_task = bot.loop.create_task(send_saturday_reminder(user))

@bot.command(name='delete_reminder_1')
async def delete_reminder(ctx):
    global reminder_task

    # Delete the command message
    await ctx.message.delete()

    # Check if the reminder task is running
    if reminder_task and not reminder_task.cancelled():
        reminder_task.cancel()  # Cancel the reminder task
        reminder_task = None

        # Create an embed for the cancellation confirmation
        embed = discord.Embed(
            title="Reminder Cancelled",
            description="Your reminder is succeffully cancelled",
            color=discord.Color.red()
        )
        embed.set_footer(text="No more reminders will be sent.")

        # Send the embed as a confirmation message
        confirmation_msg = await ctx.send(embed=embed)
        await asyncio.sleep(5)
    else:
        # Create an embed if there was no reminder task to cancel
        embed = discord.Embed(
            title="No Active Reminder",
            description="There was no active reminder to cancel.",
            color=discord.Color.orange()
        )
        embed.set_footer(text="You may want to set a reminder first.")

        # Send the embed as a message
        no_task_msg = await ctx.send(embed=embed)



# --- Help Command ---
@bot.command(name='help')
async def help_command(ctx):
    embed = discord.Embed(
        title="Bot Commands",
        description="Here's a list of commands you can use:",
        color=discord.Color.gold()  # Choose your desired embed color
    )

    embed.add_field(
        name="**Common Commands**",
        value="`!ping` - Check the bot's responsiveness\n"
        "`!Help` - Show all user command\n"
        "`!Help_Admin` - Show all admin command",
        inline=False  # Start a new field on a separate line
    )

    embed.add_field(name="**Market Commands**",
                    value="`!create_market` - Create a new market listing\n"
                    "`!buy [market_id]` - Buy an item from the market\n"
                    "`!market [page]` - View market listings",
                    inline=False)

    embed.add_field(
        name="**Coins Commands**",
        value="`!pay [amount] [user]` - Pay coins to another user\n"
        "`!coins` - Check your coin balance\n"
        "`!top` - View the top 10 users with the most coins\n"
        "`!bottom` - View the bottom 10 users with the least coins",
        inline=False)
    embed.add_field(
        name="**Hunt Commands**",
        value=
        "`!hunt` - Gonna hunt a random mob whit a chance(like gambling ig\n"
        "`!inventory` - Check your shotgun durability and ammo\n"
        "`!shop` - A shop to buy a guj and ammo\n",
        inline=False)

    await ctx.send(embed=embed)

@bot.command(name='help_admin')
@commands.has_role(1227279982435500032)
async def help_admin_command(ctx):
    embed = discord.Embed(title="Admin Commands", color=discord.Color.red())
    
    embed.add_field(
        name="**Market Management**",
        value="`!delete_all_markets` - Delete all market listings\n"
              "`!delete_market [market_id]` - Delete a specific listing\n"
              "`!banish [user]` - Remove create market permission from a user\n"
              "`!unbanish [user]` - Grant create market permission to a user\n",
        inline=False
    )
    
    embed.add_field(
        name="**Coin Management**",
        value="`!give [user] [amount]` - Give coins to a user\n"
              "`!setcoin [amount] [user]` - Set a user's coin balance\n"
              "`!set_all_coins [amount]` - Set all users' coin balance\n",
        inline=False
    )
    
    embed.add_field(
        name="**Role Management**",
        value="`!promote [user]` - Give the user a mod role\n"
              "`!demote [user]` - Remove the mod role from a user\n"
              "`!add_rarity_role [rarity] [user]` - Add a rarity role to a user\n"
              "`!delete_rarity_role [rarity] [user]` - Remove a rarity role from a user\n",
        inline=False
    )
    
    embed.add_field(
        name="**Old Commands**",
        value="`!see_all_transactions` - View IDs of all transactions\n"
              "`!see_transaction [transaction_id]` - View transaction details\n",
        inline=False
    )
    
    embed.add_field(
        name="**Game Control**",
        value="`!edit_user [user]` - Edit user's gun durability and ammo amount\n"
              "`!bioweather [weather]` - Change the weather in the game\n",
        inline=False
    )
    
    await ctx.send(embed=embed)

@bot.command(name='help_owner')
async def help_owner_command(ctx):
    # Check if the user is authorized
    if ctx.author.id not in AUTHORIZED_USERS and ctx.author.id not in AUTHORIZED_MEMBER:
        await ctx.send("You are not authorized to use this command.")
        return

    # Command logic if the user is authorized
    embed = discord.Embed(title="Owner Commands", color=discord.Color.blue())
    embed.add_field(
        name="**Owner Commands**",
        value="`!delete_all_rarities [member]` - Remove all rarity roles from a specific member\n"
              "`!delete_all_rarities_all` - Remove all rarity roles from all members\n"
              "`!owoify [user]` - Change a user's nickname to an 'OwOified' version\n"
              "`!change_name [member]` - Change a user's nickname to a random word\n"
              "`!view_logs [page]` - View the admin logs with pagination\n"
              "`!force_pay [amount] [payer] [payee]` - Force a transaction between two users\n"
              "`!give_abmin [member]` - Assign or remove a role randomly with a chance to get nothing\n"
              "`!add_member [member]` - Add a member to the authorized members list\n"
              "`!remove_member [member]` - Remove a member from the authorized members list",
        inline=False
    )
    await ctx.send(embed=embed)
# --- Ping Command ---
@bot.command()
async def ping(ctx):
    await ctx.send('Pong!')


@tasks.loop(seconds=10)
async def send_ping():
    channel = bot.get_channel(
        1266431458277457962)  # Replace with the channel ID
    if channel:
        await channel.send('!ping')


@bot.command()
@in_allowed_channels()
async def I_CAST_PING(ctx):
    if not send_ping.is_running():
        send_ping.start()
        await ctx.send("Started sending `!ping` every 10 seconds.")
    else:
        await ctx.send("Already sending `!ping` every 10 seconds.")


@bot.command()
@in_allowed_channels()
async def stop_ping(ctx):
    if send_ping.is_running():
        send_ping.stop()
        await ctx.send("Stopped sending `!ping`.")
    else:
        await ctx.send("Not currently sending `!ping`.")


# Mob data
mobs = [("Aardvark", 10, 45.0, discord.Color.random()),
        ("Albatross", 10, 45.0, discord.Color.random()),
        ("Antelope", 10, 45.0, discord.Color.random()),
        ("Armadillo", 10, 45.0, discord.Color.random()),
        ("Baboon", 10, 45.0, discord.Color.random()),
        ("Badger", 10, 45.0, discord.Color.random()),
        ("Bat", 10, 45.0, discord.Color.random()),
        ("Bear", 10, 45.0, discord.Color.random()),
        ("Beaver", 20, 35.0, discord.Color.random()),
        ("Bison", 20, 35.0, discord.Color.random()),
        ("Bluejay", 20, 35.0, discord.Color.random()),
        ("Bobcat", 20, 35.0, discord.Color.random()),
        ("Buffalo", 20, 35.0, discord.Color.random()),
        ("Camel", 20, 35.0, discord.Color.random()),
        ("Capybara", 20, 35.0, discord.Color.random()),
        ("Caribou", 20, 35.0, discord.Color.random()),
        ("Cassowary", 35, 25.0, discord.Color.random()),
        ("Cat", 35, 25.0, discord.Color.random()),
        ("Cheetah", 35, 25.0, discord.Color.random()),
        ("Chicken", 35, 25.0, discord.Color.random()),
        ("Chimpanzee", 35, 25.0, discord.Color.random()),
        ("Chinchilla", 35, 25.0, discord.Color.random()),
        ("Cobra", 35, 25.0, discord.Color.random()),
        ("Cockatoo", 35, 25.0, discord.Color.random()),
        ("Condor", 45, 20.0, discord.Color.random()),
        ("Cougar", 45, 20.0, discord.Color.random()),
        ("Coyote", 45, 20.0, discord.Color.random()),
        ("Crane", 45, 20.0, discord.Color.random()),
        ("Crocodile", 45, 20.0, discord.Color.random()),
        ("fake 🪸", 45, 20.0, discord.Color.random()),
        ("brain damaged 🪸", 45, 20.0, discord.Color.random()),
        ("Crow", 45, 20.0, discord.Color.random()),
        ("Deer", 45, 20.0, discord.Color.random()),
        ("Dingo", 45, 20.0, discord.Color.random()),
        ("Dog", 65, 15.0, discord.Color.random()),
        ("Donkey", 65, 15.0, discord.Color.random()),
        ("Dove", 65, 15.0, discord.Color.random()),
        ("Duck", 65, 15.0, discord.Color.random()),
        ("Eagle", 65, 15.0, discord.Color.random()),
        ("Elephant", 65, 15.0, discord.Color.random()),
        ("Elk", 65, 15.0, discord.Color.random()),
        ("Falcon", 65, 15.0, discord.Color.random()),
        ("Ferret", 200, 10.0, discord.Color.random()),
        ("Flamingo", 200, 10.0, discord.Color.random()),
        ("Fox", 200, 10.0, discord.Color.random()),
        ("Frog", 200, 10.0, discord.Color.random()),
        ("Gazelle", 200, 10.0, discord.Color.random()),
        ("Giraffe", 200, 10.0, discord.Color.random()),
        ("Goat", 200, 10.0, discord.Color.random()),
        ("Goose", 200, 10.0, discord.Color.random()),
        ("Gorilla", 5000, 1.0, discord.Color.random()),
        ("Hedgehog", 5000, 1.0, discord.Color.random()),
        ("Hippopotamus", 5000, 1.0, discord.Color.random()),
        ("Horse", 5000, 1.0, discord.Color.random()),
        ("Hyena", 5000, 1.0, discord.Color.random()),
        ("Ibis", 5000, 1.0, discord.Color.random()),
        ("Iguana", 5000, 1.0, discord.Color.random()),
        ("Impala", 5000, 1.0, discord.Color.random()),
        ("Jackal", 50000, 0.06, discord.Color.random()),
        ("Jaguar", 50000, 0.06, discord.Color.random()),
        ("Kangaroo", 50000, 0.06, discord.Color.random()),
        ("Koala", 50000, 0.06, discord.Color.random()),
        ("Lemur", 50000, 0.06, discord.Color.random()),
        ("Leopard", 50000, 0.06, discord.Color.random()),
        ("Lion", 100000, 0.001, discord.Color.random()),
        ("Lizard", 100000, 0.001, discord.Color.random()),
        ("( •̀ ω •́ )✧", 1000000, 0.0001, discord.Color.random()),
        ("👋", 1000000, 0.0001, discord.Color.random()),
        ("Air Conditioner", 10000000, 0.0000001, discord.Color.random()),
        ("Fire.exe", 100000000, 0.000000000001, discord.Color.random()),
        ("4malware", 100000000, 0.000000000001, discord.Color.random()),
        ("🌝light", 100000000, 0.000000000001, discord.Color.random()),
        ("🦆", 1000000, 0.000000000001, discord.Color.random()),
        ("Nob x edition", 1000000, 0.000000000001, discord.Color.random()),
        ("🪸", 1000000, 0.000000000001, discord.Color.random()),
        ("EVIL 🪸 Not Actually", 1000000, 0.000000000001,
         discord.Color.random()),
        ("🪨🍜", 1000000, 0.000000000001, discord.Color.random())]
for mob in mobs:
    random.shuffle(mobs)

# --- Hunt Command ---
@bot.command(name='hunt')
@in_hunt_channel()
async def hunt_command(ctx):
    """Hunts for a mob, taking into account the current weather."""
    global coin_data, player_data, current_weather, storm_active, camp_users, current_sub_weather, storm_warning_active 
    user_id = str(ctx.author.id)
    channel = bot.get_channel(HUNT_CHANNEL_ID)
    # --- Call initialize_player_data before reloading ---
    await initialize_player_data(user_id) 
    admin_role_id = 1227279982435500032

    is_admin = any(role.id == admin_role_id for role in ctx.author.roles)
    coin_reward = 0

    # --- Check if a storm warning is active ---
    if user_id in storm_warned_users:  # Check if user was warned about the storm
        await ctx.reply("You can't hunt while a storm warning is active for you! Seek camp by using `!camp`")
        return

    # --- Early Check for Camping ---
    if user_id in camp_users:
        await ctx.reply("You can't hunt while you are in a camp!")
        return

    # Apply cooldown ONLY if not admin
    if not is_admin:
        retry_after = hunt_cooldown.get_bucket(ctx.message).update_rate_limit()
        if retry_after:
            await ctx.send(
                f"You're in cooldown! Try again in {int(retry_after)} seconds."
            )
            return

    # --- Access player data AFTER initialization --- 
    gun_durability = player_data[user_id]["gun_durability"]
    ammo_count = player_data[user_id]["ammo"]
    player_health = player_data[user_id]["health"]
    camp_durability = player_data[user_id]['camp_durability']

    # --- Check if ammo or gun durability is 0 ---
    if ammo_count <= 0:
        embed = discord.Embed(title="Out of Ammo!", color=discord.Color.red())
        embed.description = "Your gun is out of ammunition. Use the `!shop` command to buy ammo."
        await ctx.reply(embed=embed)
        return

    if gun_durability <= 0:
        embed = discord.Embed(title="Broken Gun!", color=discord.Color.red())
        embed.description = "Your gun is broken. Use the `!shop` command to buy a new one."
        await ctx.reply(embed=embed)
        return

    # --- Apply Weather Logic ---
    result_embed = None  # Store the result embed
    if current_weather != "Chaos":
        await apply_weather_logic(ctx, user_id, is_admin) 
    else:
        result_embed = await apply_sub_weather_logic(ctx, current_sub_weather, user_id, is_admin) 
    # --- Resource Deduction Logic (add this back) ---
    if player_data[user_id]["health"] > 0:
        if not (current_weather in ["Stormy", "Super Storm"] and user_id in camp_users):
            # Use subtract_with_infinity for gun durability and ammo 
            player_data[user_id]["gun_durability"] = subtract_with_infinity(player_data[user_id]["gun_durability"], 2) 
            player_data[user_id]["ammo"] = subtract_with_infinity(player_data[user_id]["ammo"], 3) 
        if user_id in camp_users:
            # Use subtract_with_infinity for camp durability 
            player_data[user_id]['camp_durability'] = subtract_with_infinity(player_data[user_id]['camp_durability'], 5) 

    # --- Save Player Data --- 
    await save_data('player_data', { 
        'user_id': int(user_id),
        'gun_durability': player_data[user_id]['gun_durability'],
        'ammo': player_data[user_id]['ammo'],
        'health': player_data[user_id]['health'],
        'camp_durability': player_data[user_id]['camp_durability'],
        'healing_potions': player_data[user_id]['healing_potions']
    }, upsert=True)

# --- Check Player Health Task ---
@tasks.loop(seconds=2)
async def check_player_health():
    global player_data, current_weather, camp_users
    channel = bot.get_channel(HUNT_CHANNEL_ID)

    for user_id, data in player_data.items():
        if data["health"] <= 0:
            user = user_cache.get(int(user_id))
            try:
                if user is None:
                    user = await bot.fetch_user(int(user_id))
                    user_cache[int(user_id)] = user

                await channel.send(f"{user.mention} You are out of health and have been defeated!")
                loss_embed = discord.Embed(title=f"{user.name} Defeat Losses", color=discord.Color.red())

                # Apply loss logic to each item using subtract_with_infinity
                for item in ["gun_durability", "ammo", "camp_durability", "healing_potions"]:
                    loss = data[item] // 2  # Calculate loss
                    data[item] -= subtract_with_infinity(data[item], loss)  # Subtract with infinity handling
                    loss_embed.add_field(
                        name=f"{item.replace('_', ' ').title()} Loss:",
                        value=f"-{handle_infinity(loss)}", 
                        inline=True
                    )

                data["health"] = 100
                await save_data('player_data', {
                    'user_id': int(user_id),
                    'gun_durability': data['gun_durability'],
                    'ammo': data['ammo'],
                    'health': data['health'],
                    'camp_durability': data['camp_durability'],
                    'healing_potions': data['healing_potions']
                }, upsert=True)

                await channel.send(embed=loss_embed)
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = float(e.response.headers.get("Retry-After", 1))
                    print(f"Rate limited, retrying in {retry_after} seconds.")
                    await asyncio.sleep(retry_after)
                else:
                    raise e

# --- Apply Weather and Sub-weather Logic ---
async def apply_weather_logic(ctx, user_id, is_admin, sub_weather=None):
    global coin_data, storm_warning_active, storm_warned_users 
    weather_name = sub_weather if sub_weather else current_weather 
    embed = discord.Embed(title=f"Hunt Results {WEATHER_EMOJIS[weather_name]}", color=random.choice(WEATHER_COLORS[weather_name]))
    if weather_name == "Sunny":
        num_mobs = random.choices([2, 3, 4], [43, 22, 15], k=1)[0]
        coin_reward = 0
        mobs_hunted = []
        for _ in range(num_mobs):
                    possible_mobs = [mob for mob in mobs if mob[1] >= 20]
                    mob = random.choices(possible_mobs, weights=[mob[2] for mob in possible_mobs], k=1)[0]
                    mob_name, reward, _, _ = mob
                    coin_reward += reward
                    mobs_hunted.append(mob_name)
        if random.random() <= 0.15:
            player_data[user_id]["health"] = subtract_with_infinity(player_data[user_id]["health"], 5) 
            embed.title = "You are exhausted!"
            embed.description = f"You were exhausted! You lost **5** health."
            embed.color = discord.Color.red()
        else: 
            if coin_data[user_id] < INFINITY_THRESHOLD: 
                coin_data[user_id] = coin_data.get(user_id, 0) + coin_reward
        embed.add_field(name=f"You hunted in Sunny weather:", value=f"You hunted {num_mobs} animals at the same time!", inline=False)
        embed.add_field(name="Mobs Hunted:", value=", ".join(mobs_hunted), inline=False)
        embed.add_field(name="Reward:", value=f"You earned **{coin_reward:,} coins**!", inline=False)
    elif weather_name == "Snowy":
        if blizzard_event.is_set():
            if random.random() <= 0.55:
                if random.random() <= 0.19:
                    player_data[user_id]["health"] = subtract_with_infinity(player_data[user_id]["health"], 20) 
                    embed.description = "You got too cold from the blizzard, and you took **20 damages** and couldn't hunt anything!"
                else:
                    num_mobs = random.choices([1, 2, 3, 4], [54, 43, 33, 21], k=1)[0]
                    coin_reward = 0
                    mobs_hunted = []
                    for _ in range(num_mobs):
                        possible_mobs = [mob for mob in mobs if mob[1] >= 200]
                        mob = random.choices(possible_mobs, weights=[mob[2] for mob in possible_mobs], k=1)[0]
                        mob_name, reward, _, _ = mob
                        coin_reward += reward
                        mobs_hunted.append(mob_name)
                    if coin_data[user_id] < INFINITY_THRESHOLD: 
                        coin_data[user_id] = coin_data.get(user_id, 0) + coin_reward
                    embed.add_field(name=f"You hunted in a Blizzard!:", value=f"You hunted {num_mobs} animals at the same time!", inline=False)
                    embed.add_field(name="Mobs Hunted:", value=", ".join(mobs_hunted), inline=False)
                    embed.add_field(name="Reward:", value=f"You earned **{coin_reward:,} coins**!", inline=False)
            else: 
                embed.description = "The blizzard's thick snow reduced visibility, and you couldn't hunt anything!"
        else:
            if random.random() <= 0.78: 
                num_mobs = random.choices([1, 2, 3], [55, 39, 25], k=1)[0]
                coin_reward = 0
                mobs_hunted = []
                for _ in range(num_mobs):
                    possible_mobs = [mob for mob in mobs if mob[1] >= 50]
                    mob = random.choices(possible_mobs, weights=[mob[2] for mob in possible_mobs], k=1)[0]
                    mob_name, reward, _, _ = mob
                    coin_reward += reward
                    mobs_hunted.append(mob_name)
                if coin_data[user_id] < INFINITY_THRESHOLD: 
                    coin_data[user_id] = coin_data.get(user_id, 0) + coin_reward 
                embed.add_field(name=f"You hunted in Snowy weather:", value=f"You hunted {num_mobs} animals at the same time!", inline=False)
                embed.add_field(name="Mobs Hunted:", value=", ".join(mobs_hunted), inline=False)
                embed.add_field(name="Reward:", value=f"You earned **{coin_reward:,} coins**!", inline=False)
            else: 
                embed.description = "The weather was too cold, and you couldn't hunt anything!"
    elif weather_name == "Rainy":
        num_mobs = random.choices([2, 3, 4, 5, 6, 7, 8, 9, 10], [64, 57, 52, 47, 43, 37, 33, 26, 15], k=1)[0]
        coin_reward = 0
        mobs_hunted = []
        for _ in range(num_mobs):
                    possible_mobs = [mob for mob in mobs if mob[1] >= 10]
                    mob = random.choices(possible_mobs, weights=[mob[2] for mob in possible_mobs], k=1)[0]
                    mob_name, reward, _, _ = mob
                    coin_reward += reward
                    mobs_hunted.append(mob_name)
        if coin_data[user_id] < INFINITY_THRESHOLD: 
            coin_data[user_id] = coin_data.get(user_id, 0) + coin_reward 
        embed.add_field(name=f"You hunted in Rainy weather: ", value=f"You hunted {num_mobs} animals at the same time! ", inline=False)
        embed.add_field(name="Mobs Hunted:", value=", ".join(mobs_hunted), inline=False)
        embed.add_field(name="Reward:", value=f"You earned **{coin_reward:,} coins**!", inline=False)
    elif weather_name in ["Stormy", "Super Storm"]:
        num_mobs = random.choices([(1, 43), (2, 30), (3, 10)], k=1)[0][0] if current_weather == "Stormy" else random.choices([(1, 54), (3, 22), (4, 15)], k=1)[0][0]
        coin_reward = 0
        mobs_hunted = []
        for _ in range(num_mobs): 
            possible_mobs = [mob for mob in mobs if mob[1] >= 50] if current_weather == "Stormy" else [mob for mob in mobs if mob[1] >= 400]
            mob = random.choices(possible_mobs, weights=[mob[2] for mob in possible_mobs], k=1)[0]
            mob_name, reward, _, _ = mob
            coin_reward += reward
            mobs_hunted.append(mob_name)
        if coin_data[user_id] < INFINITY_THRESHOLD: 
            coin_data[user_id] = coin_data.get(user_id, 0) + coin_reward 
        embed.add_field(name=f"You hunted in {current_weather} weather:", value=f"You hunted {num_mobs} animals at the same time!", inline=False)
        embed.add_field(name="Mobs Hunted:", value=", ".join(mobs_hunted), inline=False)
        embed.add_field(name="Reward:", value=f"You earned **{coin_reward:,} coins**!", inline=False)
        # --- Storm Damage ---
        storm_probability = 0.30 if current_weather == "Stormy" else 0.20
        if random.random() <= storm_probability:
            storm_warned_users[user_id] = asyncio.get_event_loop().time() 

            await ctx.reply(embed=discord.Embed(
                title="Storm Warning!",
                description=f"<@{user_id}>, a storm is approaching or in progress! Seek shelter using `!camp` or risk taking damage!",
                color=discord.Color.magenta()
            ))
            await asyncio.sleep(STORM_WARNING_DURATION)
        if user_id in storm_warned_users:
            async with camp_users_lock:
                if user_id not in camp_users:
                    player_data[user_id]["health"] = subtract_with_infinity(player_data[user_id]["health"], STORM_DAMAGE[current_weather]) 
                    await ctx.reply(embed=discord.Embed(title="Caught in the Storm!", description=f"<@{user_id}> You took {STORM_DAMAGE[current_weather]} damage from the {current_weather}!", color=discord.Color.red()))
                    del storm_warned_users[user_id]
                    await ctx.send(embed=discord.Embed(title="Weather Update", description=f"<@{user_id}>, the storm has passed!", color=discord.Color.gold()))                    
                    return  
                else:  # Player is in camp
                    damage_taken = CAMP_DEGRADATION[current_weather]
                    player_data[user_id]['camp_durability'] -= damage_taken
                    if player_data[user_id]['camp_durability'] <= 0:
                        # Apply remaining damage to player's health 
                        remaining_damage = damage_taken 
                        player_data[user_id]['health'] = subtract_with_infinity(player_data[user_id]['health'], remaining_damage) 

                        await ctx.reply(embed=discord.Embed(
                            title="Camp Destroyed!", 
                            description=
                                f"<@{user_id}> Your camp has been destroyed by the storm! "
                                f"You also took **{remaining_damage}** damage! "
                                f"Buy camp at the `!shop` or you will be in danger.",
                            color=discord.Color.red()
                        ))
                        del camp_users[user_id] 
                        del storm_warned_users[user_id]
                        await ctx.send(embed=discord.Embed(title="Weather Update", description=f"<@{user_id}>, the storm has passed!", color=discord.Color.gold()))                    
                        return  
                    else:
                        await save_data("player_data", {
                            'user_id': int(user_id),
                            'gun_durability': player_data[user_id]['gun_durability'],
                            'ammo': player_data[user_id]['ammo'],
                            'health': player_data[user_id]['health'],
                            'camp_durability': player_data[user_id]['camp_durability']
                        }, upsert=True)
                        storm_damage_embed = discord.Embed(
                            title="Storm Damage!", 
                            description=f"Your camp took **{damage_taken}** durability damage from the storm!", 
                            color=discord.Color.dark_gray()
                        )
                        storm_damage_embed.add_field(name="Camp Durability:", value=handle_infinity(player_data[user_id]['camp_durability']), inline=False)
                        await ctx.reply(embed=storm_damage_embed) 
                        del storm_warned_users[user_id]
                        await ctx.send(embed=discord.Embed(title="Weather Update", description=f"<@{user_id}>, the storm has passed!", color=discord.Color.gold()))                    
                        return  

    await save_data('coin_data', {'user_id': int(user_id), 'coins': coin_data[user_id]}, upsert=True)
    embed.add_field(name="❤️ Health:", value=handle_infinity(player_data[user_id]["health"]), inline=True)  
    embed.add_field(name="<:shotgun:1267441675639459964> Durability:", value=handle_infinity(player_data[user_id]["gun_durability"]), inline=True) 
    embed.add_field(name="<:ammo:1267441870519144518> Ammo:", value=handle_infinity(player_data[user_id]["ammo"]), inline=True) 
    embed.set_footer(text="WARNING The data is just a reference, the error can be from 2 to 3 compared to normal. For more accuracy, use the `!inventory` command.")
    await ctx.reply(embed=embed)

async def apply_sub_weather_logic(ctx, sub_weather, user_id, is_admin):
    global coin_data, storm_warning_active, storm_warned_users 
    embed = discord.Embed(title=f" **₵Ⱨ₳Ø₴** Results **₵Ⱨ₳Ø₴** ", color=random.choice(WEATHER_COLORS[sub_weather]))
    if sub_weather == "Sunny":
        # Sunny weather logic
        num_mobs = random.choices([2, 3, 4], [43, 22, 15], k=1)[0]
        coin_reward = 0
        mobs_hunted = []
        for _ in range(num_mobs):
                    possible_mobs = [mob for mob in mobs if mob[1] >= 500]
                    mob = random.choices(possible_mobs, weights=[mob[2] for mob in possible_mobs], k=1)[0]
                    mob_name, reward, _, _ = mob
                    coin_reward += reward
                    mobs_hunted.append(mob_name)
        coin_reward *= 1 
        if random.random() <= 0.15:
            player_data[user_id]["health"] = subtract_with_infinity(player_data[user_id]["health"], 5) 
            embed.title = "ɎØɄ ₳ⱤɆ ɆӾⱧ₳Ʉ₴₮ɆĐ!"
            embed.description = f"ɎØɄ ₩ɆⱤɆ ɆӾⱧ₳Ʉ₴₮ɆĐ! ɎØɄ ⱠØ₴₮ **5** ⱧɆ₳Ⱡ₮Ⱨ."
            embed.color = discord.Color.red()
        else:
            if coin_data[user_id] < INFINITY_THRESHOLD: 
                coin_data[user_id] = coin_data.get(user_id, 0) + coin_reward
        embed.add_field(name=f"ɎØɄ ⱧɄ₦₮ɆĐ ł₦ ₴Ʉ₦₦Ɏ ₵Ⱨ₳Ø₴ :", value=f"ɎØɄ ⱧɄ₦₮ɆĐ {num_mobs} ₳₦ł₥₳Ⱡ₴ ₳₮ ₮ⱧɆ ₴₳₥Ɇ ₮ł₥Ɇ!", inline=False)
        embed.add_field(name="₥Ø฿₴ ⱧɄ₦₮ɆĐ:", value=", ".join(mobs_hunted), inline=False)
        embed.add_field(name="ⱤɆ₩₳ⱤĐ:", value=f"ɎØɄ Ɇ₳Ɽ₦ɆĐ **{coin_reward:,} ₵Øł₦₴**! ", inline=False)

    elif sub_weather == "Snowy":
        # Snowy weather logic
        if blizzard_event.is_set():
            if random.random() <= 0.55:
                if random.random() <= 0.25:
                    player_data[user_id]["health"] = subtract_with_infinity(player_data[user_id]["health"], 40) 
                    embed.description = "ɎØɄ ₲Ø₮ ₮ØØ ₵ØⱠĐ ₣ⱤØ₥ ₮ⱧɆ ฿ⱠłⱫⱫ₳ⱤĐ, ₳₦Đ ɎØɄ ₮ØØ₭ **𝟰𝟬 Đ₳₥₳₲Ɇ₴** ₳₦Đ ₵ØɄⱠĐ₦'₮ ⱧɄ₦₮ ₳₦Ɏ₮Ⱨł₦₲!"
                else:
                    num_mobs = random.choices([1, 2, 3, 4], [54, 43, 33, 21], k=1)[0]
                    coin_reward = 0
                    mobs_hunted = []
                    for _ in range(num_mobs):
                        possible_mobs = [mob for mob in mobs if mob[1] >= 1500]
                        mob = random.choices(possible_mobs, weights=[mob[2] for mob in possible_mobs], k=1)[0]
                        mob_name, reward, _, _ = mob
                        coin_reward += reward
                        mobs_hunted.append(mob_name)
                    if coin_data[user_id] < INFINITY_THRESHOLD: 
                        coin_data[user_id] = coin_data.get(user_id, 0) + coin_reward
                    embed.add_field(name=f"ɎØɄ ⱧɄ₦₮ɆĐ ł₦ ₳ ₵Ⱨ₳Ø₴ ฿ⱠłⱫⱫ₳ⱤĐ! :", value=f"ɎØɄ ⱧɄ₦₮ɆĐ {num_mobs} ₳₦ł₥₳Ⱡ₴ ₳₮ ₮ⱧɆ ₴₳₥Ɇ ₮ł₥Ɇ!", inline=False)
                    embed.add_field(name="₥Ø฿₴ ⱧɄ₦₮ɆĐ:", value=", ".join(mobs_hunted), inline=False)
                    embed.add_field(name="ⱤɆ₩₳ⱤĐ:", value=f"ɎØɄ Ɇ₳Ɽ₦ɆĐ **{coin_reward:,} ₵Øł₦₴**!", inline=False)
            else: 
                embed.description = "₮ⱧɆ ฿ⱠłⱫⱫ₳ⱤĐ'₴ ₮Ⱨł₵₭ ₴₦Ø₩ ⱤɆĐɄ₵ɆĐ Vł₴ł฿łⱠł₮Ɏ, ₳₦Đ ɎØɄ ₵ØɄⱠĐ₦'₮ ⱧɄ₦₮ ₳₦Ɏ₮Ⱨł₦₲!"
        else: 
            if random.random() <= 0.50:    
                num_mobs = random.choices([1, 2, 3], [55, 39, 25], k=1)[0]
                coin_reward = 0
                mobs_hunted = []
                for _ in range(num_mobs):
                    possible_mobs = [mob for mob in mobs if mob[1] >= 500]
                    mob = random.choices(possible_mobs, weights=[mob[2] for mob in possible_mobs], k=1)[0]
                    mob_name, reward, _, _ = mob
                    coin_reward += reward
                    mobs_hunted.append(mob_name)
                if coin_data[user_id] < INFINITY_THRESHOLD: 
                    coin_data[user_id] = coin_data.get(user_id, 0) + coin_reward
                embed.add_field(name=f"ɎØɄ ⱧɄ₦₮ɆĐ ł₦ ₵Ⱨ₳Ø₴ ₴₦Ø₩Ɏ :", value=f"ɎØɄ ⱧɄ₦₮ɆĐ {num_mobs} ₳₦ł₥₳Ⱡ₴ ₳₮ ₮ⱧɆ ₴₳₥Ɇ ₮ł₥Ɇ!", inline=False)
                embed.add_field(name="₥Ø฿₴ ⱧɄ₦₮ɆĐ:", value=", ".join(mobs_hunted), inline=False)
                embed.add_field(name="ⱤɆ₩₳ⱤĐ:", value=f"ɎØɄ Ɇ₳Ɽ₦ɆĐ **{coin_reward:,} ₵Øł₦₴**!", inline=False)
            else: 
                embed.description = "₮ⱧɆ ₩Ɇ₳₮ⱧɆⱤ ₩₳₴ ₮ØØ ₵ØⱠĐ, ₳₦Đ ɎØɄ ₵ØɄⱠĐ₦'₮ ⱧɄ₦₮ ₳₦Ɏ₮Ⱨł₦₲!"

    elif sub_weather == "Rainy":
        # Rainy weather logic
        num_mobs = random.choices([1, 2, 4, 5, 6, 7, 8, 9, 10], [64, 57, 52, 47, 43, 37, 33, 26, 15], k=1)[0]
        coin_reward = 0
        mobs_hunted = []
        for _ in range(num_mobs):
                    possible_mobs = [mob for mob in mobs if mob[1] >= 500]
                    mob = random.choices(possible_mobs, weights=[mob[2] for mob in possible_mobs], k=1)[0]
                    mob_name, reward, _, _ = mob
                    coin_reward += reward
                    mobs_hunted.append(mob_name)
        if coin_data[user_id] < INFINITY_THRESHOLD: 
            coin_data[user_id] = coin_data.get(user_id, 0) + coin_reward
        embed.add_field(name=f"ɎØɄ ⱧɄ₦₮ɆĐ ł₦ ₵Ⱨ₳Ø₴ Ɽ₳ł₦Ɏ :", value=f"ɎØɄ ⱧɄ₦₮ɆĐ {num_mobs} ₳₦ł₥₳Ⱡ₴ ₳₮ ₮ⱧɆ ₴₳₥Ɇ ₮ł₥Ɇ!", inline=False)
        embed.add_field(name="₥Ø฿₴ ⱧɄ₦₮ɆĐ:", value=", ".join(mobs_hunted), inline=False)
        embed.add_field(name="ⱤɆ₩₳ⱤĐ:", value=f"ɎØɄ Ɇ₳Ɽ₦ɆĐ **{coin_reward:,} ₵Øł₦₴**!", inline=False)

    if sub_weather in ["Stormy", "Super Storm"]: 
        num_mobs = random.choices([(1, 43), (2, 30), (3, 10)], k=1)[0][0] if sub_weather == "Stormy" else random.choices([(1, 54), (3, 22), (4, 15)], k=1)[0][0]
        coin_reward = 0
        mobs_hunted = []
        for _ in range(num_mobs):
            possible_mobs = [mob for mob in mobs if mob[1] >= 2000] if sub_weather == "Stormy" else [mob for mob in mobs if mob[1] >= 8000] 
            mob = random.choices(possible_mobs, weights=[mob[2] for mob in possible_mobs], k=1)[0]
            mob_name, reward, _, _ = mob
            coin_reward += reward
            mobs_hunted.append(mob_name)
        if coin_data[user_id] < INFINITY_THRESHOLD: 
            coin_data[user_id] = coin_data.get(user_id, 0) + coin_reward
        embed.add_field(name=f"ɎØɄ ⱧɄ₦₮ɆĐ ł₦ ₵Ⱨ₳Ø₴ {sub_weather.upper()} :", 
                        value=f"ɎØɄ ⱧɄ₦₮ɆĐ {num_mobs} ₳₦ł₥₳Ⱡ₴ ₳₮ ₮ⱧɆ ₴₳₥Ɇ ₮ł₥Ɇ!", inline=False)
        embed.add_field(name="₥Ø฿₴ ⱧɄ₦₮ɆĐ:", value=", ".join(mobs_hunted), inline=False)
        embed.add_field(name="ⱤɆ₩₳ⱤĐ:", value=f"ɎØɄ Ɇ₳Ɽ₦ɆĐ **{coin_reward:,} ₵Øł₦₴**! ", inline=False)
        
        
        storm_probability = 0.40 if sub_weather == "Stormy" else 0.50
        if random.random() <= storm_probability:
            async with camp_users_lock:
                storm_warned_users[user_id] = asyncio.get_event_loop().time()

            await ctx.reply(embed=discord.Embed(
                title=f" ₵Ⱨ₳Ø₴ {sub_weather.upper()} ₩₳Ɽ₦ł₦₲!",
                description=f"<@{user_id}>, ₳ ₵Ⱨ₳Ø₴ {sub_weather.upper()}  ł₴ Ɽ₳₲ł₦₲! ₴ɆɆ₭ ₴ⱧɆⱠ₮ɆⱤ Ʉ₴ł₦₲ `!camp` ØⱤ Ɽł₴₭ ₮₳₭ł₦₲ Đ₳₥₳₲Ɇ!",
                color=discord.Color.magenta()
            ))
        # --- Apply Storm Damage during Chaos --- 
            async def storm_timeout():
                await asyncio.sleep(STORM_WARNING_DURATION_CHAOS + 5)
                try:
                    async with camp_users_lock:
                        if user_id in storm_warned_users:
                            if user_id not in camp_users:
                                # Apply damage logic
                                player_data[user_id]["health"] = subtract_with_infinity(player_data[user_id]["health"], STORM_DAMAGE_CHAOS[sub_weather])
                                await ctx.reply(embed=discord.Embed(
                                    title=f"₵₳Ʉ₲Ⱨ₮ ł₦ ₮ⱧɆ ₵Ⱨ₳Ø₴ {sub_weather.upper()}!",
                                    description=f"<@{user_id}> ɎØɄ ₮ØØ₭ {STORM_DAMAGE_CHAOS[sub_weather]} Đ₳₥₳₲Ɇ ₣ⱤØ₥ ₮ⱧɆ {sub_weather.upper()}!",
                                    color=discord.Color.dark_gray()
                                ))
                                del storm_warned_users[user_id] 
                                return
                            else:  # Player is in camp
                                # Apply camp logic
                                damage_taken = CAMP_DEGRADATION_CHAOS[sub_weather]
                                player_data[user_id]['camp_durability'] -= damage_taken
                                if player_data[user_id]['camp_durability'] <= 0:
                                    # Camp destroyed 
                                    remaining_damage = damage_taken 
                                    player_data[user_id]['health'] = subtract_with_infinity(player_data[user_id]['health'], remaining_damage)
                                    await ctx.reply(embed=discord.Embed(
                                        title="₵₳₥₱ ĐɆ₴₮ⱤØɎɆĐ! ",
                                        description=f"<@{user_id}> ɎØɄⱤ ₵₳₥₱ Ⱨ₳₴ ฿ɆɆ₦ ĐɆ₴₮ⱤØɎɆĐ ฿Ɏ ₮ⱧɆ ₵Ⱨ₳Ø₴ {sub_weather.upper()}! You also took **{remaining_damage}** damage!",
                                        color=discord.Color.red()
                                    ))
                                    del camp_users[user_id]
                                    del storm_warned_users[user_id]
                                    return
                                else:
                                    await save_data("player_data", {
                                        'user_id': int(user_id),
                                        'gun_durability': player_data[user_id]['gun_durability'],
                                        'ammo': player_data[user_id]['ammo'],
                                        'health': player_data[user_id]['health'],
                                        'camp_durability': player_data[user_id]['camp_durability']
                                    }, upsert=True)
                                    storm_damage_embed = discord.Embed(
                                        title=f"₵Ⱨ₳Ø₴ {sub_weather.upper()} Đ₳₥₳₲Ɇ!",
                                        description=f"ɎØɄⱤ ₵₳₥₱ ₮ØØ₭ **{damage_taken}** ĐɄⱤ₳฿łⱠł₮Ɏ Đ₳₥₳₲Ɇ ₣ⱤØ₥ ₮ⱧɆ {sub_weather.upper()}!",
                                        color=discord.Color.dark_gray()
                                    )
                                    storm_damage_embed.add_field(name="Camp Durability:", value=handle_infinity(player_data[user_id]['camp_durability']), inline=False)
                                    del storm_warned_users[user_id]
                                    await ctx.reply(embed=storm_damage_embed)
                                    return
                except Exception as e:
                    print(f"Error applying storm damage: {e}")
                    await ctx.reply(f"An error occurred while applying storm damage. Please contact an admin.")
                finally:
                    async with camp_users_lock:
                        # Weather update message moved inside finally block
                        await ctx.send(embed=discord.Embed(title="₩Ɇ₳₮ⱧɆⱤ Ʉ₱Đ₳₮Ɇ", description=f"<@{user_id}>, ₮ⱧɆ ₵Ⱨ₳Ø₴ {sub_weather.upper()} Ⱨ₳₴ ₱₳₴₴ɆĐ!", color=discord.Color.gold()))
                return

            await storm_timeout()

    await save_data('coin_data', {'user_id': int(user_id), 'coins': coin_data[user_id]}, upsert=True)
    await save_data('player_data', { 
        'user_id': int(user_id),                                                                                                                                                                                                                                                                                                                                                            
        'gun_durability': player_data[user_id]['gun_durability'],
        'ammo': player_data[user_id]['ammo'],
        'health': player_data[user_id]['health'],
        'camp_durability': player_data[user_id]['camp_durability'],
        'healing_potions': player_data[user_id]['healing_potions']
    }, upsert=True)

    # Add Player Stats to Embed for Hunt Results
    embed.add_field(name="❤️ Health:", value=handle_infinity(player_data[user_id]["health"]), inline=True)  
    embed.add_field(name="<:shotgun:1267441675639459964> Durability:", value=handle_infinity(player_data[user_id]["gun_durability"]), inline=True) 
    embed.add_field(name="<:ammo:1267441870519144518> Ammo:", value=handle_infinity(player_data[user_id]["ammo"]), inline=True)  
    embed.set_footer(text="WARNING The data is just a reference, the error can be from 2 to 3 compared to normal. For more accuracy, use the `!inventory` command.")
    await ctx.reply(embed=embed)
    return embed

#-- CAMP --
@bot.command(name='camp')
@in_hunt_channel()
async def camp_command(ctx):
    global camp_users, player_data, current_weather, current_sub_weather
    user_id = str(ctx.author.id)
    await initialize_player_data(user_id)

    async with camp_users_lock:
        if (current_weather == "Chaos" and current_sub_weather in ["Stormy", "Super Storm"]) or \
           (current_weather in ["Stormy", "Super Storm"] and current_weather != "Chaos"):
            if user_id in camp_users:
                await ctx.reply("You are already in a camp.")
                return

            # --- Check for Minimum Durability and Warn ---
            required_durability = 40 if current_weather == "Stormy" else 70 
            if current_weather == "Chaos":
                required_durability = 80 if current_sub_weather == "Stormy" else 200  

            if player_data[user_id]['camp_durability'] < required_durability:
                await ctx.reply(
                    f"Your camp is too damaged to fully withstand this "
                    f"{'₵Ⱨ₳Ø₴ ' if current_weather == 'Chaos' else ''}{current_sub_weather if current_weather == 'Chaos' else current_weather}! "
                    f"You need at least {required_durability} durability. "
                    f"It may be destroyed."
                )

            # --- Set Up Camp Regardless ---
            camp_users[user_id] = asyncio.get_event_loop().time()

            embed = discord.Embed(title="🏕️ Camp Setup", color=discord.Color.green())
            embed.description = "You set up camp. If you want to leave, use `!uncamp`."
            embed.add_field(
                name="Camp Durability:",
                value=handle_infinity(player_data[user_id]['camp_durability']),
                inline=False
            )
            await ctx.reply(embed=embed)
        else:
            await ctx.reply(
                "You can only set up camp during a storm or chaos storm."
            )
            return

# --- Uncamp Command ---
@bot.command(name='uncamp')
@in_hunt_channel()
async def uncamp_command(ctx):
    global camp_users
    user_id = str(ctx.author.id)
    async with camp_users_lock:  
        if user_id in camp_users:
            del camp_users[user_id]
            await ctx.reply("You left your camp.")
        else:
            await ctx.reply("You are not currently in a camp.")

# --- Shop Command ---
@bot.command(name='shop')
@in_hunt_or_allowed_channels() 
async def shop_command(ctx):
    """Shows the shop's current items."""
    global player_data

    async def buy_item(interaction, item_name):
        global coin_data, player_data
        user_id = str(interaction.user.id)
        item = shop_items[item_name]
        cost_per_item = item['price']

        modal = Modal(title=f"Buy {item_name}")
        quantity_input = TextInput(
            label="Quantity",
            placeholder=f"Enter the number of {item_name} you want to buy.",
            style=discord.TextStyle.short,
            required=True
        )
        modal.add_item(quantity_input)

        async def modal_submit(interaction: discord.Interaction):
            global player_data
            try:
                quantity = int(quantity_input.value)
                if quantity <= 0:
                    await interaction.response.send_message(
                        "Invalid quantity. Must be a positive number.",
                        ephemeral=True
                    )
                    return
                total_cost = cost_per_item * quantity

                if coin_data.get(user_id, 0) < total_cost and coin_data.get(user_id, 0) < INFINITY_THRESHOLD:
                    await interaction.response.send_message(
                    "You don't have enough coins!", ephemeral=True
                    )
                    return
    
                coin_data[user_id] -= total_cost 
                await save_data(
                    'coin_data',
                    {'user_id': int(user_id), 'coins': coin_data[user_id]},
                    upsert=True
                )

                if user_id not in player_data:
                    player_data[user_id] = {
                        "gun_durability": 30,
                        "ammo": 30,
                        "health": 100,
                        "camp_durability": 100, 
                        "healing_potions": 0
                    }

                if item_name == "ShotGun":
                    player_data[user_id]["gun_durability"] = add_with_infinity(player_data[user_id]["gun_durability"], 10 * quantity) 
                elif item_name == "A box of Ammo":
                    player_data[user_id]["ammo"] = add_with_infinity(player_data[user_id]["ammo"], 5 * quantity) 
                elif item_name == "Camp":
                    if 'camp_durability' not in player_data[user_id]:
                        player_data[user_id]['camp_durability'] = 0
                    player_data[user_id]['camp_durability'] = add_with_infinity(player_data[user_id]['camp_durability'], 10 * quantity)
                elif item_name == "Healing Potion":
                    player_data[user_id]["healing_potions"] = add_with_infinity(player_data[user_id]["healing_potions"], quantity)

                await save_data(
                    'player_data',
                    {
                        'user_id': int(user_id),
                        'gun_durability': player_data[user_id]['gun_durability'],
                        'ammo': player_data[user_id]['ammo'],
                        'health': player_data[user_id]['health'],
                        'camp_durability': player_data[user_id]['camp_durability'],
                        'healing_potions': player_data[user_id]['healing_potions'] 
                    },
                    upsert=True
                )

                await interaction.response.send_message(
                    f"You bought {quantity} x {item_name} for {total_cost} coins!",
                    ephemeral=True
                )

            except ValueError:
                await interaction.response.send_message(
                    "Invalid input. Please enter a number.", ephemeral=True
                )

        modal.on_submit = modal_submit
        await interaction.response.send_modal(modal)
    # --- Create Buttons ---
    gun_button = Button(label="Buy ShotGun (20 coins)",
                        style=discord.ButtonStyle.primary,
                        custom_id="buy_gun")
    gun_button.callback = lambda interaction: buy_item(interaction, "ShotGun")

    ammo_button = Button(label="Buy A box of Ammo (10 coins)",
                         style=discord.ButtonStyle.primary,
                         custom_id="buy_ammo")
    ammo_button.callback = lambda interaction: buy_item(interaction, "A box of Ammo")
    camp_button = Button(
        label="Buy Camp (50 coins)",
        style=discord.ButtonStyle.primary,
        custom_id="buy_camp",
    )
    camp_button.callback = lambda interaction: buy_item(interaction, "Camp")
    potion_button = Button(
        label="Buy Healing Potion (50 coins)",
        style=discord.ButtonStyle.primary,
        custom_id="buy_potion"
    )
    potion_button.callback = lambda interaction: buy_item(interaction, "Healing Potion")

    view = View(timeout=200)
    view.add_item(gun_button)
    view.add_item(ammo_button)
    view.add_item(camp_button)
    view.add_item(potion_button) 

    embed = discord.Embed(title="Shop", color=discord.Color.green())
    shop_items = {
        "ShotGun": { 
            "emoji": "<:shotgun:1267441675639459964>",
            "description": "A Shotgun(10 Durability)",
            "price": 20
        },
        "A box of Ammo": { 
            "emoji": "<:ammo:1267441870519144518>",
            "description": "Ammunition(5 Ammos)",
            "price": 10 
        }, 
        "Camp": { 
            "emoji": "🏕️",
            "description": "A sturdy camp to weather the storms.(10 Durability)",
            "price": 50
        },
        "Healing Potion": { 
            "emoji": "🧪",
            "description": "A bottle of healing potion(1 Healing Potion)",
            "price": 50
        }
    }

    for item_name, item_data in shop_items.items():
        embed.add_field(
            name=f"{item_data['emoji']} {item_data['description']}",
            value=f"{item_data['description']}\n**Price:** {item_data['price']} coins",
            inline=False
        )

    await ctx.reply(embed=embed, view=view)

# --- Stats Command ---
@bot.command(name='stats', aliases=['profile', 'inventory', 'coin', 'inv'])
@in_hunt_or_allowed_channels() 
async def stats_command(ctx, target_user: discord.Member = None):
    """Displays the player's stats: coins, inventory, health, and a potion button."""
    global coin_data, player_data, stats_messages # Access the global dictionary
    user = target_user or ctx.author
    user_id = user.id  # Use user.id to get an integer ID
    await initialize_player_data(str(user_id)) 

    # --- Create Embed ---
    embed = discord.Embed(title=f"{user.name}'s Stats", color=discord.Color.gold())
    embed.set_thumbnail(url=user.avatar.url)

    # --- Wealth ---
    embed.add_field(name="**🪙 Wealth:**", value=f"{handle_infinity(coin_data.get(str(user_id), 0))} 🪙", inline=True) 

    # --- Health (Square Loading Bar Style - 10 blocks, 1 block = 10 health) ---
    health = player_data[str(user_id)]["health"] # Use str(user_id) here
    if health >= INFINITY_THRESHOLD:
        health_bar = "🟥" * 10 
        health_display = "∞/∞"
    else:
        health_percentage = int(health // 10)  # 1 block = 10 health
        health_bar = "🟥" * health_percentage + "⬛" * (10 - health_percentage)
        health_display = f"{health}/100"
    embed.add_field(name="**❤️ Health:**", value=f"{health_bar} {health_display}", inline=True)

    # --- Inventory ---
    inventory_str = (
        f"**<:shotgun:1267441675639459964> Shotgun Durability:** {handle_infinity(player_data[str(user_id)]['gun_durability'])}\n" # str(user_id) here
        f"**<:ammo:1267441870519144518> Ammo:** {handle_infinity(player_data[str(user_id)]['ammo'])}\n" # str(user_id) here
        f"**🏕️ Camp Durability:** {handle_infinity(player_data[str(user_id)]['camp_durability'])}\n" # str(user_id) here
        f"**🧪 Healing Potions:** {handle_infinity(player_data[str(user_id)]['healing_potions'])}" # str(user_id) here
    )
    embed.add_field(name="**🎒Inventory:**", value=inventory_str, inline=False)

    # --- Use Potion Button ---
    async def use_potion_callback(interaction):
        nonlocal user_id, embed, message

        await interaction.response.defer()  

        # --- Check if the interaction user is the owner of the stats message ---
        if str(interaction.user.id) != str(user_id):
            await interaction.response.send_message("This potion is not for you!", ephemeral=True)
            await interaction.response.defer()
            return

        async with camp_users_lock:
            if player_data[str(user_id)]['healing_potions'] > 0 and player_data[str(user_id)]['health'] < 100:
                player_data[str(user_id)]['health'] = min(player_data[str(user_id)]['health'] + 5, 100)
                player_data[str(user_id)]['healing_potions'] -= 1

                # Update health bar 
                health = player_data[str(user_id)]['health']
                health_percentage = int(health // 10)
                health_bar = "🟥" * health_percentage + "⬛" * (10 - health_percentage)
                health_display = f"{health}/100"
                embed.set_field_at(1, name="**❤️ Health:**", value=f"{health_bar} {health_display}", inline=True)

                # Update inventory string (including healing potions)
                inventory_str = (
                    f"**<:shotgun:1267441675639459964> Shotgun Durability:** {handle_infinity(player_data[str(user_id)]['gun_durability'])}\n"
                    f"**<:ammo:1267441870519144518> Ammo:** {handle_infinity(player_data[str(user_id)]['ammo'])}\n"
                    f"**🏕️ Camp Durability:** {handle_infinity(player_data[str(user_id)]['camp_durability'])}\n"
                    f"**🧪 Healing Potions:** {handle_infinity(player_data[str(user_id)]['healing_potions'])}"
                )
                embed.set_field_at(2, name="**🎒Inventory:**", value=inventory_str, inline=False) 

                await save_data('player_data', {
                    'user_id': int(user_id),
                    'gun_durability': player_data[str(user_id)]['gun_durability'],
                    'ammo': player_data[str(user_id)]['ammo'],
                    'health': player_data[str(user_id)]['health'],
                    'camp_durability': player_data[str(user_id)]['camp_durability'],
                    'healing_potions': player_data[str(user_id)]['healing_potions']
                }, upsert=True)

                await message.edit(embed=embed, view=view) 
            else:
                message_text = "You are already at full health!" if player_data[str(user_id)]['health'] >= 100 else "You have no healing potions!"
                await interaction.response.defer()
                await interaction.response.send_message(message_text, ephemeral=True)

    use_potion_button = Button(label="Use Potion", style=discord.ButtonStyle.red)
    use_potion_button.callback = use_potion_callback
    view = View(timeout=300)
    view.add_item(use_potion_button)

    message = await ctx.reply(embed=embed, view=view) 
    stats_messages[user_id] = message  

@bot.command(name='create_market')
@in_allowed_channels()
@check_no_role(1266352717572603967)  # Replace with actual restricted role ID
async def create_market_command(ctx):
    """Initiates the market creation process with a modal."""
    # --- Limit Market Listings Per User ---
    user_id = str(ctx.author.id)
    user_listings = sum(1 for market in markets if market['seller'] == user_id)

    # --- Check if the user has reached the limit or is admin ---
    if user_listings >= 2 and not any(role.id == ADMIN_ROLE_ID
                                      for role in ctx.author.roles):
        await ctx.send(
            "You have reached the maximum number of active market listings (2). Please delete an existing listing."
        )
        return

    class MarketCreationModal(Modal, title="Create a Market Listing"):

        def __init__(self):
            super().__init__()
            self.add_item(
                TextInput(label="Name",
                          placeholder="Enter service name...",
                          style=discord.TextStyle.short,
                          required=True,
                          max_length=50))
            self.add_item(
                TextInput(label="Description",
                          placeholder="Enter a detailed description...",
                          style=discord.TextStyle.long,
                          required=True,
                          max_length=200))
            self.add_item(
                TextInput(label="Cost",
                          placeholder="Enter cost in coins...",
                          style=discord.TextStyle.short,
                          required=True,
                          max_length=10))

        async def on_submit(self, interaction: discord.Interaction):
            global markets
            try:
                market_id = len(markets) + 1
                new_market = {
                    'id': market_id,
                    'name': self.children[0].value,
                    'desc': self.children[1].value,
                    'cost':
                    int(self.children[2].value),  # Conversion inside try
                    'seller': str(interaction.user.id)
                }
                markets.append(new_market)
                await save_data('markets', new_market)
                await interaction.response.send_message(
                    f"Market listing created... ID {market_id}!",
                    ephemeral=True)
            except ValueError:  # Catch the error if conversion to int fails
                await interaction.response.send_message(
                    "Invalid cost. Please enter a number.", ephemeral=True)

    modal = MarketCreationModal()
    button = Button(label="Create Listing")  # Create the button
    view = View()
    view.add_item(button)  # Add the button to the view

    # Associate the modal with the button's callback
    async def button_callback(interaction):
        await interaction.response.send_modal(modal)

    button.callback = button_callback

    await ctx.send(f"{ctx.author.mention} Please fill out the form,",
                   view=view)


@bot.command(name='market')
@in_allowed_channels()
async def market_command(ctx, page: int = 1):
    """Displays the available market listings."""

    global markets, coin_data, market_view  # Access global view object
    items_per_page = 5
    total_pages = math.ceil(len(markets) / items_per_page)

    # --- Create the initial embed ---
    embed = discord.Embed(
        title="Market!",
        description=
        "Hey! Welcome to the Market!\n\nBrowse through our current offerings:",
        color=discord.Color.gold(),
    )

    # --- Button Logic ---
    async def previous_page(interaction, current_page: int):
        new_page = max(1, current_page - 1)
        await update_market_embed(interaction, new_page)

    async def next_page(interaction, current_page: int):
        global markets, coin_data, market_view
        new_page = min(total_pages, current_page + 1)
        await update_market_embed(interaction, new_page)

    # --- Buttons (add to the global view object) ---
    if len(market_view.children) == 0:  # Add buttons only once
        previous_button = Button(label="◀", style=discord.ButtonStyle.primary)
        previous_button.callback = lambda i: previous_page(i, 1
                                                           )  # Start on page 1

        next_button = Button(label="▶", style=discord.ButtonStyle.primary)
        next_button.callback = lambda i: next_page(i, 2)  # Next page will be 2
        market_view.add_item(previous_button)
        market_view.add_item(next_button)

    sorted_coins = sorted(coin_data.items(),
                          key=lambda item: item[1],
                          reverse=True)

    async def update_market_embed(interaction=None,
                                  current_page: int = 1,
                                  view=None):
        global markets, coin_data, market_view  # Access coin_data here
        start_index = (current_page - 1) * items_per_page
        end_index = start_index + items_per_page
        market_list = markets[start_index:end_index]

        embed.clear_fields()  # Clear existing fields before adding new ones
        embed.add_field(name=f"Page {current_page} of {total_pages}",
                        value="\u200b",
                        inline=False)

        for market in market_list:
            seller_id = int(market['seller'])
            seller = bot.get_user(seller_id)
            seller_name = seller.mention if seller else "Unknown Seller"
            short_desc = market['desc'][:200]
            if len(market['desc']) > 200:
                short_desc += "..."

            creator_position = next(
                (i + 1 for i, (user_id, _) in enumerate(sorted_coins)
                 if user_id == market['seller']), None)

            embed.add_field(
                name=f"{market['name']} | 🪙 {market['cost']:,}",
                value=f"**Seller:** {seller_name}\n{short_desc}\n",
                inline=False,
            )

        if interaction:
            # Edit the original message
            await interaction.response.edit_message(embed=embed,
                                                    view=market_view)
        else:
            # Send the initial message and return it
            return await ctx.reply(embed=embed, view=market_view)
            # Send the initial message

    await update_market_embed(current_page=page)


@bot.command(name='buy')
@in_allowed_channels()
async def buy_command(ctx, market_id: int ):
    if ctx.channel.id != 1264476140664262728: 
        await ctx.send(
            "This command can only be used in the designated market command channel."
        )
        return
    market = next((m for m in markets if m['id'] == market_id), None)
    if not market:
        await ctx.send(f"Market with ID {market_id} not found.")
        return

    buyer_id = str(ctx.author.id)  # Get user ID here
    if buyer_id == market['seller']:
        await ctx.send("You cannot buy your own service.")
        return

    cost = market['cost'] 
    if coin_data.get(buyer_id, 0) < cost and coin_data.get(buyer_id, 0) < INFINITY_THRESHOLD: 
        await ctx.send("You don't have enough coins to buy this service.")
        return

    coin_data[buyer_id] = coin_data.get(buyer_id, 0) - cost
    coin_data[buyer_id] -= cost
    await save_data('coin_data', {
        'user_id': int(buyer_id),
        'coins': coin_data[buyer_id]
    },
                    upsert=True)

    seller_id_str = str(market['seller'])
    coin_data[seller_id_str] += cost 
    await save_data('coin_data', {
        'user_id': int(market['seller']),
        'coins': coin_data[seller_id_str]  
    },
                    upsert=True)

    transaction_id = len(transactions) + 1
    transaction = {
        'id': transaction_id,
        'buyer': buyer_id,
        'seller': market['seller'],
        'market_id': market_id,
        'status': 'pending'
    }
    transactions.append(transaction)
    await save_data('transactions', transaction)
    # --- Create the embed for the seller ---
    embed_seller = discord.Embed(title="💰 New Order Received! 💰", color=discord.Color.gold()) 
    buyer_user = bot.get_user(int(buyer_id))
    seller_user = bot.get_user(int(market['seller']))
    embed_seller.add_field(name="Item:", value=f"**{market['name']}**", inline=False)
    embed_seller.add_field(name="Description:", value=f"{market['desc']}", inline=False)
    embed_seller.add_field(name="Buyer:", value=f"{buyer_user.mention}", inline=True)
    embed_seller.add_field(name="Price:", value=f"{cost:,}🪙", inline=True)
    embed_seller.add_field(name="Instructions:", value="Please fulfill the buyer's order promptly, otherwise you will be tracked by us!", inline=False)
    embed_seller.set_footer(text="Thank you for using the market!")
    # --- Send the embed to the seller in DM ---
    await seller_user.send(embed=embed_seller)
    # --- Create the embed for the buyer ---
    embed_buyer = discord.Embed(title="🎉 Purchase Successful! 🎉", color=discord.Color.gold())
    embed_buyer.add_field(name="Item:", value=f"**{market['name']}**", inline=False) 
    embed_buyer.add_field(name="Description:", value=f"{market['desc']}", inline=False)
    embed_buyer.add_field(name="Seller:", value=f"{seller_user.mention}", inline=True)
    embed_buyer.add_field(name="Price:", value=f"{cost:,}🪙", inline=True) 
    embed_buyer.set_footer(text="Thank you for your purchase!")
    # --- Send the embed to the buyer as a reply ---
    await ctx.reply(embed=embed_buyer)


@bot.command(name='pay')
@in_allowed_channels()
async def pay_command(ctx, amount: int, user: discord.User):
    payer = str(ctx.author.id)
    payee = str(user.id)

    if amount <= 0:
        await ctx.send("Amount must be positive.")
        return
    # --- Calculate Before Values ---
    payer_coins_before = handle_infinity(coin_data.get(payer, 0))
    payee_coins_before = handle_infinity(coin_data.get(payee, 0))
    # --- Check if payer has enough coins ---
    if coin_data.get(payer, 0) < amount and coin_data.get(payer, 0) < INFINITY_THRESHOLD:
        await ctx.send("You don't have enough coins to make this payment.")
        return
    coin_data[payer] = subtract_with_infinity(coin_data.get(payer, 0), amount)
    coin_data[payee] = add_with_infinity(coin_data.get(payee, 0), amount)
    # --- Save Data ---
    await save_data('coin_data', {'user_id': int(payer), 'coins': coin_data[payer]}, upsert=True)
    await save_data('coin_data', {'user_id': int(payee), 'coins': coin_data[payee]}, upsert=True)
    # --- Calculate After Values ---
    payer_coins_after = handle_infinity(coin_data.get(payer, 0))
    payee_coins_after = handle_infinity(coin_data.get(payee, 0))

    embed = discord.Embed(title="✅ Successful Transaction ✅", color=discord.Color.green())
    embed.add_field(name="From:", value=f"{ctx.author.mention}\n**Before:** {payer_coins_before} coins\n**After:** {payer_coins_after} coins", inline=True)
    embed.add_field(name="To:", value=f"{user.mention}\n**Before:** {payee_coins_before} coins\n**After:** {payee_coins_after} coins", inline=True)

    await ctx.send(embed=embed)

# --- Top Command ---
@bot.command(name='top')
@in_allowed_channels()
async def top_command(ctx, page: int = 1):
    """🪙 View the top users with the most coins (paginated)."""
    global coin_data
    if page <= 0:
        await ctx.send("Invalid page number. Please enter a positive number.")
        return

    sorted_users = sorted(coin_data.items(),
                          key=lambda item: item[1],
                          reverse=True)

    total_pages = math.ceil(len(sorted_users) / ITEMS_PER_PAGE)
    if page > total_pages:
        await ctx.send(
            f"Page number too high. There are only {total_pages} pages.")
        return

    start_index = (page - 1) * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    top_users = sorted_users[start_index:end_index]

    # --- Create Leaderboard String ---
    leaderboard_str = ""
    for i, (user_id, coins) in enumerate(top_users, start=start_index + 1):
        user = bot.get_user(int(user_id))
        user_display = user.mention if user else f"<@{user_id}>"
        coins_display = "∞ coins" if coins >= INFINITY_THRESHOLD else f"{coins:,} coins"
        leaderboard_str += f"{i}. {user_display} - {coins_display}\n"

    # --- Find Author's Position ---
    author_position = next((i + 1
                            for i, (user_id, _) in enumerate(sorted_users)
                            if user_id == str(ctx.author.id)), None)

    # --- Embed Creation ---
    embed = discord.Embed(
        title=f"The Richest People🪙 (Page {page}/{total_pages})",
        description=leaderboard_str,
        color=discord.Color.gold())

    embed.add_field(name=f"{ctx.author.name}'s Position:",
                    value=f"#{author_position}"
                    if author_position else "Not on the leaderboard",
                    inline=False)

    # --- Buttons ---
    previous_button = Button(label="◀", style=discord.ButtonStyle.primary)
    next_button = Button(label="▶", style=discord.ButtonStyle.primary)
    view = View()
    view.add_item(previous_button)
    view.add_item(next_button)

    # --- Send Initial Message ---
    message = await ctx.send(embed=embed, view=view)

    # --- Button Callbacks (Edit the original message) ---
    async def previous_page(interaction):
        nonlocal page
        new_page = max(1, page - 1)
        page = new_page
        await update_leaderboard(new_page, message, interaction, top_command,
                                 view)

    async def next_page(interaction):
        nonlocal page
        new_page = min(total_pages, page + 1)
        page = new_page
        await update_leaderboard(new_page, message, interaction, top_command,
                                 view)

    previous_button.callback = previous_page
    next_button.callback = next_page


# --- Bottom Command ---
@bot.command(name='bottom')
@in_allowed_channels()
async def bottom_command(ctx, page: int = 1):
    global coin_data
    """⚠️ Redlist."""
    if page <= 0:
        await ctx.send("Invalid page number. Please enter a positive number.")
        return

    sorted_users = sorted(coin_data.items(), key=lambda item: item[1])

    total_pages = math.ceil(len(sorted_users) / ITEMS_PER_PAGE)
    if page > total_pages:
        await ctx.send(
            f"Page number too high. There are only {total_pages} pages.")
        return

    start_index = (page - 1) * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    bottom_users = sorted_users[start_index:end_index]

    # --- Create Leaderboard String ---
    leaderboard_str = ""
    for i, (user_id, coins) in enumerate(bottom_users, start=start_index + 1):
        user = bot.get_user(int(user_id))
        user_display = user.mention if user else f"<@{user_id}>"
        coins_display = "-∞ coins" if coins <= NEGATIVE_INFINITY_THRESHOLD else f"{coins:,} coins"
        leaderboard_str += f"{i}. {user_display} - {coins_display}\n"

    # --- Find Author's Position ---
    author_position = next((i + 1
                            for i, (user_id, _) in enumerate(sorted_users)
                            if user_id == str(ctx.author.id)), None)

    # --- Embed Creation ---
    embed = discord.Embed(title=f"⚠️ Redlist. (Page {page}/{total_pages})",
                          description=leaderboard_str,
                          color=discord.Color.red())
    embed.add_field(name=f"{ctx.author.name}'s Position:",
                    value=f"#{author_position}"
                    if author_position else "Not on the leaderboard",
                    inline=False)

    # --- Buttons ---
    previous_button = Button(label="◀", style=discord.ButtonStyle.primary)
    next_button = Button(label="▶", style=discord.ButtonStyle.primary)
    view = View()
    view.add_item(previous_button)
    view.add_item(next_button)

    # --- Send Initial Message ---
    message = await ctx.send(embed=embed, view=view)

    # --- Button Callbacks ---
    async def previous_page(interaction):
        nonlocal page
        new_page = max(1, page - 1)
        page = new_page
        await update_leaderboard(new_page, message, interaction,
                                 bottom_command, view)

    async def next_page(interaction):
        nonlocal page
        new_page = min(total_pages, page + 1)
        page = new_page
        await update_leaderboard(new_page, message, interaction,
                                 bottom_command, view)

    previous_button.callback = previous_page
    next_button.callback = next_page


#update_learderboard
async def update_leaderboard(page: int, message: discord.Message,
                             interaction: discord.Interaction, command_to_call,
                             view: View):
    await interaction.response.defer()
    global coin_data
    sorted_users = sorted(
        coin_data.items(), key=lambda item: item[1],
        reverse=True) if command_to_call == top_command else sorted(
            coin_data.items(), key=lambda item: item[1])

    total_pages = math.ceil(len(sorted_users) / ITEMS_PER_PAGE)
    start_index = (page - 1) * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE

    # --- Create Leaderboard String (Iterate over FULL sorted_users list) ---
    leaderboard_str = ""
    for i, (user_id, coins) in enumerate(sorted_users, start=1): 
        user = bot.get_user(int(user_id))
        user_display = user.mention if user else f"<@{user_id}>"

        # --- Updated Infinity Check ---
        if command_to_call == top_command:
            coins_display = "∞ coins" if coins >= INFINITY_THRESHOLD else f"{coins:,} coins" 
        else:  # bottom_command
            coins_display = "-∞ coins" if coins <= NEGATIVE_INFINITY_THRESHOLD else f"{coins:,} coins" 

        # --- Display entries within the current page range ---
        if start_index < i <= end_index:
            leaderboard_str += f"{i}. {user_display} - {coins_display}\n"

    author_position = next((i + 1
                            for i, (user_id, _) in enumerate(sorted_users)
                            if user_id == str(interaction.user.id)), None)

    # --- Update Embed ---
    embed = discord.Embed(
        title=f"The Richest People🪙 (Page {page}/{total_pages})"
        if command_to_call == top_command else
        f"⚠️ Redlist. (Page {page}/{total_pages})",
        description=leaderboard_str,
        color=discord.Color.gold()
        if command_to_call == top_command else discord.Color.red())
    embed.add_field(name=f"{interaction.user.name}'s Position:",
                    value=f"#{author_position}"
                    if author_position else "Not on the leaderboard",
                    inline=False)

    # --- Update View ---
    await message.edit(embed=embed, view=view)


# --- Admin Commands ---
def has_role(role_id: int):

    def predicate(ctx):
        role = discord.utils.get(ctx.author.roles, id=role_id)
        return role is not None

    return commands.check(predicate)


@bot.command(name='banish')
@in_allowed_channels()
async def banish_command(ctx, member: discord.Member):
    log_admin_command(ctx.author.name, f"!banish {member}")

    # Role IDs
    required_role_id = 1227279982435500032
    restricted_role_id = 1266352717572603967

    # Check if the author has the required role
    required_role = discord.utils.get(ctx.author.roles, id=required_role_id)
    if not required_role:
        await ctx.send("You do not have the required role to use this command."
                       )
        return

    # Get the restricted role
    restricted_role = discord.utils.get(ctx.guild.roles, id=restricted_role_id)
    if not restricted_role:
        await ctx.send("Role not found.")
        return

    # Add the restricted role to the specified user
    await member.add_roles(restricted_role)
    await ctx.send(f"I CAST, NO CREATE MARKET FOR YOU {member.mention}")


@bot.command(name='unbanish')
@in_allowed_channels()
async def banish_command(ctx, member: discord.Member):
    log_admin_command(ctx.author.name, f"!unbanish {member}")

    # Role IDs
    required_role_id = 1227279982435500032
    restricted_role_id = 1266352717572603967

    # Check if the author has the required role
    required_role = discord.utils.get(ctx.author.roles, id=required_role_id)
    if not required_role:
        await ctx.send("You do not have the required role to use this command."
                       )
        return

    # Get the restricted role
    restricted_role = discord.utils.get(ctx.guild.roles, id=restricted_role_id)
    if not restricted_role:
        await ctx.send("Role not found.")
        return

    # Remove the restricted role from the specified user
    await member.remove_roles(restricted_role)
    await ctx.send(f"I CAST, REMOVE CURSE {member.mention}")


def create_embed(title, description, color=discord.Color.gold()):
    """Creates and returns a discord.Embed object."""
    return discord.Embed(title=title, description=description, color=color)


# --- Bioweather Command ---
@bot.command(name='bioweather')
@in_allowed_channels()
@has_role(1227279982435500032)
async def bioweather_command(ctx, weather: str = None):
    """Changes the weather in the game, including Chaos."""
    global weather_task
    channel = bot.get_channel(HUNT_CHANNEL_ID)
    valid_weather = ["Sunny", "Snowy", "Rainy", "Stormy", "Super Storm"]

    if weather is not None:
        weather = weather.replace("_", " ")
        weather = weather.title()

    if weather not in valid_weather:
        await ctx.reply(
            "Invalid weather type. Choose from: Sunny, Snowy, Rainy, Stormy, Super Storm, must use 5 weather in order to spawn CHAOS"
        )
        return

    await change_weather(channel, new_weather=weather)

@bot.command(name='delete_all_markets')
@has_role(1227279982435500032)
async def delete_all_markets_command(ctx):
    log_admin_command(ctx.author.name, "!delete_all_markets")
    global markets
    markets = []
    await supabase.table('markets').delete().execute()
    await ctx.send("All markets have been deleted.")


@bot.command(name='delete_market')
@has_role(1227279982435500032)
async def delete_market_command(ctx, market_id: int):
    log_admin_command(ctx.author.name, f"!delete_market {market_id}")
    global markets
    markets = [market for market in markets if market['id'] != market_id]
    await supabase.table('markets').delete().eq('id', market_id).execute()
    await ctx.send(f"Market with ID {market_id} has been deleted.")


@bot.command(name='give')
@has_role(1227279982435500032)
async def give_command(ctx, amount: str, user: discord.User):
    log_admin_command(ctx.author.name, f"!give {amount} {user}")
    try:
        amount = int(amount)
        user_id = str(user.id)

        coins_before = coin_data.get(user_id, 0) 
        coins_before_display = handle_infinity(coins_before)

        if amount == 0:
            await ctx.send("Amount cannot be zero.")
            return
        coin_data[user_id] = add_with_infinity(coins_before, amount) 
        coin_data[user_id] = INFINITY_THRESHOLD if coin_data[user_id] >= INFINITY_THRESHOLD else coin_data[user_id]
        coins_after = handle_infinity(coin_data[user_id])

        embed = discord.Embed(title="✅Success✅", color=discord.Color.green())
        embed.description = f"{user.mention} has {coins_before_display} -> {coins_after} coins!"
        await ctx.send(embed=embed)

    except ValueError:
        await ctx.send("Invalid amount. Please enter a number.")
    await save_data('coin_data', {'user_id': int(user_id), 'coins': coin_data[user_id]}, upsert=True) 

@bot.command(name='setcoin')
@has_role(1227279982435500032)
async def setcoin_command(ctx, amount: str, user: discord.User):
    log_admin_command(ctx.author.name, f"!setcoin {amount} {user}")
    try:
        amount = int(amount)  
        user_id = str(user.id)

        coins_before = coin_data.get(user_id, 0)
        coins_before_display = handle_infinity(coins_before)

        # --- Directly set the coin amount ---
        coin_data[user_id] = amount

        # --- Apply infinity thresholds AFTER setting ---
        coin_data[user_id] = INFINITY_THRESHOLD if coin_data[user_id] >= INFINITY_THRESHOLD else coin_data[user_id]
        coin_data[user_id] = NEGATIVE_INFINITY_THRESHOLD if coin_data[user_id] <= NEGATIVE_INFINITY_THRESHOLD else coin_data[user_id]

        coins_after = handle_infinity(coin_data[user_id]) 

        embed = discord.Embed(title="✅Success✅", color=discord.Color.green())
        embed.description = f"{user.mention} has {coins_before_display} -> {coins_after} coins!"
        await ctx.send(embed=embed)

    except ValueError:
        await ctx.send("Invalid amount. Please enter a number.")
    await save_data('coin_data', {'user_id': int(user_id), 'coins': coin_data[user_id]}, upsert=True) 


@bot.command(name='see_all_transactions')
@has_role(1227279982435500032)
async def see_all_transactions_command(ctx):
    if not transactions:
        await ctx.send("No transactions found.")
        return

    transaction_ids = [str(transaction['id']) for transaction in transactions]
    await ctx.send("Transaction IDs: " + ", ".join(transaction_ids))


@bot.command(name='see_transaction')
@has_role(1227279982435500032)
async def see_transaction_command(ctx,
                                  transaction_id: int):
    transaction = next((t for t in transactions if t['id'] == transaction_id),
                       None)
    if not transaction:
        await ctx.send(f"Transaction with ID {transaction_id} not found.")
        return

    embed = discord.Embed(title=f"Transaction {transaction_id}",
                          color=discord.Color.gold())
    embed.add_field(name="Buyer", value=transaction['buyer'], inline=True)
    embed.add_field(name="Seller", value=transaction['seller'], inline=True)
    embed.add_field(name="Market ID",
                    value=transaction['market_id'],
                    inline=True)
    embed.add_field(name="Status", value=transaction['status'], inline=True)
    await ctx.send(embed=embed)


@bot.command(name='set_all_coins')
@has_role(1227279982435500032)
async def set_all_coins_command(ctx, amount: str):
    log_admin_command(ctx.author.name, f"!set_all_coins {amount}")
    try:
        amount = int(amount)
        new_amount = amount
        new_amount = float("inf") if new_amount > 2147483647 else new_amount
        display_amount = handle_infinity(new_amount) 
        for user_id in coin_data.keys():
            coin_data[user_id] = new_amount
        embed = discord.Embed(title="✅Success✅", color=discord.Color.green())
        embed.description = (
            f"All users' coin amounts have been set to {display_amount}!")
        await ctx.send(embed=embed)
    except ValueError:
        await ctx.send("Invalid amount. Please enter a number.") # dont add save data here it is too risky


@bot.command(name='promote')
async def promote_command(ctx, member: discord.Member):
    if ctx.author.id in AUTHORIZED_USERS:
        log_admin_command(ctx.author.name, f"!promote {member}")
        role = discord.utils.get(ctx.guild.roles, id=ROLE_ID)
        if role:
            await member.add_roles(role)
            await ctx.send(
                f'{member.mention} has been given the role {role.name}.')
        else:
            await ctx.send('Role not found.')
    else:
        await ctx.send('You are not choosen to use this command.')


@bot.command(name='demote')
async def demote_command(ctx, member: discord.Member):
    if ctx.author.id in AUTHORIZED_USERS:
        log_admin_command(ctx.author.name, f"!demote {member}")
        role = discord.utils.get(ctx.guild.roles, id=ROLE_ID)
        if role:

            await member.remove_roles(role)
            await ctx.send(
                f'{member.mention} has had the role {role.name} removed.')
        else:
            await ctx.send('Role not found.')
    else:
        await ctx.send('You are not choosen to use this command.')

@bot.command(name='force_chaos_check')
@has_role(1227279982435500032)
async def force_chaos_check_command(ctx):
    global last_weathers, current_weather
    print(f"Current last_weathers: {last_weathers}")

    if len(last_weathers) == 5:
        if len(set(last_weathers)) == 5:
            print("Chaos condition met!")
            channel = bot.get_channel(HUNT_CHANNEL_ID)
            current_weather = "Chaos"
            await change_weather(channel, new_weather="Chaos", duration=CHAOS_DURATION)
            last_weathers = []  # Clear the list
        else:
            print("Chaos condition NOT met. Duplicate weather in last 5.") 
    else:
        print("Chaos condition NOT met. Not enough unique weather types yet.")

@bot.command(name='edit_user')
@commands.has_role(1227279982435500032)
async def edit_user_command(ctx, target_user: discord.User):
    """Edit the gun durability, ammo, camp durability, health, and healing potions of a specified user."""
    target_user_id = str(target_user.id)

    # Only the command author can interact with the modal
    def check_author(interaction: discord.Interaction):
        return interaction.user == ctx.author

    embed = discord.Embed(title="Edit User Data", color=discord.Color.yellow())
    button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="edit_user_button")

    async def button_callback(interaction: discord.Interaction):
        if interaction.user != ctx.author:
            await interaction.response.send_message(
                "This button is not for you!", ephemeral=True
            )
            return

        modal = Modal(title="Edit User Data")

        gun_durability_input = TextInput(
            label="Gun Durability",
            placeholder="Enter the new gun durability...",
            style=discord.TextStyle.short,
            required=True,
            max_length=50
        )
        modal.add_item(gun_durability_input)

        ammo_input = TextInput(
            label="Ammo",
            placeholder="Enter the new ammo amount...",
            style=discord.TextStyle.short,
            required=True,
            max_length=50
        )
        modal.add_item(ammo_input)

        camp_durability_input = TextInput(  # Input for camp durability
            label="Camp Durability",
            placeholder="Enter the new camp durability...",
            style=discord.TextStyle.short,
            required=True,
            max_length=50
        )
        modal.add_item(camp_durability_input)

        health_input = TextInput(  # Input for health
            label="Health",
            placeholder="Enter the new health...",
            style=discord.TextStyle.short,
            required=True,
            max_length=50
        )
        modal.add_item(health_input)

        healing_potions_input = TextInput(  # Input for healing potions
            label="Healing Potions",
            placeholder="Enter the new number of healing potions...",
            style=discord.TextStyle.short,
            required=True,
            max_length=50
        )
        modal.add_item(healing_potions_input)

        async def modal_submit(interaction: discord.Interaction):
            global player_data

            if target_user_id not in player_data:
                player_data[target_user_id] = {}

            try:
                # Get values from input fields and apply infinity logic
                player_data[target_user_id]["gun_durability"] = int(gun_durability_input.value)
                player_data[target_user_id]["ammo"] = int(ammo_input.value)
                player_data[target_user_id]["camp_durability"] = int(camp_durability_input.value)
                player_data[target_user_id]["health"] = int(health_input.value)
                player_data[target_user_id]["healing_potions"] = int(healing_potions_input.value)
                for key in ["gun_durability", "ammo", "camp_durability", "healing_potions", "health"]:
                    if player_data[target_user_id][key] >= INFINITY_THRESHOLD:
                        player_data[target_user_id][key] = INFINITY_THRESHOLD
                await interaction.response.send_message(
                    f"Updated {target_user.mention}'s data:\n\n"
                    f"**Gun Durability:** {handle_infinity(player_data[target_user_id]['gun_durability'])}\n"
                    f"**Ammo:** {handle_infinity(player_data[target_user_id]['ammo'])}\n"
                    f"**Camp Durability:** {handle_infinity(player_data[target_user_id]['camp_durability'])}\n"
                    f"**Health:** {handle_infinity(player_data[target_user_id]['health'])}\n"
                    f"**Healing Potions:** {handle_infinity(player_data[target_user_id]['healing_potions'])}",
                    ephemeral=True
                )

            except ValueError:
                await interaction.response.send_message(
                    "Invalid input. Enter whole numbers or 'infinity'.", ephemeral=True
                )
                return

            await save_data(
                'player_data',
                {
                    'user_id': int(target_user_id),
                    'gun_durability': player_data[target_user_id]['gun_durability'],
                    'ammo': player_data[target_user_id]['ammo'],
                    'health': player_data[target_user_id].get('health', 100),
                    'camp_durability': player_data[target_user_id].get('camp_durability', 100),
                    'healing_potions': player_data[target_user_id].get('healing_potions', 0)
                },
                upsert=True
            )

        modal.on_submit = modal_submit
        await interaction.response.send_modal(modal)

    button.callback = button_callback
    view = View(timeout=900)
    view.add_item(button)
    await ctx.reply(embed=embed, view=view)
    log_admin_command(ctx.author.name, f"!edit_user {target_user}")

rarity_roles = {
    "Ultra": 1253891579392032829,
    "Super": 1253891495090454558,
    "Omega": 1253891315893141574,
    "Fabled": 1253891650871230496,
    "Divine": 1253891705275420713,
    "Supreme": 1253891749013618709,
    "Omnipotent": 1265899339524476989
}


@bot.command()
@commands.has_role(1227279982435500032)  # Role ID for permission check
async def add_rarity_role(ctx, rarity: str, member: discord.Member):
    role_id = rarity_roles.get(rarity)
    if role_id:
        role = ctx.guild.get_role(role_id)
        if role:
            await member.add_roles(role)
            embed = discord.Embed(
                title="Role Added",
                description=f"{rarity} role has been added to {member.mention}.",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            log_admin_command(ctx.author.name, f"!add_rarity_role {rarity} {member}")
        else:
            await ctx.send("Role not found.")
    else:
        available_rarities = ', '.join(rarity_roles.keys())
        await ctx.send(f"Invalid rarity specified. Available rarities are: {available_rarities}")

@add_rarity_role.error
async def add_rarity_role_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("You don't have permission to use this command.")
    else:
        await ctx.send(f"An error occurred: {error}")

@bot.command()
@commands.has_role(1227279982435500032)  # Role ID for permission check
async def delete_rarity_role(ctx, rarity: str, member: discord.Member):
    role_id = rarity_roles.get(rarity)
    if role_id:
        role = ctx.guild.get_role(role_id)
        if role:
            await member.remove_roles(role)
            embed = discord.Embed(
                title="Role Removed",
                description=f"{rarity} role has been removed from {member.mention}.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            log_admin_command(ctx.author.name, f"!delete_rarity_role {rarity} {member}")
        else:
            await ctx.send("Role not found.")
    else:
        available_rarities = ', '.join(rarity_roles.keys())
        await ctx.send(f"Invalid rarity specified. Available rarities are: {available_rarities}")

@delete_rarity_role.error
async def delete_rarity_role_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("You don't have permission to use this command.")
    else:
        await ctx.send(f"An error occurred: {error}")
#owner command
random_words = ["scammer",
                 "pls bioevent", 
                 "beggar", 
                 "pls carry me", 
                 "ayoub fan", 
                 "ayoub bigest fan", 
                 "fire exe, pls ban me", 
                 "fire exe hater", 
                 "CASE OH 2.0", 
                 "im gay", 
                 "local femboy", 
                 "im a furry :3", 
                 "pls banish me"]

@bot.command()
async def delete_all_rarities(ctx, member: discord.Member):
    if ctx.author.id not in AUTHORIZED_USERS and ctx.author.id not in AUTHORIZED_MEMBER:
        await ctx.send("You do not have permission to use this command.")
        return
    
    if ctx.author.id in AUTHORIZED_MEMBER:
        log_admin_command(ctx.author.name, f"delete_all_rarities {member.name}")
    
    for role_name, role_id in rarity_roles.items():
        role = ctx.guild.get_role(role_id)
        if role in member.roles:
            await member.remove_roles(role)
    
    embed = discord.Embed(
        title="Roles Removed",
        description=f"All rarity roles have been removed from {member.mention}.",
        color=discord.Color.red()
    )
    await ctx.send(embed=embed)

@delete_all_rarities.error
async def delete_all_rarities_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("You don't have permission to use this command.")
    else:
        await ctx.send(f"An error occurred: {error}")

@bot.command()
async def delete_all_rarities_all(ctx):
    if ctx.author.id not in AUTHORIZED_USERS and ctx.author.id not in AUTHORIZED_MEMBER:
        await ctx.send("You do not have permission to use this command.")
        return
    
    if ctx.author.id in AUTHORIZED_MEMBER:
        log_admin_command(ctx.author.name, "delete_all_rarities_all")

    for member in ctx.guild.members:
        for role_name, role_id in rarity_roles.items():
            role = ctx.guild.get_role(role_id)
            if role in member.roles:
                await member.remove_roles(role)
    
    embed = discord.Embed(
        title="Roles Removed",
        description="All rarity roles have been removed from all users.",
        color=discord.Color.red()
    )
    await ctx.send(embed=embed)


@delete_all_rarities_all.error
async def delete_all_rarities_all_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("You don't have permission to use this command.")
    else:
        await ctx.send(f"An error occurred: {error}")
@bot.command()
@commands.has_permissions(administrator=True)
async def owoify(ctx, user: discord.Member):
    if ctx.author.id not in AUTHORIZED_USERS and ctx.author.id not in AUTHORIZED_MEMBER:
        await ctx.send("You are not authorized to use this command.")
        return
    
    if ctx.author.id in AUTHORIZED_MEMBER:
        log_admin_command(ctx.author.name, f"owoify {user.name}")

    original_text = user.display_name

    if random.choice([True, False]):
        owoified_text = original_text.replace('r', 'w').replace('R', 'W')
    else:
        additions = ["owo", ":3", "nyaa~~", "(femboy)", "(furry)", "please fuck me"]
        owoified_text = original_text + " " + random.choice(additions)

    try:
        await user.edit(nick=owoified_text)
        embed = discord.Embed(
            title="OwOify",
            description=f"{user.mention}, your nickname has been changed to: **{owoified_text}**",
            color=discord.Color.purple()
        )
        await ctx.send(embed=embed)
    except discord.Forbidden:
        await ctx.send("I do not have permission to change this user's nickname.")
    except discord.HTTPException as e:
        await ctx.send(f"An error occurred while trying to change the nickname: {e}")


@bot.command()
@commands.has_permissions(administrator=True)
async def change_name(ctx, member: discord.Member):
    if ctx.author.id not in AUTHORIZED_USERS and ctx.author.id not in AUTHORIZED_MEMBER:
        await ctx.send("You are not authorized to use this command.")
        return
    
    if ctx.author.id in AUTHORIZED_MEMBER:
        log_admin_command(ctx.author.name, f"change_name {member.name}")

    new_nickname = random.choice(random_words)

    try:
        await member.edit(nick=new_nickname)
        embed = discord.Embed(
            title="Nickname Changed",
            description=f"{member.mention}'s nickname has been changed to **{new_nickname}**",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)
    except discord.Forbidden:
        await ctx.send("I don't have permission to change that user's nickname.")
    except discord.HTTPException as e:
        await ctx.send(f"An error occurred: {e}")


@bot.command()
async def view_logs(ctx, page: int = 1):
    if ctx.author.id in AUTHORIZED_USERS or ctx.author.id in AUTHORIZED_MEMBER:

        with open('admin_logs.txt', 'r') as f:
            logs = f.readlines()

        items_per_page_logs = 10
        total_pages = math.ceil(len(logs) / items_per_page_logs)

        embed = discord.Embed(
            title="Admin Logs",
            color=0x8B0000
        )

        current_page = page

        async def previous_page(interaction):
            nonlocal current_page
            current_page = max(1, current_page - 1)
            await update_logs_embed(interaction)

        async def next_page(interaction):
            nonlocal current_page
            current_page = min(total_pages, current_page + 1)
            await update_logs_embed(interaction)

        previous_button = discord.ui.Button(label="◀", style=discord.ButtonStyle.primary)
        previous_button.callback = previous_page

        next_button = discord.ui.Button(label="▶", style=discord.ButtonStyle.primary)
        next_button.callback = next_page

        log_view = discord.ui.View()
        log_view.add_item(previous_button)
        log_view.add_item(next_button)

        async def update_logs_embed(interaction=None):
            start_index = (current_page - 1) * items_per_page_logs
            end_index = start_index + items_per_page_logs
            log_list = logs[start_index:end_index]

            embed.clear_fields()
            embed.add_field(
                name=f"Page {current_page} of {total_pages}",
                value="\u200b",
                inline=False
            )

            formatted_logs = "\n".join(log.strip() for log in log_list)

            embed.add_field(name="Logs", value=formatted_logs or "No logs available.", inline=False)

            if interaction:
                await interaction.response.edit_message(embed=embed, view=log_view)
            else:
                await ctx.send(embed=embed, view=log_view)

        await update_logs_embed()

    else:
        await ctx.send("# NO")


@bot.command(name='force_pay')
async def force_pay_command(ctx, amount: int, payer: discord.User, payee: discord.User):
    if ctx.author.id not in AUTHORIZED_USERS and ctx.author.id not in AUTHORIZED_MEMBER:
        await ctx.send("Hell nah, shut your mouth, go beg him, not using this command, you doesnt have perm mf")
        return

    if ctx.author.id in AUTHORIZED_MEMBER:
        log_admin_command(ctx.author.name, f"force_pay {amount} from {payer.name} to {payee.name}")

    payer_id = str(payer.id)
    payee_id = str(payee.id)

    if amount <= 0:
        await ctx.send("Amount must be positive.")
        return

    payer_coins_before = handle_infinity(coin_data.get(payer_id, 0))
    payee_coins_before = handle_infinity(coin_data.get(payee_id, 0))

    if coin_data.get(payer_id, 0) != INFINITY_THRESHOLD and coin_data.get(payer_id, 0) < amount:
        await ctx.send(f"{payer.mention} doesn't have enough coins to make this payment.")
        return

    coin_data[payer_id] = subtract_with_infinity(coin_data.get(payer_id, 0), amount) 
    coin_data[payee_id] = add_with_infinity(coin_data.get(payee_id, 0), amount) 

    await save_data('coin_data', {'user_id': int(payer_id), 'coins': coin_data[payer_id]}, upsert=True)
    await save_data('coin_data', {'user_id': int(payee_id), 'coins': coin_data[payee_id]}, upsert=True)

    payer_coins_after = handle_infinity(coin_data.get(payer_id, 0))
    payee_coins_after = handle_infinity(coin_data.get(payee_id, 0))

    embed = discord.Embed(title="✅ Forceful Transaction ✅", color=discord.Color.red())
    embed.add_field(name="From:", value=f"{payer.mention}\n**Before:** {payer_coins_before} coins\n**After:** {payer_coins_after} coins", inline=True)
    embed.add_field(name="To:", value=f"{payee.mention}\n**Before:** {payee_coins_before} coins\n**After:** {payee_coins_after} coins", inline=True)

    await ctx.send(embed=embed)

# Role IDs to be used in the command
abmin = [
    1231904184459333703,
    1252971250398007387
]
@bot.command(name='give_abmin')
async def give_abmin(ctx, member: discord.Member):
    # Check if the user is authorized
    if ctx.author.id not in AUTHORIZED_USERS and ctx.author.id not in AUTHORIZED_MEMBER:
        await ctx.send("no access for you mf. go ask fire exe for perm")
        return

    # Log command if the user is in AUTHORIZED_MEMBER
    if ctx.author.id in AUTHORIZED_MEMBER:
        log_admin_command(ctx.author.name, f"give_abmin {member.name}")

    # Remove all specified roles from the member
    roles_to_remove = [discord.Object(id=role_id) for role_id in abmin]
    await member.remove_roles(*roles_to_remove)
    
    # Determine the role to add and the message to send
    if random.random() < 0.75:
        # 75% chance of getting nothing
        await ctx.send(f"lmao, {member.mention} you don't get anything, lmao. Now get out")
    else:
        # 25% chance to assign one of the roles
        new_role_id = random.choice(abmin)
        new_role = discord.Object(id=new_role_id)
        await member.add_roles(new_role)

        if new_role_id == 1231904184459333703:
            await ctx.send(f"{member.mention}, you got an abmin role")
        elif new_role_id == 1252971250398007387:
            await ctx.send(f"{member.mention}, you got a fake abmin role, nice, now touch grass")

@bot.command(name='add_member')
async def add_member(ctx, member: discord.Member):
    if ctx.author.id not in AUTHORIZED_USERS:
        await ctx.send("You do not have permission to use this command.")
        return
    
    if member.id in AUTHORIZED_MEMBER:
        await ctx.send(f"{member.mention} is already an authorized member.")
    else:
        AUTHORIZED_MEMBER.append(member.id)
        await ctx.send(f"{member.mention} has been added to the authorized members list.")

@bot.command(name='remove_member')
async def remove_member(ctx, member: discord.Member):
    if ctx.author.id not in AUTHORIZED_USERS:
        await ctx.send("You do not have permission to use this command.")
        return

    if member.id not in AUTHORIZED_MEMBER:
        await ctx.send(f"{member.mention} is not an authorized member.")
    else:
        AUTHORIZED_MEMBER.remove(member.id)
        await ctx.send(f"{member.mention} has been removed from the authorized members list.")

# --- Run Bot ---
# Get Discord token from environment variables
discord_token = os.getenv("DISCORD_TOKEN")
if not discord_token:
    print("Error: DISCORD_TOKEN not found in .env file")
    exit(1)

bot.run(discord_token)


