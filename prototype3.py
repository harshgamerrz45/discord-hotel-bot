import asyncio
import os
import sys
import threading
from datetime import datetime

import discord
from discord.ext import commands

# ── Driver selection ──────────────────────────────────────
try:
    import pymysql
    _PYMYSQL = True
except ImportError:
    import mysql.connector
    _PYMYSQL = False

# ─────────────────────────────────────────────────────────
#  DATABASE CONFIG
# ─────────────────────────────────────────────────────────

DB_HOST     = os.environ.get("MYSQL_HOST", "").strip()
DB_PORT     = int(os.environ.get("MYSQL_PORT", "3306").strip() or "3306")
DB_USER     = os.environ.get("MYSQL_USER", "").strip()
DB_PASSWORD = os.environ.get("MYSQL_PASSWORD", "").strip()
DB_DATABASE = os.environ.get("MYSQL_DATABASE", "").strip()
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "").strip()

REQUIRED_ENV_VARS = (
    "DISCORD_TOKEN",
    "MYSQL_HOST",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "MYSQL_DATABASE",
)

def validate_environment():
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name, "").strip()]
    if missing:
        raise RuntimeError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
            + ". Add them in your hosting provider's Variables/Environment settings."
        )

# ─────────────────────────────────────────────────────────
#  DATABASE HELPERS
# ─────────────────────────────────────────────────────────

def get_connection():
    if _PYMYSQL:
        return pymysql.connect(
            host=DB_HOST, port=DB_PORT, user=DB_USER,
            password=DB_PASSWORD, database=DB_DATABASE,
            connect_timeout=10,
            cursorclass=pymysql.cursors.Cursor
        )
    else:
        return mysql.connector.connect(
            host=DB_HOST, port=DB_PORT, user=DB_USER,
            password=DB_PASSWORD, database=DB_DATABASE,
            connection_timeout=10, ssl_disabled=True
        )

