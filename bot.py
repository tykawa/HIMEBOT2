import os
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from threading import Thread

import discord
from discord.ext import commands
from flask import Flask

# =========================
# 基本設定
# =========================

BOT_NAME = "姫様マネージャー"
JST = timezone(timedelta(hours=9))
DB_PATH = "hime_bot.db"

# 管理者ロール名（必要なら変更）
ADMIN_ROLE_NAMES = {"管理者", "Admin", "姫教幹部"}

# Render系でWebサービスとして起動したい場合の簡易サーバー
app = Flask(__name__)

@app.route("/")
def home():
    return f"{BOT_NAME} is alive!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# =========================
# DB初期化
# =========================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            user_name TEXT NOT NULL,
            points INTEGER NOT NULL DEFAULT 0,
            last_worship_date TEXT,
            last_rebellion_date TEXT
        )
    """)

    conn.commit()
    conn.close()


def get_conn():
    return sqlite3.connect(DB_PATH)


def ensure_user(user_id: int, user_name: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()

    if row is None:
        cur.execute(
            "INSERT INTO users (user_id, user_name, points) VALUES (?, ?, 0)",
            (user_id, user_name)
        )
    else:
        cur.execute(
            "UPDATE users SET user_name = ? WHERE user_id = ?",
            (user_name, user_id)
        )

    conn.commit()
    conn.close()


def get_user_data(user_id: int):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT user_id, user_name, points, last_worship_date, last_rebellion_date
        FROM users
        WHERE user_id = ?
    """, (user_id,))
    row = cur.fetchone()

    conn.close()
    return row


def add_points(user_id: int, user_name: str, amount: int):
    ensure_user(user_id, user_name)

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        UPDATE users
        SET points = points + ?, user_name = ?
        WHERE user_id = ?
    """, (amount, user_name, user_id))

    conn.commit()
    conn.close()


def remove_points(user_id: int, user_name: str, amount: int):
    ensure_user(user_id, user_name)

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    current_points = row[0] if row else 0

    new_points = max(0, current_points - amount)

    cur.execute("""
        UPDATE users
        SET points = ?, user_name = ?
        WHERE user_id = ?
    """, (new_points, user_name, user_id))

    conn.commit()
    conn.close()

    return current_points, new_points


def set_last_worship(user_id: int, date_str: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        UPDATE users
        SET last_worship_date = ?
        WHERE user_id = ?
    """, (date_str, user_id))

    conn.commit()
    conn.close()


def set_last_rebellion(user_id: int, date_str: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        UPDATE users
        SET last_rebellion_date = ?
        WHERE user_id = ?
    """, (date_str, user_id))

    conn.commit()
    conn.close()


def get_top_users(limit: int = 10):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT user_id, user_name, points
        FROM users
        ORDER BY points DESC, user_id ASC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()

    conn.close()
    return rows


def today_jst_str():
    return datetime.now(JST).strftime("%Y-%m-%d")


def has_admin_permission(ctx):
    # サーバー管理権限を持っている人
    if ctx.author.guild_permissions.administrator:
        return True

    # 指定ロール名を持っている人
    author_role_names = {role.name for role in ctx.author.roles}
    if ADMIN_ROLE_NAMES & author_role_names:
        return True

    return False


# =========================
# Discord Bot設定
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


@bot.event
async def on_ready():
    print(f"{BOT_NAME} 起動完了: {bot.user}")


# =========================
# コマンド
# =========================

@bot.command(name="礼拝")
async def worship(ctx):
    user = ctx.author
    ensure_user(user.id, user.display_name)

    user_data = get_user_data(user.id)
    today = today_jst_str()
    last_worship_date = user_data[3]

    if last_worship_date == today:
        await ctx.send(
            f"**{user.mention}** よ、本日の礼拝はすでに済んでおります。\n"
            "姫様は信徒の勤勉さをきちんと見ておられます。明日また礼を尽くしなさい。"
        )
        return

    gained = random.randint(10, 20)
    add_points(user.id, user.display_name, gained)
    set_last_worship(user.id, today)

    updated = get_user_data(user.id)
    total = updated[2]

    messages = [
        f"**{user.mention}** は厳かに礼拝を行った。\n姫様の加護により **{gained} 姫ポイント** を獲得した！\n現在の所持ポイント: **{total}**",
        f"**{user.mention}** は今日も姫様への忠誠を示した。\nその敬虔さを讃え、**{gained} 姫ポイント** が授けられた！\n現在の所持ポイント: **{total}**",
        f"**{user.mention}** の礼拝は無事受理された。\n姫様は微笑み、**{gained} 姫ポイント** を与えた。\n現在の所持ポイント: **{total}**"
    ]
    await ctx.send(random.choice(messages))


@bot.command(name="ランキング")
async def ranking(ctx):
    top_users = get_top_users(10)

    if not top_users:
        await ctx.send("まだ誰も姫ポイントを所持していません。まずは礼拝から始めましょう。")
        return

    embed = discord.Embed(
        title="👑 姫ポイントランキング",
        description="姫様に最も忠実なる信徒たち",
        color=discord.Color.purple()
    )

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    lines = []
    for i, (_, user_name, points) in enumerate(top_users, start=1):
        icon = medals.get(i, f"{i}位")
        lines.append(f"{icon} **{user_name}** - {points} pt")

    embed.add_field(name="順位", value="\n".join(lines), inline=False)
    await ctx.send(embed=embed)


@bot.command(name="付与")
async def grant_points(ctx, amount: int, member: discord.Member):
    if not has_admin_permission(ctx):
        await ctx.send("このコマンドは姫様に認められし管理者のみ使用できます。")
        return

    if amount <= 0:
        await ctx.send("付与するポイントは1以上にしてください。")
        return

    add_points(member.id, member.display_name, amount)
    updated = get_user_data(member.id)
    total = updated[2]

    await ctx.send(
        f"姫様の御心により、**{member.mention}** に **{amount} 姫ポイント** が付与されました。\n"
        f"現在の所持ポイント: **{total}**"
    )


@bot.command(name="剥奪")
async def revoke_points(ctx, amount: int, member: discord.Member):
    if not has_admin_permission(ctx):
        await ctx.send("このコマンドは姫様に認められし管理者のみ使用できます。")
        return

    if amount <= 0:
        await ctx.send("剥奪するポイントは1以上にしてください。")
        return

    before, after = remove_points(member.id, member.display_name, amount)

    await ctx.send(
        f"姫様の裁定により、**{member.mention}** から **{amount} 姫ポイント** が剥奪されました。\n"
        f"所持ポイント: **{before} → {after}**"
    )


@bot.command(name="反逆")
async def rebellion(ctx):
    user = ctx.author
    ensure_user(user.id, user.display_name)

    user_data = get_user_data(user.id)
    today = today_jst_str()
    last_rebellion_date = user_data[4]

    if last_rebellion_date == today:
        await ctx.send(
            f"**{user.mention}** よ、反逆は1日1回までです。\n"
            "姫様は何度も同じ無礼を受けるほど暇ではありません。"
        )
        return

    set_last_rebellion(user.id, today)

    success = random.random() < 0.20  # 成功率20%

    if success:
        add_points(user.id, user.display_name, 100)
        updated = get_user_data(user.id)
        total = updated[2]

        messages = [
            f"⚔️ **{user.mention}** は姫様への反逆を試み……見事成功した！\n"
            f"混乱に乗じて **100 姫ポイント** を奪取！\n現在の所持ポイント: **{total}**",
            f"⚔️ **{user.mention}** の反逆は意外にも成就した。\n"
            f"大胆不敵なる行いにより **100 姫ポイント** を獲得！\n現在の所持ポイント: **{total}**"
        ]
        await ctx.send(random.choice(messages))
    else:
        messages = [
            f"⚔️ **{user.mention}** は姫様への反逆を試みたが失敗した。\n"
            "しかし寛大なる姫様はこれを許し、罪を問わなかった。",
            f"⚔️ **{user.mention}** の反逆は姫様の前にあっけなく潰えた。\n"
            "だが姫様は慈悲深く、敗者に赦しを与えた。",
            f"⚔️ **{user.mention}** は反逆に失敗した。\n"
            "それでも姫様は寛大であり、今回に限り許しを与えられた。"
        ]
        await ctx.send(random.choice(messages))


@bot.command(name="ヘルプ")
async def help_command(ctx):
    embed = discord.Embed(
        title="姫様マネージャー コマンド一覧",
        description="姫教の運営を補佐する神聖なるBotです。",
        color=discord.Color.gold()
    )

    embed.add_field(
        name="一般コマンド",
        value=(
            "`!礼拝` - 1日1回、10〜20姫ポイント獲得\n"
            "`!ランキング` - 所持ポイント上位10名を表示\n"
            "`!反逆` - 1日1回、成功で100ポイント"
        ),
        inline=False
    )

    embed.add_field(
        name="管理者コマンド",
        value=(
            "`!付与 数字 @ユーザー` - ポイント付与\n"
            "`!剥奪 数字 @ユーザー` - ポイント剥奪"
        ),
        inline=False
    )

    await ctx.send(embed=embed)


# =========================
# 起動
# =========================

def main():
    token = os.environ.get("MTQ4NTcxMjEwMzU3ODAxMzc0Ng.Ghc-Fu.4gNXO4ZRPkg_VmES_rxmECqiodtYVJ2xQTLbKI")
    if not token:
        raise ValueError("環境変数 DISCORD_TOKEN が設定されていません。")

    init_db()

    # Webサーバーを別スレッドで起動（Webサービス型ホスティング向け）
    Thread(target=run_web, daemon=True).start()

    bot.run(token)


if __name__ == "__main__":
    main()