def setup_database():
    print(f"🔌 Connecting to MySQL at {DB_HOST}:{DB_PORT} ...")
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rooms (
            id               INT AUTO_INCREMENT PRIMARY KEY,
            room_number      VARCHAR(10) UNIQUE NOT NULL,
            room_type        VARCHAR(50) NOT NULL,
            status           VARCHAR(20) DEFAULT 'available',
            price_per_night  DECIMAL(10,2) NOT NULL,
            description      TEXT,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            id               INT AUTO_INCREMENT PRIMARY KEY,
            guest_name       VARCHAR(100) NOT NULL,
            guest_discord_id VARCHAR(50),
            room_number      VARCHAR(10) NOT NULL,
            check_in         DATE NOT NULL,
            check_out        DATE NOT NULL,
            total_price      DECIMAL(10,2),
            status           VARCHAR(20) DEFAULT 'confirmed',
            notes            TEXT,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (room_number) REFERENCES rooms(room_number)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guests (
            id             INT AUTO_INCREMENT PRIMARY KEY,
            discord_id     VARCHAR(50) UNIQUE,
            name           VARCHAR(100) NOT NULL,
            email          VARCHAR(100),
            phone          VARCHAR(30),
            loyalty_points INT DEFAULT 0,
            vip_status     BOOLEAN DEFAULT FALSE,
            created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS staff (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            discord_id VARCHAR(50) UNIQUE NOT NULL,
            name       VARCHAR(100) NOT NULL,
            role       VARCHAR(50) NOT NULL,
            shift      VARCHAR(50),
            added_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS maintenance (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            room_number VARCHAR(10),
            issue       TEXT NOT NULL,
            priority    VARCHAR(20) DEFAULT 'normal',
            status      VARCHAR(20) DEFAULT 'open',
            reported_by VARCHAR(50),
            resolved_at TIMESTAMP NULL,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_log (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            action       VARCHAR(100),
            performed_by VARCHAR(100),
            details      TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()
    print("✅ Database tables ready.")

def log_action(action, performed_by, details=""):
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO bot_log (action, performed_by, details) VALUES (%s, %s, %s)",
            (action, performed_by, details)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception:
        pass

# ─────────────────────────────────────────────────────────
#  BOT SETUP
# ─────────────────────────────────────────────────────────

PREFIX  = "$"
intents = discord.Intents.default()
intents.message_content = True
intents.members         = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

@bot.event
async def on_ready():
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  🏨 Grand Hotel Management Bot")
    print(f"  ✅ Logged in as: {bot.user} (ID: {bot.user.id})")
    print(f"  📡 Prefix: {PREFIX}")
    print(f"  🌐 Servers: {len(bot.guilds)}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="🏨 Grand Hotel | $hotelhelp"),
        status=discord.Status.online
    )

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(title="🚫 Permission Denied", description="You don't have permission to use this command.", color=discord.Color.red())
    elif isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(title="⚠️ Missing Argument", description=f"Missing: `{error.param.name}`\nUse `$hotelhelp` for help.", color=discord.Color.orange())
    elif isinstance(error, commands.BadArgument):
        embed = discord.Embed(title="⚠️ Invalid Argument", description=str(error), color=discord.Color.orange())
    else:
        embed = discord.Embed(title="❌ Error", description=str(error), color=discord.Color.red())
    await ctx.send(embed=embed)

# ─────────────────────────────────────────────────────────
#  COG: ROOMS
# ─────────────────────────────────────────────────────────

class Rooms(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="addroom")
    @commands.has_permissions(administrator=True)
    async def add_room(self, ctx, room_number: str, room_type: str, price: float, *, description: str = "No description provided."):
        """Usage: $addroom <room_number> <type> <price> [description]"""
        conn = get_connection(); cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO rooms (room_number, room_type, price_per_night, description) VALUES (%s, %s, %s, %s)",
                (room_number, room_type, price, description)
            )
            conn.commit()
            embed = discord.Embed(title="🏨 Room Added Successfully", color=discord.Color.green(), timestamp=datetime.utcnow())
            embed.add_field(name="🔢 Room Number", value=room_number, inline=True)
            embed.add_field(name="🛏️ Type",        value=room_type,   inline=True)
            embed.add_field(name="💰 Price/Night",  value=f"${price:.2f}", inline=True)
            embed.add_field(name="📝 Description",  value=description, inline=False)
            embed.add_field(name="📊 Status",       value="✅ Available", inline=True)
            embed.set_footer(text=f"Added by {ctx.author.display_name}")
            await ctx.send(embed=embed)
            log_action("ADD_ROOM", str(ctx.author), f"Room {room_number} ({room_type}) at ${price}/night")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")
        finally:
            cursor.close(); conn.close()

    @commands.command(name="rooms")
    async def list_rooms(self, ctx, status: str = "all"):
        """Usage: $rooms [all|available|occupied|maintenance]"""
        conn = get_connection(); cursor = conn.cursor()
        try:
            if status == "all":
                cursor.execute("SELECT room_number, room_type, status, price_per_night FROM rooms ORDER BY room_number")
            else:
                cursor.execute("SELECT room_number, room_type, status, price_per_night FROM rooms WHERE status=%s ORDER BY room_number", (status,))
            rows = cursor.fetchall()
            if not rows:
                await ctx.send(f"📭 No rooms found with status: **{status}**"); return
            e = {"available": "✅", "occupied": "🔴", "maintenance": "🔧"}
            lines = "\n".join(f"{e.get(r[2],'❓')} **Room {r[0]}** | {r[1]} | ${r[3]:.2f}/night | `{r[2].upper()}`" for r in rows)
            embed = discord.Embed(title="🏨 Hotel Room Directory",
                description=f"**{len(rows)}** room(s) — Filter: `{status}`\n\n{lines}",
                color=discord.Color.blue(), timestamp=datetime.utcnow())
            embed.set_footer(text="Grand Hotel Management System")
            await ctx.send(embed=embed)
        finally:
            cursor.close(); conn.close()

    @commands.command(name="roominfo")
    async def room_info(self, ctx, room_number: str):
        """Usage: $roominfo <room_number>"""
        conn = get_connection(); cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM rooms WHERE room_number=%s", (room_number,))
            row = cursor.fetchone()
            if not row:
                await ctx.send(f"❌ Room **{room_number}** not found."); return
            emoji = {"available": "✅", "occupied": "🔴", "maintenance": "🔧"}.get(row[3], "❓")
            embed = discord.Embed(title=f"🏨 Room {row[1]} — Details", color=discord.Color.gold(), timestamp=datetime.utcnow())
            embed.add_field(name="🛏️ Type",        value=row[2], inline=True)
            embed.add_field(name="📊 Status",       value=f"{emoji} {row[3].capitalize()}", inline=True)
            embed.add_field(name="💰 Price/Night",  value=f"${row[4]:.2f}", inline=True)
            embed.add_field(name="📝 Description",  value=row[5] or "N/A", inline=False)
            embed.add_field(name="🗓️ Added",        value=str(row[6])[:10], inline=True)
            embed.set_footer(text="Grand Hotel Management System")
            await ctx.send(embed=embed)
        finally:
            cursor.close(); conn.close()

    @commands.command(name="setstatus")
    @commands.has_permissions(administrator=True)
    async def set_status(self, ctx, room_number: str, new_status: str):
        """Usage: $setstatus <room_number> <available|occupied|maintenance>"""
        if new_status not in ["available", "occupied", "maintenance"]:
            await ctx.send("❌ Status must be: available | occupied | maintenance"); return
        conn = get_connection(); cursor = conn.cursor()
        try:
            cursor.execute("UPDATE rooms SET status=%s WHERE room_number=%s", (new_status, room_number))
            if cursor.rowcount == 0:
                await ctx.send(f"❌ Room **{room_number}** not found."); return
            conn.commit()
            emoji = {"available": "✅", "occupied": "🔴", "maintenance": "🔧"}[new_status]
            embed = discord.Embed(title="🔄 Room Status Updated", color=discord.Color.orange(), timestamp=datetime.utcnow())
            embed.add_field(name="🔢 Room",       value=room_number, inline=True)
            embed.add_field(name="📊 New Status", value=f"{emoji} {new_status.capitalize()}", inline=True)
            embed.set_footer(text=f"Updated by {ctx.author.display_name}")
            await ctx.send(embed=embed)
            log_action("SET_STATUS", str(ctx.author), f"Room {room_number} → {new_status}")
        finally:
            cursor.close(); conn.close()

    @commands.command(name="deleteroom")
    @commands.has_permissions(administrator=True)
    async def delete_room(self, ctx, room_number: str):
        """Usage: $deleteroom <room_number>"""
        conn = get_connection(); cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM rooms WHERE room_number=%s", (room_number,))
            if cursor.rowcount == 0:
                await ctx.send(f"❌ Room **{room_number}** not found."); return
            conn.commit()
            embed = discord.Embed(title="🗑️ Room Removed",
                description=f"Room **{room_number}** has been deleted.",
                color=discord.Color.red(), timestamp=datetime.utcnow())
            embed.set_footer(text=f"Removed by {ctx.author.display_name}")
            await ctx.send(embed=embed)
            log_action("DELETE_ROOM", str(ctx.author), f"Room {room_number} deleted")
        finally:
            cursor.close(); conn.close()

# ─────────────────────────────────────────────────────────
#  COG: RESERVATIONS
# ─────────────────────────────────────────────────────────

class Reservations(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="reserve")
    async def make_reservation(self, ctx, room_number: str, guest_name: str, check_in: str, check_out: str, *, notes: str = ""):
        """Usage: $reserve <room> <guest_name> <YYYY-MM-DD> <YYYY-MM-DD> [notes]"""
        conn = get_connection(); cursor = conn.cursor()
        try:
            cursor.execute("SELECT status, price_per_night FROM rooms WHERE room_number=%s", (room_number,))
            room = cursor.fetchone()
            if not room:
                await ctx.send(f"❌ Room **{room_number}** does not exist."); return
            if room[0] != "available":
                await ctx.send(f"❌ Room **{room_number}** is currently **{room[0]}**."); return
            ci     = datetime.strptime(check_in,  "%Y-%m-%d").date()
            co     = datetime.strptime(check_out, "%Y-%m-%d").date()
            nights = (co - ci).days
            if nights <= 0:
                await ctx.send("❌ Check-out must be after check-in."); return
            total = nights * float(room[1])
            cursor.execute(
                "INSERT INTO reservations (guest_name, guest_discord_id, room_number, check_in, check_out, total_price, notes) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (guest_name, str(ctx.author.id), room_number, ci, co, total, notes)
            )
            res_id = cursor.lastrowid
            cursor.execute("UPDATE rooms SET status='occupied' WHERE room_number=%s", (room_number,))
            conn.commit()
            embed = discord.Embed(title="✅ Reservation Confirmed", color=discord.Color.green(), timestamp=datetime.utcnow())
            embed.add_field(name="🆔 Booking ID",  value=f"#{res_id}",    inline=True)
            embed.add_field(name="👤 Guest",        value=guest_name,      inline=True)
            embed.add_field(name="🔢 Room",         value=room_number,     inline=True)
            embed.add_field(name="📅 Check-In",     value=check_in,        inline=True)
            embed.add_field(name="📅 Check-Out",    value=check_out,       inline=True)
            embed.add_field(name="🌙 Nights",       value=str(nights),     inline=True)
            embed.add_field(name="💰 Total",        value=f"${total:.2f}", inline=True)
            if notes: embed.add_field(name="📝 Notes", value=notes, inline=False)
            embed.set_footer(text=f"Booked by {ctx.author.display_name} • Grand Hotel")
            await ctx.send(embed=embed)
            log_action("RESERVATION", str(ctx.author), f"Room {room_number} for {guest_name} #{res_id}")
        except ValueError:
            await ctx.send("❌ Invalid date format. Use YYYY-MM-DD.")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")
        finally:
            cursor.close(); conn.close()

    @commands.command(name="reservations")
    async def list_reservations(self, ctx, status: str = "confirmed"):
        """Usage: $reservations [confirmed|checked_out|cancelled|all]"""
        conn = get_connection(); cursor = conn.cursor()
        try:
            if status == "all":
                cursor.execute("SELECT id, guest_name, room_number, check_in, check_out, total_price, status FROM reservations ORDER BY check_in DESC LIMIT 20")
            else:
                cursor.execute("SELECT id, guest_name, room_number, check_in, check_out, total_price, status FROM reservations WHERE status=%s ORDER BY check_in DESC LIMIT 20", (status,))
            rows = cursor.fetchall()
            if not rows:
                await ctx.send(f"📭 No reservations with status: **{status}**"); return
            se    = {"confirmed": "✅", "checked_out": "🏁", "cancelled": "❌"}
            lines = "\n".join(f"{se.get(r[6],'📌')} **#{r[0]}** | 👤 {r[1]} | Room {r[2]} | {r[3]} → {r[4]} | 💰 ${r[5]:.2f}" for r in rows)
            embed = discord.Embed(title="📅 Hotel Reservations",
                description=f"**{len(rows)}** booking(s) — Filter: `{status}`\n\n{lines}",
                color=discord.Color.blue(), timestamp=datetime.utcnow())
            embed.set_footer(text="Grand Hotel Management System")
            await ctx.send(embed=embed)
        finally:
            cursor.close(); conn.close()

    @commands.command(name="checkout")
    @commands.has_permissions(manage_guild=True)
    async def checkout(self, ctx, reservation_id: int):
        """Usage: $checkout <reservation_id>"""
        conn = get_connection(); cursor = conn.cursor()
        try:
            cursor.execute("SELECT guest_name, room_number, status FROM reservations WHERE id=%s", (reservation_id,))
            res = cursor.fetchone()
            if not res:
                await ctx.send(f"❌ Reservation **#{reservation_id}** not found."); return
            if res[2] != "confirmed":
                await ctx.send(f"❌ Already **{res[2]}**."); return
            cursor.execute("UPDATE reservations SET status='checked_out' WHERE id=%s", (reservation_id,))
            cursor.execute("UPDATE rooms SET status='available' WHERE room_number=%s", (res[1],))
            conn.commit()
            embed = discord.Embed(title="🏁 Guest Checked Out", color=discord.Color.teal(), timestamp=datetime.utcnow())
            embed.add_field(name="🆔 Booking", value=f"#{reservation_id}", inline=True)
            embed.add_field(name="👤 Guest",   value=res[0],               inline=True)
            embed.add_field(name="🔢 Room",    value=f"{res[1]} (now ✅ Available)", inline=True)
            embed.set_footer(text=f"Processed by {ctx.author.display_name}")
            await ctx.send(embed=embed)
            log_action("CHECKOUT", str(ctx.author), f"#{reservation_id} checked out, Room {res[1]} freed")
        finally:
            cursor.close(); conn.close()

    @commands.command(name="cancelreservation")
    @commands.has_permissions(manage_guild=True)
    async def cancel_reservation(self, ctx, reservation_id: int):
        """Usage: $cancelreservation <reservation_id>"""
        conn = get_connection(); cursor = conn.cursor()
        try:
            cursor.execute("SELECT guest_name, room_number, status FROM reservations WHERE id=%s", (reservation_id,))
            res = cursor.fetchone()
            if not res:
                await ctx.send(f"❌ Reservation **#{reservation_id}** not found."); return
            if res[2] == "cancelled":
                await ctx.send("❌ Already cancelled."); return
            cursor.execute("UPDATE reservations SET status='cancelled' WHERE id=%s", (reservation_id,))
            cursor.execute("UPDATE rooms SET status='available' WHERE room_number=%s", (res[1],))
            conn.commit()
            embed = discord.Embed(title="❌ Reservation Cancelled", color=discord.Color.red(), timestamp=datetime.utcnow())
            embed.add_field(name="🆔 Booking", value=f"#{reservation_id}", inline=True)
            embed.add_field(name="👤 Guest",   value=res[0],               inline=True)
            embed.add_field(name="🔢 Room",    value=f"{res[1]} (now ✅ Available)", inline=True)
            embed.set_footer(text=f"Cancelled by {ctx.author.display_name}")
            await ctx.send(embed=embed)
            log_action("CANCEL_RESERVATION", str(ctx.author), f"#{reservation_id} cancelled")
        finally:
            cursor.close(); conn.close()

# ─────────────────────────────────────────────────────────
#  COG: GUESTS
# ─────────────────────────────────────────────────────────

class Guests(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="addguest")
    @commands.has_permissions(manage_guild=True)
    async def add_guest(self, ctx, member: discord.Member, name: str, email: str = "N/A", phone: str = "N/A"):
        """Usage: $addguest @Member "Full Name" [email] [phone]"""
        conn = get_connection(); cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO guests (discord_id, name, email, phone) VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE name=%s, email=%s, phone=%s",
                (str(member.id), name, email, phone, name, email, phone)
            )
            conn.commit()
            embed = discord.Embed(title="👤 Guest Registered", color=discord.Color.green(), timestamp=datetime.utcnow())
            embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
            embed.add_field(name="👤 Name",    value=name,           inline=True)
            embed.add_field(name="🎮 Discord", value=member.mention, inline=True)
            embed.add_field(name="📧 Email",   value=email,          inline=True)
            embed.add_field(name="📞 Phone",   value=phone,          inline=True)
            embed.add_field(name="⭐ Points",  value="0",            inline=True)
            embed.add_field(name="👑 VIP",     value="No",           inline=True)
            embed.set_footer(text=f"Registered by {ctx.author.display_name}")
            await ctx.send(embed=embed)
            log_action("ADD_GUEST", str(ctx.author), f"Registered {name} ({member})")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")
        finally:
            cursor.close(); conn.close()

    @commands.command(name="removeguest")
    @commands.has_permissions(administrator=True)
    async def remove_guest(self, ctx, member: discord.Member):
        """Usage: $removeguest @Member"""
        conn = get_connection(); cursor = conn.cursor()
        try:
            cursor.execute("SELECT name FROM guests WHERE discord_id=%s", (str(member.id),))
            row = cursor.fetchone()
            if not row:
                await ctx.send(f"❌ {member.mention} is not in the guest registry."); return
            guest_name = row[0]
            cursor.execute("DELETE FROM guests WHERE discord_id=%s", (str(member.id),))
            conn.commit()
            embed = discord.Embed(title="🗑️ Guest Removed",
                description=f"**{guest_name}** ({member.mention}) has been removed from the guest registry.",
                color=discord.Color.red(), timestamp=datetime.utcnow())
            embed.set_footer(text=f"Removed by {ctx.author.display_name}")
            await ctx.send(embed=embed)
            log_action("REMOVE_GUEST", str(ctx.author), f"Removed guest {guest_name} ({member})")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")
        finally:
            cursor.close(); conn.close()

    @commands.command(name="guestinfo")
    async def guest_info(self, ctx, member: discord.Member = None):
        """Usage: $guestinfo [@Member]"""
        target = member or ctx.author
        conn = get_connection(); cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM guests WHERE discord_id=%s", (str(target.id),))
            guest = cursor.fetchone()
            if not guest:
                await ctx.send(f"❌ No profile for {target.mention}. Use `$addguest` first."); return
            cursor.execute("SELECT COUNT(*), SUM(total_price) FROM reservations WHERE guest_discord_id=%s AND status='checked_out'", (str(target.id),))
            stats = cursor.fetchone()
            embed = discord.Embed(title=f"👤 {guest[2]}", color=discord.Color.gold(), timestamp=datetime.utcnow())
            embed.set_thumbnail(url=target.avatar.url if target.avatar else None)
            embed.add_field(name="🎮 Discord",       value=target.mention,            inline=True)
            embed.add_field(name="📧 Email",          value=guest[3] or "N/A",         inline=True)
            embed.add_field(name="📞 Phone",          value=guest[4] or "N/A",         inline=True)
            embed.add_field(name="⭐ Loyalty Points", value=str(guest[5]),             inline=True)
            embed.add_field(name="👑 VIP",            value="✅ Yes" if guest[6] else "❌ No", inline=True)
            embed.add_field(name="🏨 Total Stays",    value=str(stats[0] or 0),        inline=True)
            embed.add_field(name="💰 Total Spent",    value=f"${stats[1] or 0:.2f}",   inline=True)
            embed.add_field(name="🗓️ Member Since",   value=str(guest[7])[:10],        inline=True)
            embed.set_footer(text="Grand Hotel Loyalty Program")
            await ctx.send(embed=embed)
        finally:
            cursor.close(); conn.close()

    @commands.command(name="addpoints")
    @commands.has_permissions(manage_guild=True)
    async def add_points(self, ctx, member: discord.Member, points: int):
        """Usage: $addpoints @Member <points>"""
        conn = get_connection(); cursor = conn.cursor()
        try:
            cursor.execute("UPDATE guests SET loyalty_points = loyalty_points + %s WHERE discord_id=%s", (points, str(member.id)))
            if cursor.rowcount == 0:
                await ctx.send("❌ Guest not found. Register with `$addguest` first."); return
            cursor.execute("SELECT loyalty_points FROM guests WHERE discord_id=%s", (str(member.id),))
            new_total = cursor.fetchone()[0]
            conn.commit()
            embed = discord.Embed(title="⭐ Loyalty Points Added", color=discord.Color.yellow(), timestamp=datetime.utcnow())
            embed.add_field(name="👤 Guest",    value=member.mention, inline=True)
            embed.add_field(name="➕ Added",    value=str(points),    inline=True)
            embed.add_field(name="🏆 New Total", value=str(new_total), inline=True)
            embed.set_footer(text=f"Added by {ctx.author.display_name}")
            await ctx.send(embed=embed)
            log_action("ADD_POINTS", str(ctx.author), f"+{points} pts to {member} (total: {new_total})")
        finally:
            cursor.close(); conn.close()

    @commands.command(name="setvip")
    @commands.has_permissions(administrator=True)
    async def set_vip(self, ctx, member: discord.Member, status: str = "true"):
        """Usage: $setvip @Member <true|false>"""
        vip = status.lower() in ["true", "yes", "1", "on"]
        conn = get_connection(); cursor = conn.cursor()
        try:
            cursor.execute("UPDATE guests SET vip_status=%s WHERE discord_id=%s", (vip, str(member.id)))
            if cursor.rowcount == 0:
                await ctx.send("❌ Guest not found."); return
            conn.commit()
            embed = discord.Embed(title="👑 VIP Status Updated", color=discord.Color.purple(), timestamp=datetime.utcnow())
            embed.add_field(name="👤 Guest", value=member.mention, inline=True)
            embed.add_field(name="👑 VIP",   value="✅ Granted" if vip else "❌ Removed", inline=True)
            embed.set_footer(text=f"Updated by {ctx.author.display_name}")
            await ctx.send(embed=embed)
            log_action("SET_VIP", str(ctx.author), f"{member} VIP → {vip}")
        finally:
            cursor.close(); conn.close()

# ─────────────────────────────────────────────────────────
#  COG: STAFF
# ─────────────────────────────────────────────────────────

class Staff(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="addstaff")
    @commands.has_permissions(administrator=True)
    async def add_staff(self, ctx, member: discord.Member, name: str, role: str, shift: str = "Day"):
        """Usage: $addstaff @Member "Name" "Role" [Day|Night|Evening]"""
        conn = get_connection(); cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO staff (discord_id, name, role, shift) VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE name=%s, role=%s, shift=%s",
                (str(member.id), name, role, shift, name, role, shift)
            )
            conn.commit()
            embed = discord.Embed(title="👷 Staff Member Added", color=discord.Color.green(), timestamp=datetime.utcnow())
            embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
            embed.add_field(name="👤 Name",    value=name,           inline=True)
            embed.add_field(name="🎮 Discord", value=member.mention, inline=True)
            embed.add_field(name="🏷️ Role",   value=role,           inline=True)
            embed.add_field(name="🕐 Shift",   value=shift,          inline=True)
            embed.set_footer(text=f"Added by {ctx.author.display_name}")
            await ctx.send(embed=embed)
            log_action("ADD_STAFF", str(ctx.author), f"Added {name} as {role} ({shift} shift)")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")
        finally:
            cursor.close(); conn.close()

    @commands.command(name="stafflist")
    @commands.has_permissions(manage_guild=True)
    async def staff_list(self, ctx):
        """Usage: $stafflist"""
        conn = get_connection(); cursor = conn.cursor()
        try:
            cursor.execute("SELECT discord_id, name, role, shift FROM staff ORDER BY role")
            rows = cursor.fetchall()
            if not rows:
                await ctx.send("📭 No staff registered yet."); return
            se    = {"Day": "☀️", "Night": "🌙", "Evening": "🌆"}
            lines = "\n".join(f"👤 **{s[1]}** | <@{s[0]}> | 🏷️ {s[2]} | {se.get(s[3],'🕐')} {s[3]}" for s in rows)
            embed = discord.Embed(title="👷 Hotel Staff Directory",
                description=f"Total Staff: **{len(rows)}**\n\n{lines}",
                color=discord.Color.blue(), timestamp=datetime.utcnow())
            embed.set_footer(text="Grand Hotel HR System")
            await ctx.send(embed=embed)
        finally:
            cursor.close(); conn.close()

    @commands.command(name="removestaff")
    @commands.has_permissions(administrator=True)
    async def remove_staff(self, ctx, member: discord.Member):
        """Usage: $removestaff @Member"""
        conn = get_connection(); cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM staff WHERE discord_id=%s", (str(member.id),))
            if cursor.rowcount == 0:
                await ctx.send(f"❌ {member.mention} is not in the staff registry."); return
            conn.commit()
            embed = discord.Embed(title="🗑️ Staff Member Removed",
                description=f"{member.mention} has been removed from the registry.",
                color=discord.Color.red(), timestamp=datetime.utcnow())
            embed.set_footer(text=f"Removed by {ctx.author.display_name}")
            await ctx.send(embed=embed)
            log_action("REMOVE_STAFF", str(ctx.author), f"Removed {member}")
        finally:
            cursor.close(); conn.close()

# ─────────────────────────────────────────────────────────
#  COG: MAINTENANCE
# ─────────────────────────────────────────────────────────

class Maintenance(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="reportissue")
    async def report_issue(self, ctx, room_number: str, priority: str, *, issue: str):
        """Usage: $reportissue <room_number> <low|normal|high|urgent> <description>"""
        if priority not in ["low", "normal", "high", "urgent"]:
            await ctx.send("❌ Priority must be: low | normal | high | urgent"); return
        conn = get_connection(); cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO maintenance (room_number, issue, priority, reported_by) VALUES (%s,%s,%s,%s)",
                (room_number, issue, priority, str(ctx.author))
            )
            ticket_id = cursor.lastrowid
            conn.commit()
            pe = {"low": "🟢", "normal": "🟡", "high": "🟠", "urgent": "🔴"}[priority]
            embed = discord.Embed(title="🔧 Maintenance Ticket Created", color=discord.Color.orange(), timestamp=datetime.utcnow())
            embed.add_field(name="🎫 Ticket ID",  value=f"#{ticket_id}", inline=True)
            embed.add_field(name="🔢 Room",        value=room_number,     inline=True)
            embed.add_field(name="⚠️ Priority",   value=f"{pe} {priority.capitalize()}", inline=True)
            embed.add_field(name="📝 Issue",       value=issue,           inline=False)
            embed.add_field(name="👤 Reported By", value=ctx.author.mention, inline=True)
            embed.add_field(name="📊 Status",      value="🔄 Open",      inline=True)
            embed.set_footer(text="Grand Hotel Maintenance System")
            await ctx.send(embed=embed)
            log_action("REPORT_ISSUE", str(ctx.author), f"Ticket #{ticket_id} Room {room_number}: {issue}")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")
        finally:
            cursor.close(); conn.close()

    @commands.command(name="maintenance")
    @commands.has_permissions(manage_guild=True)
    async def list_maintenance(self, ctx, status: str = "open"):
        """Usage: $maintenance [open|in_progress|resolved|all]"""
        conn = get_connection(); cursor = conn.cursor()
        try:
            if status == "all":
                cursor.execute("SELECT id, room_number, issue, priority, status FROM maintenance ORDER BY created_at DESC LIMIT 20")
            else:
                cursor.execute("SELECT id, room_number, issue, priority, status FROM maintenance WHERE status=%s ORDER BY created_at DESC LIMIT 20", (status,))
            rows = cursor.fetchall()
            if not rows:
                await ctx.send(f"📭 No tickets with status: **{status}**"); return
            pe    = {"low": "🟢", "normal": "🟡", "high": "🟠", "urgent": "🔴"}
            lines = "\n".join(f"{pe.get(r[3],'⚪')} **#{r[0]}** | Room {r[1]} | `{r[4]}` | {r[2][:60]}" for r in rows)
            embed = discord.Embed(title="🔧 Maintenance Tickets",
                description=f"**{len(rows)}** ticket(s) — Status: `{status}`\n\n{lines}",
                color=discord.Color.orange(), timestamp=datetime.utcnow())
            embed.set_footer(text="Grand Hotel Maintenance System")
            await ctx.send(embed=embed)
        finally:
            cursor.close(); conn.close()

    @commands.command(name="resolveissue")
    @commands.has_permissions(manage_guild=True)
    async def resolve_issue(self, ctx, ticket_id: int):
        """Usage: $resolveissue <ticket_id>"""
        conn = get_connection(); cursor = conn.cursor()
        try:
            cursor.execute("SELECT room_number, issue, status FROM maintenance WHERE id=%s", (ticket_id,))
            ticket = cursor.fetchone()
            if not ticket:
                await ctx.send(f"❌ Ticket **#{ticket_id}** not found."); return
            if ticket[2] == "resolved":
                await ctx.send(f"✅ Ticket **#{ticket_id}** is already resolved."); return
            cursor.execute("UPDATE maintenance SET status='resolved', resolved_at=NOW() WHERE id=%s", (ticket_id,))
            conn.commit()
            embed = discord.Embed(title="✅ Ticket Resolved", color=discord.Color.green(), timestamp=datetime.utcnow())
            embed.add_field(name="🎫 Ticket", value=f"#{ticket_id}", inline=True)
            embed.add_field(name="🔢 Room",   value=ticket[0],       inline=True)
            embed.add_field(name="📝 Issue",  value=ticket[1],       inline=False)
            embed.set_footer(text=f"Resolved by {ctx.author.display_name}")
            await ctx.send(embed=embed)
            log_action("RESOLVE_ISSUE", str(ctx.author), f"Ticket #{ticket_id} resolved")
        finally:
            cursor.close(); conn.close()

# ─────────────────────────────────────────────────────────
#  COG: ADMIN
# ─────────────────────────────────────────────────────────

class Admin(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="dashboard")
    @commands.has_permissions(manage_guild=True)
    async def dashboard(self, ctx):
        """Usage: $dashboard"""
        conn = get_connection(); cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM rooms");                                        total_rooms = cursor.fetchone()[0]
            cursor.execute("SELECT status, COUNT(*) FROM rooms GROUP BY status");                room_stats  = {r[0]: r[1] for r in cursor.fetchall()}
            cursor.execute("SELECT COUNT(*) FROM reservations WHERE status='confirmed'");        active_res  = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM reservations WHERE DATE(check_in)=CURDATE()"); checkins    = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM reservations WHERE DATE(check_out)=CURDATE()");checkouts   = cursor.fetchone()[0]
            cursor.execute("SELECT SUM(total_price) FROM reservations WHERE status='checked_out'"); revenue = cursor.fetchone()[0] or 0
            cursor.execute("SELECT COUNT(*) FROM guests");                                       guests      = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM staff");                                        staff       = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM maintenance WHERE status='open'");              open_t      = cursor.fetchone()[0]
            occupancy = (room_stats.get("occupied", 0) / total_rooms * 100) if total_rooms else 0
            embed = discord.Embed(title="🏨 Grand Hotel — Live Dashboard", color=discord.Color.gold(), timestamp=datetime.utcnow())
            embed.add_field(name="🏨 Total Rooms",    value=str(total_rooms),                  inline=True)
            embed.add_field(name="✅ Available",       value=str(room_stats.get("available",0)),inline=True)
            embed.add_field(name="🔴 Occupied",        value=str(room_stats.get("occupied",0)), inline=True)
            embed.add_field(name="🔧 Maintenance",     value=str(room_stats.get("maintenance",0)), inline=True)
            embed.add_field(name="📊 Occupancy Rate",  value=f"{occupancy:.1f}%",              inline=True)
            embed.add_field(name="📅 Active Bookings", value=str(active_res),                  inline=True)
            embed.add_field(name="━━ TODAY ━━",        value="━━━━━━━━",                       inline=False)
            embed.add_field(name="📥 Check-Ins",       value=str(checkins),                    inline=True)
            embed.add_field(name="📤 Check-Outs",      value=str(checkouts),                   inline=True)
            embed.add_field(name="🔧 Open Tickets",    value=str(open_t),                      inline=True)
            embed.add_field(name="━━ TOTALS ━━",       value="━━━━━━━━",                       inline=False)
            embed.add_field(name="💰 Total Revenue",   value=f"${revenue:,.2f}",               inline=True)
            embed.add_field(name="👤 Guests",          value=str(guests),                      inline=True)
            embed.add_field(name="👷 Staff",           value=str(staff),                       inline=True)
            embed.set_footer(text="Grand Hotel Management System • Live Data")
            await ctx.send(embed=embed)
        finally:
            cursor.close(); conn.close()

    @commands.command(name="activitylog")
    @commands.has_permissions(administrator=True)
    async def activity_log(self, ctx, limit: int = 10):
        """Usage: $activitylog [limit]"""
        conn = get_connection(); cursor = conn.cursor()
        try:
            cursor.execute("SELECT action, performed_by, details, created_at FROM bot_log ORDER BY created_at DESC LIMIT %s", (limit,))
            rows = cursor.fetchall()
            if not rows:
                await ctx.send("📭 No activity logged yet."); return
            lines = "\n\n".join(f"`{str(r[3])[:16]}` | **{r[0]}** by {r[1]}\n> {r[2][:80]}" for r in rows)
            embed = discord.Embed(title="📜 Activity Log",
                description=f"Last **{len(rows)}** actions\n\n{lines}",
                color=discord.Color.dark_blue(), timestamp=datetime.utcnow())
            embed.set_footer(text="Grand Hotel Audit System")
            await ctx.send(embed=embed)
        finally:
            cursor.close(); conn.close()

    @commands.command(name="announce")
    @commands.has_permissions(administrator=True)
    async def announce(self, ctx, *, message: str):
        """Usage: $announce <message>"""
        embed = discord.Embed(title="📢 Official Hotel Announcement", description=message,
            color=discord.Color.dark_gold(), timestamp=datetime.utcnow())
        embed.set_author(name="Grand Hotel Management", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        embed.set_footer(text=f"Posted by {ctx.author.display_name}")
        await ctx.send(embed=embed)

    @commands.command(name="hotelhelp")
    async def hotel_help(self, ctx):
        """Usage: $hotelhelp"""
        embed = discord.Embed(
            title="🏨 Grand Hotel Bot — Command Guide",
            description="Prefix: `$`  |  Dates format: `YYYY-MM-DD`",
            color=discord.Color.blue(), timestamp=datetime.utcnow()
        )
        embed.add_field(name="🏨 Rooms",
            value="`$addroom <room> <type> <price> [desc]`\n`$rooms [status]`\n`$roominfo <room>`\n`$setstatus <room> <status>`\n`$deleteroom <room>`",
            inline=False)
        embed.add_field(name="📅 Reservations",
            value="`$reserve <room> <name> <in> <out> [notes]`\n`$reservations [status]`\n`$checkout <id>`\n`$cancelreservation <id>`",
            inline=False)
        embed.add_field(name="👤 Guests",
            value="`$addguest @Member <name> [email] [phone]`\n`$removeguest @Member`\n`$guestinfo [@Member]`\n`$addpoints @Member <pts>`\n`$setvip @Member <true|false>`",
            inline=False)
        embed.add_field(name="👷 Staff",
            value="`$addstaff @Member <name> <role> [shift]`\n`$stafflist`\n`$removestaff @Member`",
            inline=False)
        embed.add_field(name="🔧 Maintenance",
            value="`$reportissue <room> <priority> <desc>`\n`$maintenance [status]`\n`$resolveissue <id>`",
            inline=False)
        embed.add_field(name="🛡️ Admin",
            value="`$dashboard`\n`$activitylog [n]`\n`$announce <message>`",
            inline=False)
        embed.add_field(name="🔍 Search & Billing",
            value="`$search <name | room | YYYY-MM-DD>`\n`$billing <reservation_id>`\n`$billing @Member`",
            inline=False)
        embed.add_field(name="📊 Reports",
            value="`$report weekly`\n`$report monthly`",
            inline=False)
        embed.set_footer(text="Grand Hotel Management System • discord.py")
        await ctx.send(embed=embed)

# ─────────────────────────────────────────────────────────
#  COG: SEARCH
# ─────────────────────────────────────────────────────────

class Search(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="search")
    async def search(self, ctx, *, query: str):
        """Usage: $search <guest name | room number | YYYY-MM-DD>"""
        conn = get_connection(); cursor = conn.cursor()
        try:
            is_date = False
            try:
                datetime.strptime(query.strip(), "%Y-%m-%d")
                is_date = True
            except ValueError:
                pass

            if is_date:
                cursor.execute("""
                    SELECT id, guest_name, room_number, check_in, check_out, total_price, status
                    FROM reservations
                    WHERE check_in = %s OR check_out = %s
                    ORDER BY check_in DESC LIMIT 15
                """, (query.strip(), query.strip()))
                title = f"🔍 Search Results for date: `{query}`"
            else:
                like = f"%{query}%"
                cursor.execute("""
                    SELECT id, guest_name, room_number, check_in, check_out, total_price, status
                    FROM reservations
                    WHERE guest_name LIKE %s OR room_number LIKE %s
                    ORDER BY check_in DESC LIMIT 15
                """, (like, like))
                title = f"🔍 Search Results for: `{query}`"

            rows = cursor.fetchall()
            if not rows:
                await ctx.send(f"📭 No reservations found matching **{query}**."); return

            se = {"confirmed": "✅", "checked_out": "🏁", "cancelled": "❌"}
            lines = "\n".join(
                f"{se.get(r[6],'📌')} **#{r[0]}** | 👤 {r[1]} | Room {r[2]} | 📅 {r[3]} → {r[4]} | 💰 ${r[5]:.2f} | `{r[6]}`"
                for r in rows
            )
            embed = discord.Embed(title=title,
                description=f"**{len(rows)}** result(s)\n\n{lines}",
                color=discord.Color.blurple(), timestamp=datetime.utcnow())
            embed.set_footer(text="Grand Hotel Management System — use $billing <id> for full details")
            await ctx.send(embed=embed)
        finally:
            cursor.close(); conn.close()

# ─────────────────────────────────────────────────────────
#  COG: BILLING
# ─────────────────────────────────────────────────────────

class Billing(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="billing")
    async def billing(self, ctx, target: str):
        """Usage: $billing <reservation_id>  OR  $billing @Member"""
        conn = get_connection(); cursor = conn.cursor()
        try:
            member = ctx.message.mentions[0] if ctx.message.mentions else None

            if member:
                discord_id = str(member.id)
                cursor.execute("""
                    SELECT id, room_number, check_in, check_out, total_price, status
                    FROM reservations WHERE guest_discord_id = %s
                    ORDER BY check_in DESC LIMIT 20
                """, (discord_id,))
                rows = cursor.fetchall()
                cursor.execute("""
                    SELECT COUNT(*), SUM(total_price) FROM reservations
                    WHERE guest_discord_id = %s AND status = 'checked_out'
                """, (discord_id,))
                totals = cursor.fetchone()
                cursor.execute("SELECT name, loyalty_points, vip_status FROM guests WHERE discord_id = %s", (discord_id,))
                guest_row = cursor.fetchone()
                if not rows:
                    await ctx.send(f"📭 No billing records found for {member.mention}."); return
                se = {"confirmed": "✅", "checked_out": "🏁", "cancelled": "❌"}
                lines = "\n".join(
                    f"{se.get(r[5],'📌')} **#{r[0]}** | Room {r[1]} | {r[2]} → {r[3]} | 💰 ${r[4]:.2f}"
                    for r in rows
                )
                embed = discord.Embed(
                    title=f"💳 Billing History — {guest_row[0] if guest_row else member.display_name}",
                    color=discord.Color.gold(), timestamp=datetime.utcnow())
                embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
                embed.add_field(name="🎮 Discord",        value=member.mention,                         inline=True)
                embed.add_field(name="✅ Completed Stays", value=str(totals[0] or 0),                    inline=True)
                embed.add_field(name="💰 Total Spent",     value=f"${totals[1] or 0:.2f}",              inline=True)
                if guest_row:
                    embed.add_field(name="⭐ Loyalty Points", value=str(guest_row[1]),                  inline=True)
                    embed.add_field(name="👑 VIP",            value="✅ Yes" if guest_row[2] else "❌ No", inline=True)
                embed.add_field(name="📋 All Reservations", value=lines or "None",                       inline=False)
                embed.set_footer(text="Grand Hotel Billing System")
                await ctx.send(embed=embed)
            else:
                try:
                    res_id = int(target)
                except ValueError:
                    await ctx.send("❌ Usage: `$billing <reservation_id>` or `$billing @Member`"); return
                cursor.execute("""
                    SELECT r.id, r.guest_name, r.guest_discord_id, r.room_number,
                           r.check_in, r.check_out, r.total_price, r.status, r.notes,
                           rm.room_type, rm.price_per_night
                    FROM reservations r
                    LEFT JOIN rooms rm ON r.room_number = rm.room_number
                    WHERE r.id = %s
                """, (res_id,))
                row = cursor.fetchone()
                if not row:
                    await ctx.send(f"❌ Reservation **#{res_id}** not found."); return
                ci     = row[4]; co = row[5]
                nights = (co - ci).days
                pn     = float(row[10]) if row[10] else 0
                total  = float(row[6]) if row[6] else 0
                se     = {"confirmed": "✅ Confirmed", "checked_out": "🏁 Checked Out", "cancelled": "❌ Cancelled"}
                embed = discord.Embed(title=f"💳 Invoice — Booking #{row[0]}",
                    color=discord.Color.green() if row[7] == "confirmed" else discord.Color.greyple(),
                    timestamp=datetime.utcnow())
                embed.add_field(name="👤 Guest",      value=row[1],                             inline=True)
                embed.add_field(name="🎮 Discord ID", value=f"<@{row[2]}>" if row[2] else "N/A", inline=True)
                embed.add_field(name="📊 Status",     value=se.get(row[7], row[7]),             inline=True)
                embed.add_field(name="🔢 Room",       value=row[3],                             inline=True)
                embed.add_field(name="🛏️ Room Type", value=row[9] or "N/A",                    inline=True)
                embed.add_field(name="💵 Rate/Night", value=f"${pn:.2f}",                       inline=True)
                embed.add_field(name="📅 Check-In",   value=str(ci),                            inline=True)
                embed.add_field(name="📅 Check-Out",  value=str(co),                            inline=True)
                embed.add_field(name="🌙 Nights",     value=str(nights),                        inline=True)
                embed.add_field(name="━━ TOTAL ━━",   value=f"**${total:.2f}**",                inline=False)
                if row[8]:
                    embed.add_field(name="📝 Notes",  value=row[8],                             inline=False)
                embed.set_footer(text="Grand Hotel Billing System")
                await ctx.send(embed=embed)
        finally:
            cursor.close(); conn.close()

# ─────────────────────────────────────────────────────────
#  COG: REPORTS
# ─────────────────────────────────────────────────────────

class Reports(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="report")
    @commands.has_permissions(manage_guild=True)
    async def report(self, ctx, period: str = "weekly"):
        """Usage: $report [weekly|monthly]"""
        period = period.lower()
        if period not in ["weekly", "monthly"]:
            await ctx.send("❌ Period must be `weekly` or `monthly`."); return
        conn = get_connection(); cursor = conn.cursor()
        try:
            interval = "7 DAY" if period == "weekly" else "30 DAY"
            label    = "Last 7 Days" if period == "weekly" else "Last 30 Days"

            cursor.execute(f"SELECT COUNT(*), COALESCE(SUM(total_price),0) FROM reservations WHERE status='checked_out' AND check_out >= CURDATE() - INTERVAL {interval}")
            total_count, total_revenue = cursor.fetchone(); total_revenue = float(total_revenue)

            cursor.execute(f"""
                SELECT rm.room_type, COUNT(*), COALESCE(SUM(r.total_price),0)
                FROM reservations r JOIN rooms rm ON r.room_number=rm.room_number
                WHERE r.status='checked_out' AND r.check_out >= CURDATE() - INTERVAL {interval}
                GROUP BY rm.room_type ORDER BY 3 DESC
            """)
            room_type_rows = cursor.fetchall()

            cursor.execute("SELECT COUNT(*) FROM rooms")
            total_rooms = cursor.fetchone()[0]
            cursor.execute(f"""
                SELECT COUNT(DISTINCT room_number) FROM reservations
                WHERE status IN ('confirmed','checked_out') AND check_in<=CURDATE() AND check_out>=CURDATE()-INTERVAL {interval}
            """)
            occupied_rooms  = cursor.fetchone()[0]
            occupancy_rate  = (occupied_rooms / total_rooms * 100) if total_rooms else 0

            cursor.execute(f"SELECT COUNT(*) FROM reservations WHERE created_at >= NOW() - INTERVAL {interval}")
            new_bookings = cursor.fetchone()[0]

            cursor.execute(f"SELECT COUNT(*) FROM reservations WHERE status='cancelled' AND created_at >= NOW() - INTERVAL {interval}")
            cancellations = cursor.fetchone()[0]

            cursor.execute(f"""
                SELECT guest_name, COUNT(*), COALESCE(SUM(total_price),0)
                FROM reservations WHERE status='checked_out' AND check_out >= CURDATE() - INTERVAL {interval}
                GROUP BY guest_name ORDER BY 3 DESC LIMIT 5
            """)
            top_guests = cursor.fetchall()

            embed = discord.Embed(
                title=f"📊 Grand Hotel — {period.capitalize()} Report",
                description=f"{'📆' if period=='monthly' else '🗓️'} Period: **{label}**",
                color=discord.Color.dark_gold(), timestamp=datetime.utcnow())
            embed.add_field(name="💰 Revenue",        value=f"**${total_revenue:,.2f}**", inline=True)
            embed.add_field(name="🏁 Checkouts",      value=str(total_count),             inline=True)
            embed.add_field(name="📋 New Bookings",   value=str(new_bookings),            inline=True)
            embed.add_field(name="📊 Occupancy Rate", value=f"{occupancy_rate:.1f}%",     inline=True)
            embed.add_field(name="❌ Cancellations",  value=str(cancellations),           inline=True)
            embed.add_field(name="🏨 Total Rooms",    value=str(total_rooms),             inline=True)

            if room_type_rows:
                max_rev = float(room_type_rows[0][2]) if room_type_rows else 1
                lines = []
                for rt, stays, rev in room_type_rows:
                    rev = float(rev)
                    bar = "█" * max(1, round((rev/max_rev)*10) if max_rev > 0 else 0) + "░" * (10 - max(1, round((rev/max_rev)*10) if max_rev > 0 else 0))
                    lines.append(f"`{bar}` **{rt}** — {stays} stay(s) — ${rev:,.2f}")
                embed.add_field(name="🛏️ Revenue by Room Type", value="\n".join(lines), inline=False)
            else:
                embed.add_field(name="🛏️ Revenue by Room Type", value="No data for this period.", inline=False)

            if top_guests:
                medals = ["🥇","🥈","🥉","4️⃣","5️⃣"]
                embed.add_field(name="🏆 Top Guests by Spend",
                    value="\n".join(f"{medals[i]} **{g[0]}** — {g[1]} stay(s) — ${float(g[2]):,.2f}" for i,g in enumerate(top_guests)),
                    inline=False)
            else:
                embed.add_field(name="🏆 Top Guests by Spend", value="No completed stays in this period.", inline=False)

            embed.set_footer(text=f"Grand Hotel Analytics • {period.capitalize()} Report")
            await ctx.send(embed=embed)
        finally:
            cursor.close(); conn.close()

# ─────────────────────────────────────────────────────────
#  TKINTER DASHBOARD  (python bot.py --gui)
# ─────────────────────────────────────────────────────────

def launch_dashboard():
    try:
        import tkinter as tk
        from tkinter import ttk, scrolledtext
    except ImportError:
        print("❌ Tkinter is not available. Install it or run without --gui."); return

    DARK_BG  = "#1a1a2e"; PANEL_BG = "#16213e"; ACCENT   = "#0f3460"
    ACCENT2  = "#1a1a4e"; TEXT     = "#e0e0e0"; TEXT_DIM = "#888888"
    SUCCESS  = "#27ae60"; DANGER   = "#e74c3c"; WARNING  = "#f39c12"; GOLD = "#f1c40f"

    root = tk.Tk()
    root.title("Grand Hotel Management Dashboard")
    root.geometry("1200x700"); root.configure(bg=DARK_BG); root.minsize(900, 550)

    header = tk.Frame(root, bg=ACCENT, height=56); header.pack(fill="x"); header.pack_propagate(False)
    tk.Label(header, text="Grand Hotel Management System", font=("Segoe UI", 16, "bold"), bg=ACCENT, fg=TEXT).pack(side="left", padx=20, pady=10)
    tk.Label(header, text="discord.py  |  MySQL", font=("Segoe UI", 10), bg=ACCENT, fg=TEXT_DIM).pack(side="right", padx=20)

    sidebar = tk.Frame(root, bg=PANEL_BG, width=200); sidebar.pack(side="left", fill="y"); sidebar.pack_propagate(False)
    tk.Label(sidebar, text="NAVIGATION", font=("Segoe UI", 8, "bold"), bg=PANEL_BG, fg=TEXT_DIM).pack(pady=(15, 5), padx=15, anchor="w")

    content = tk.Frame(root, bg=DARK_BG); content.pack(side="left", fill="both", expand=True, padx=10, pady=10)
    pages   = {}
    current_page = {"key": "dashboard"}

    def make_page(key, title):
        frame = tk.Frame(content, bg=DARK_BG); pages[key] = frame
        tk.Label(frame, text=title, font=("Segoe UI", 18, "bold"), bg=DARK_BG, fg=TEXT).pack(anchor="w", pady=(0, 10))
        return frame

    def make_tree(parent, cols, heads):
        style = ttk.Style(); style.theme_use("clam")
        style.configure("H.Treeview", background=PANEL_BG, foreground=TEXT, fieldbackground=PANEL_BG, rowheight=28, font=("Segoe UI", 10))
        style.configure("H.Treeview.Heading", background=ACCENT2, foreground=TEXT, font=("Segoe UI", 10, "bold"))
        style.map("H.Treeview", background=[("selected", ACCENT)])
        wrap = tk.Frame(parent, bg=DARK_BG)
        tree = ttk.Treeview(wrap, columns=cols, show="headings", style="H.Treeview")
        for c, h in zip(cols, heads):
            tree.heading(c, text=h); tree.column(c, width=120, anchor="center")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True); vsb.pack(side="right", fill="y")
        return wrap, tree

    # Dashboard page
    dash_page  = make_page("dashboard", "Hotel Dashboard")
    cards_row  = tk.Frame(dash_page, bg=DARK_BG); cards_row.pack(fill="x")
    stat_labels = {}
    for title, color in [("Total Rooms", ACCENT2), ("Available", SUCCESS), ("Occupied", DANGER),
                          ("Maintenance", WARNING), ("Reservations", GOLD), ("Open Tickets", WARNING),
                          ("Guests", "#9b59b6"), ("Staff", "#3498db")]:
        card = tk.Frame(cards_row, bg=PANEL_BG, width=135, height=90)
        card.pack(side="left", padx=5, pady=5); card.pack_propagate(False)
        tk.Frame(card, bg=color, height=4).pack(fill="x")
        lbl = tk.Label(card, text="0", font=("Segoe UI", 26, "bold"), bg=PANEL_BG, fg=color)
        lbl.pack(pady=(6, 0))
        tk.Label(card, text=title, font=("Segoe UI", 8), bg=PANEL_BG, fg=TEXT_DIM).pack()
        stat_labels[title] = lbl
    rev_frame = tk.Frame(dash_page, bg=PANEL_BG); rev_frame.pack(fill="x", pady=10)
    tk.Frame(rev_frame, bg=GOLD, height=4).pack(fill="x")
    rev_lbl = tk.Label(rev_frame, text="Total Revenue: $0.00", font=("Segoe UI", 14, "bold"), bg=PANEL_BG, fg=GOLD)
    rev_lbl.pack(pady=10, padx=20, anchor="w")

    # Other pages
    rooms_page = make_page("rooms", "Room Management")
    _, rooms_tree = make_tree(rooms_page, ("room_number","type","status","price","desc"), ("Room #","Type","Status","Price/Night","Description"))

    res_page = make_page("reservations", "Reservations")
    _, res_tree = make_tree(res_page, ("id","guest","room","check_in","check_out","total","status"), ("ID","Guest","Room","Check-In","Check-Out","Total","Status"))

    guests_page = make_page("guests", "Guest Profiles")
    _, guests_tree = make_tree(guests_page, ("name","discord","email","phone","points","vip","joined"), ("Name","Discord ID","Email","Phone","Points","VIP","Joined"))

    staff_page = make_page("staff", "Staff Directory")
    _, staff_tree = make_tree(staff_page, ("name","discord","role","shift","added"), ("Name","Discord ID","Role","Shift","Added"))

    maint_page = make_page("maintenance", "Maintenance Tickets")
    _, maint_tree = make_tree(maint_page, ("id","room","issue","priority","status","by","created"), ("ID","Room","Issue","Priority","Status","Reported By","Created"))

    logs_page = make_page("logs", "Activity Log")
    log_box   = scrolledtext.ScrolledText(logs_page, bg=PANEL_BG, fg=TEXT, font=("Consolas", 10), relief="flat", state="disabled")

    for pg, tw in [(rooms_page, rooms_tree), (res_page, res_tree), (guests_page, guests_tree), (staff_page, staff_tree), (maint_page, maint_tree)]:
        tw.master.pack(fill="both", expand=True)
    log_box.pack(fill="both", expand=True)

    bar = tk.Frame(root, bg=ACCENT2, height=28); bar.pack(fill="x", side="bottom"); bar.pack_propagate(False)
    status_lbl = tk.Label(bar, text="Ready", font=("Segoe UI", 9), bg=ACCENT2, fg=TEXT_DIM)
    status_lbl.pack(side="left", padx=15)
    tk.Label(bar, text="Grand Hotel Management  |  discord.py", font=("Segoe UI", 9), bg=ACCENT2, fg=TEXT_DIM).pack(side="right", padx=15)

    def set_status(msg): status_lbl.config(text=msg)

    def load_dashboard():
        try:
            conn = get_connection(); cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM rooms");                                              total = cur.fetchone()[0]
            cur.execute("SELECT status, COUNT(*) FROM rooms GROUP BY status");                     rs    = {r[0]: r[1] for r in cur.fetchall()}
            cur.execute("SELECT COUNT(*) FROM reservations WHERE status='confirmed'");             ar    = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM maintenance WHERE status='open'");                   ot    = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM guests");                                             g     = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM staff");                                              s     = cur.fetchone()[0]
            cur.execute("SELECT SUM(total_price) FROM reservations WHERE status='checked_out'");   rev   = cur.fetchone()[0] or 0.0
            cur.close(); conn.close()
            for k, v in [("Total Rooms", total), ("Available", rs.get("available", 0)),
                          ("Occupied", rs.get("occupied", 0)), ("Maintenance", rs.get("maintenance", 0)),
                          ("Reservations", ar), ("Open Tickets", ot), ("Guests", g), ("Staff", s)]:
                stat_labels[k].config(text=str(v))
            rev_lbl.config(text=f"Total Revenue (All Time): ${rev:,.2f}")
            set_status("Dashboard loaded successfully")
        except Exception as e:
            set_status(f"DB Error: {e}")

    def load_table(tree, query, transform=None):
        try:
            conn = get_connection(); cur = conn.cursor()
            cur.execute(query); rows = cur.fetchall(); cur.close(); conn.close()
            for i in tree.get_children(): tree.delete(i)
            for r in rows:
                row = list(r)
                if transform: row = transform(row)
                tree.insert("", "end", values=row)
            set_status(f"{len(rows)} records loaded")
        except Exception as e:
            set_status(f"Error: {e}")

    def load_logs():
        try:
            conn = get_connection(); cur = conn.cursor()
            cur.execute("SELECT action, performed_by, details, created_at FROM bot_log ORDER BY created_at DESC LIMIT 100")
            rows = cur.fetchall(); cur.close(); conn.close()
            log_box.config(state="normal"); log_box.delete("1.0", "end")
            for r in rows:
                log_box.insert("end", f"[{str(r[3])[:16]}]  {r[0]:30s}  by {r[1]}\n  -> {r[2]}\n\n")
            log_box.config(state="disabled")
            set_status(f"{len(rows)} log entries loaded")
        except Exception as e:
            set_status(f"Error: {e}")

    loaders = {
        "dashboard":    load_dashboard,
        "rooms":        lambda: load_table(rooms_tree, "SELECT room_number, room_type, status, price_per_night, description FROM rooms ORDER BY room_number"),
        "reservations": lambda: load_table(res_tree, "SELECT id, guest_name, room_number, check_in, check_out, total_price, status FROM reservations ORDER BY check_in DESC LIMIT 50"),
        "guests":       lambda: load_table(guests_tree, "SELECT name, discord_id, email, phone, loyalty_points, vip_status, created_at FROM guests ORDER BY name",
                                            lambda r: r[:5] + ["VIP" if r[5] else "--"] + [str(r[6])[:10]]),
        "staff":        lambda: load_table(staff_tree, "SELECT name, discord_id, role, shift, added_at FROM staff ORDER BY role",
                                            lambda r: r[:4] + [str(r[4])[:10]]),
        "maintenance":  lambda: load_table(maint_tree, "SELECT id, room_number, issue, priority, status, reported_by, created_at FROM maintenance ORDER BY created_at DESC LIMIT 50",
                                            lambda r: r[:6] + [str(r[6])[:10]]),
        "logs":         load_logs,
    }

    nav_btns = {}
    def navigate(key):
        current_page["key"] = key
        for p in pages.values(): p.pack_forget()
        pages[key].pack(fill="both", expand=True)
        for k, b in nav_btns.items():
            b.config(bg=ACCENT if k == key else PANEL_BG)
        if key in loaders: loaders[key]()

    nav_items = [
        ("Dashboard",    "dashboard"),
        ("Rooms",        "rooms"),
        ("Reservations", "reservations"),
        ("Guests",       "guests"),
        ("Staff",        "staff"),
        ("Maintenance",  "maintenance"),
        ("Activity Log", "logs"),
    ]
    for label, key in nav_items:
        b = tk.Button(sidebar, text=label, font=("Segoe UI", 11), bg=PANEL_BG, fg=TEXT,
                      activebackground=ACCENT, activeforeground=TEXT, relief="flat",
                      anchor="w", padx=15, pady=8, cursor="hand2",
                      command=lambda k=key: navigate(k))
        b.pack(fill="x", padx=8, pady=2); nav_btns[key] = b

    tk.Frame(sidebar, bg=ACCENT2, height=1).pack(fill="x", padx=10, pady=10)
    tk.Button(sidebar, text="Refresh", font=("Segoe UI", 10), bg=ACCENT2, fg=TEXT,
              relief="flat", padx=10, pady=6, cursor="hand2",
              command=lambda: loaders[current_page["key"]]()).pack(fill="x", padx=8, pady=2)
    tk.Button(sidebar, text="Start Bot", font=("Segoe UI", 10, "bold"), bg=ACCENT, fg=TEXT,
              relief="flat", padx=10, pady=6, cursor="hand2",
              command=lambda: threading.Thread(
                  target=lambda: asyncio.run(run_bot()), daemon=True).start()
              ).pack(fill="x", padx=8, pady=4)

    navigate("dashboard")
    root.mainloop()

# ─────────────────────────────────────────────────────────
#  BOT RUNNER
# ─────────────────────────────────────────────────────────

ALL_COGS = [Rooms, Reservations, Guests, Staff, Maintenance, Admin, Search, Billing, Reports]

async def run_bot():
    async with bot:
        validate_environment()
        try:
            setup_database()
        except Exception as e:
            print(f"WARNING: Could not connect to MySQL: {e}")
            print("Bot will start but database commands will fail.")
        for cog in ALL_COGS:
            await bot.add_cog(cog(bot))
            print(f"  Loaded cog: {cog.__name__}")
        await bot.start(DISCORD_TOKEN)

# ─────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Grand Hotel Management Bot")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    if "--nogui" in sys.argv:
        print("  Starting Discord Bot (headless)...")
        asyncio.run(run_bot())
    else:
        print("  Launching Tkinter Dashboard...")
        launch_dashboard()
