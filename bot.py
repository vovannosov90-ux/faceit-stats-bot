import os
import json
import sqlite3
import threading
from urllib.request import Request, urlopen
from urllib.parse import quote
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# ============================================================
# НАСТРОЙКИ
# ============================================================

TOKEN = os.getenv("TOKEN")
FACEIT_API_KEY = os.getenv("FACEIT_API_KEY")

FACEIT_API_URL = "https://open.faceit.com/data/v4"

MAX_PLAYERS = 10
DB_NAME = "cs_team.db"


# ============================================================
# ПРОВЕРКА НАСТРОЕК
# ============================================================

if not TOKEN:
    raise RuntimeError("Не найдена переменная TOKEN")

if not FACEIT_API_KEY:
    raise RuntimeError("Не найдена переменная FACEIT_API_KEY")


# ============================================================
# DATABASE
# ============================================================

def init_db():
    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS players (
            telegram_id INTEGER PRIMARY KEY,
            nickname TEXT NOT NULL,
            faceit_id TEXT
        )
        """
    )

    conn.commit()
    conn.close()


def save_player(telegram_id, nickname, faceit_id):
    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR REPLACE INTO players
        (telegram_id, nickname, faceit_id)
        VALUES (?, ?, ?)
        """,
        (
            telegram_id,
            nickname,
            faceit_id,
        ),
    )

    conn.commit()
    conn.close()


def get_saved_player(telegram_id):
    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT nickname, faceit_id
        FROM players
        WHERE telegram_id = ?
        """,
        (telegram_id,),
    )

    row = cursor.fetchone()

    conn.close()

    if not row:
        return None

    return {
        "nickname": row[0],
        "faceit_id": row[1],
    }


# ============================================================
# FACEIT API
# ============================================================

def faceit_get(endpoint):

    url = FACEIT_API_URL + endpoint

    print()
    print("========================================")
    print("FACEIT API REQUEST")
    print("URL:", url)
    print("========================================")

    try:

        request = Request(
            url,
            headers={
                "Authorization": f"Bearer {FACEIT_API_KEY}",
                "Accept": "application/json",
            },
            method="GET",
        )

        with urlopen(request, timeout=20) as response:

            data = response.read().decode("utf-8")

            print("STATUS:", response.status)

            print("RESPONSE:")
            print(data[:5000])

            print("========================================")
            print()

            return json.loads(data)

    except Exception as e:

        print()
        print("========================================")
        print("FACEIT API ERROR")
        print("URL:", url)
        print("ERROR:", repr(e))
        print("========================================")
        print()

        raise


# ============================================================
# PLAYER
# ============================================================

def get_player(nickname):

    endpoint = f"/players?nickname={quote(nickname)}"

    return faceit_get(endpoint)


# ============================================================
# MATCHES
# ============================================================

def get_matches(player_id, limit=100):

    endpoint = (
        f"/players/{player_id}/history"
        f"?game=cs2"
        f"&limit={limit}"
    )

    data = faceit_get(endpoint)

    return data.get("items", [])


# ============================================================
# PLAYER MATCH STATS
# ============================================================

def get_player_match_stats(player_id):

    endpoint = f"/players/{player_id}/games/cs2/stats"

    data = faceit_get(endpoint)

    return data.get("items", [])


# ============================================================
# MATCH DETAILS
# ============================================================

def get_match_details(match_id):

    endpoint = f"/matches/{match_id}"

    return faceit_get(endpoint)


# ============================================================
# MATCH STATS
# ============================================================

def get_match_stats(match_id):

    endpoint = f"/matches/{match_id}/stats"

    return faceit_get(endpoint)


# ============================================================
# DEBUG MATCH RATING
# ============================================================

def debug_match_rating(matches):

    if not matches:
        print("DEBUG RATING: нет матчей")
        return

    test_match_id = matches[0].get("match_id")

    if not test_match_id:
        print("DEBUG RATING: match_id не найден")
        return

    try:

        test_match = get_match_details(test_match_id)

        print()
        print("========== FACEIT MATCH RATING DEBUG ==========")
        print("MATCH ID:", test_match_id)
        print()

        print("TEAMS:")

        teams = test_match.get("teams", {})

        print(
            json.dumps(
                teams,
                ensure_ascii=False,
                indent=2,
            )[:30000]
        )

        print()
        print("================================================")
        print()

    except Exception as e:

        print(
            "Ошибка получения match details:",
            repr(e),
        )


# ============================================================
# DEBUG MATCH STATS
# ============================================================

def debug_match_stats(matches):

    if not matches:
        print("DEBUG MATCH STATS: нет матчей")
        return

    test_match_id = matches[0].get("match_id")

    if not test_match_id:
        print("DEBUG MATCH STATS: match_id не найден")
        return

    try:

        stats = get_match_stats(test_match_id)

        print()
        print("========== FACEIT MATCH STATS DEBUG ==========")
        print("MATCH ID:", test_match_id)
        print()

        print(
            json.dumps(
                stats,
                ensure_ascii=False,
                indent=2,
            )[:30000]
        )

        print()
        print("==============================================")
        print()

    except Exception as e:

        print(
            "Ошибка получения match stats:",
            repr(e),
        )


# ============================================================
# DEBUG PLAYER STATS
# ============================================================

def debug_player_stats(player_id):

    try:

        stats = get_player_match_stats(player_id)

        print()
        print("========== FACEIT PLAYER STATS DEBUG ==========")
        print("PLAYER ID:", player_id)
        print()

        print(
            json.dumps(
                stats[:3],
                ensure_ascii=False,
                indent=2,
            )[:30000]
        )

        print()
        print("===============================================")
        print()

    except Exception as e:

        print(
            "Ошибка получения player stats:",
            repr(e),
        )


# ============================================================
# ANALYZE PLAYER STATS
# ============================================================

def analyze_player_stats(player_id, limit=100):

    matches = get_matches(
        player_id,
        limit=limit,
    )

    player_stats = get_player_match_stats(
        player_id
    )

    print()
    print("========== ANALYZE ==========")
    print("MATCHES:", len(matches))
    print("PLAYER STATS:", len(player_stats))
    print("==============================")
    print()

    # --------------------------------------------------------
    # DEBUG
    # --------------------------------------------------------

    debug_match_rating(matches)

    debug_match_stats(matches)

    debug_player_stats(player_id)

    # --------------------------------------------------------
    # СТАТИСТИКА
    # --------------------------------------------------------

    kills = 0
    deaths = 0

    wins = 0
    losses = 0

    processed = 0

    ratings = []

    for item in player_stats[:limit]:

        stats = item.get("stats", {})

        # Иногда FACEIT отдаёт:
        #
        # "stats": {
        #     "stats": {...}
        # }
        #
        # Поэтому проверяем оба варианта.

        if (
            isinstance(stats, dict)
            and isinstance(stats.get("stats"), dict)
        ):
            stats = stats["stats"]

        if not isinstance(stats, dict):
            continue

        processed += 1

        # ----------------------------------------------------
        # KILLS
        # ----------------------------------------------------

        try:

            kills_value = int(
                stats.get("Kills", 0)
            )

            kills += kills_value

        except Exception:
            pass

        # ----------------------------------------------------
        # DEATHS
        # ----------------------------------------------------

        try:

            deaths_value = int(
                stats.get("Deaths", 0)
            )

            deaths += deaths_value

        except Exception:
            pass

        # ----------------------------------------------------
        # RESULT
        # ----------------------------------------------------

        result = str(
            stats.get("Result", "")
        )

        if result == "1":
            wins += 1

        elif result == "0":
            losses += 1

        # ----------------------------------------------------
        # RATING
        # ----------------------------------------------------

        rating = stats.get("Rating")

        if rating is not None:

            try:
                ratings.append(
                    float(rating)
                )
            except Exception:
                pass

    # --------------------------------------------------------
    # KD
    # --------------------------------------------------------

    if deaths > 0:

        kd = kills / deaths

    else:

        kd = 0

    # --------------------------------------------------------
    # WINRATE
    # --------------------------------------------------------

    total_results = wins + losses

    if total_results > 0:

        winrate = (
            wins / total_results
        ) * 100

    else:

        winrate = 0

    # --------------------------------------------------------
    # RATING
    # --------------------------------------------------------

    if ratings:

        average_rating = (
            sum(ratings) / len(ratings)
        )

        best_rating = max(ratings)

    else:

        average_rating = None
        best_rating = None

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    return {
        "matches": len(matches),
        "processed": processed,

        "kills": kills,
        "deaths": deaths,
        "kd": kd,

        "wins": wins,
        "losses": losses,
        "winrate": winrate,

        "ratings": ratings,
        "average_rating": average_rating,
        "best_rating": best_rating,
    }


# ============================================================
# TELEGRAM KEYBOARD
# ============================================================

def main_keyboard():

    keyboard = [
        [
            "📊 Моя статистика",
        ],
        [
            "👤 Мой профиль",
        ],
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
    )


# ============================================================
# START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(
        "🎮 FACEIT Stats Bot\n\n"
        "Отправь свой FACEIT nickname.\n\n"
        "После этого я смогу показывать "
        "твою статистику CS2.",
        reply_markup=main_keyboard(),
    )


# ============================================================
# SET NICKNAME
# ============================================================

async def handle_nickname(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    text = update.message.text.strip()

    if text.startswith("📊"):
        await show_stats(
            update,
            context,
        )
        return

    if text.startswith("👤"):
        player = get_saved_player(
            update.effective_user.id
        )

        if not player:

            await update.message.reply_text(
                "❌ Профиль ещё не сохранён.\n\n"
                "Просто отправь свой FACEIT nickname."
            )

            return

        await update.message.reply_text(
            f"👤 FACEIT профиль\n\n"
            f"Nickname: {player['nickname']}\n"
            f"ID: {player['faceit_id']}",
            reply_markup=main_keyboard(),
        )

        return

    nickname = text

    await update.message.reply_text(
        "⏳ Ищу игрока на FACEIT..."
    )

    try:

        player_data = get_player(
            nickname
        )

        # ----------------------------------------------------
        # Пытаемся получить ID
        # ----------------------------------------------------

        player_id = player_data.get(
            "player_id"
        )

        real_nickname = player_data.get(
            "nickname",
            nickname,
        )

        if not player_id:

            await update.message.reply_text(
                "❌ FACEIT не вернул player_id.\n\n"
                "Проверь nickname."
            )

            return

        save_player(
            update.effective_user.id,
            real_nickname,
            player_id,
        )

        await update.message.reply_text(
            f"✅ Игрок найден!\n\n"
            f"🎮 {real_nickname}\n"
            f"🆔 {player_id}\n\n"
            f"Теперь нажми «📊 Моя статистика».",
            reply_markup=main_keyboard(),
        )

    except Exception as e:

        print()
        print("========== PLAYER ERROR ==========")
        print(repr(e))
        print("==================================")
        print()

        await update.message.reply_text(
            "❌ Не удалось найти игрока.\n\n"
            "Проверь nickname и попробуй ещё раз."
        )


# ============================================================
# SHOW STATS
# ============================================================

async def show_stats(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    player = get_saved_player(
        update.effective_user.id
    )

    if not player:

        await update.message.reply_text(
            "❌ Сначала отправь свой FACEIT nickname.",
            reply_markup=main_keyboard(),
        )

        return

    nickname = player["nickname"]
    player_id = player["faceit_id"]

    await update.message.reply_text(
        "FACEIT Stats:\n"
        "⏳ Загружаю статистику..."
    )

    try:

        result = analyze_player_stats(
            player_id,
            limit=100,
        )

        # ----------------------------------------------------
        # RATING
        # ----------------------------------------------------

        ratings = result["ratings"]

        count_180 = sum(
            1
            for x in ratings
            if x >= 1.80
        )

        count_170 = sum(
            1
            for x in ratings
            if x >= 1.70
        )

        count_160 = sum(
            1
            for x in ratings
            if x >= 1.60
        )

        count_150 = sum(
            1
            for x in ratings
            if x >= 1.50
        )

        average_rating = (
            result["average_rating"]
        )

        best_rating = (
            result["best_rating"]
        )

        if average_rating is not None:

            average_rating_text = (
                f"{average_rating:.2f}"
            )

        else:

            average_rating_text = "—"

        if best_rating is not None:

            best_rating_text = (
                f"{best_rating:.2f}"
            )

        else:

            best_rating_text = "—"

        # ----------------------------------------------------
        # MESSAGE
        # ----------------------------------------------------

        message = (
            f"🎮 FACEIT Stats — {nickname}\n\n"

            f"📊 Последних матчей: "
            f"{result['matches']}\n"

            f"🔎 Обработано матчей: "
            f"{result['processed']}\n\n"

            f"🔥 Rating ≥ 1.80: "
            f"{count_180}\n"

            f"⚡ Rating ≥ 1.70: "
            f"{count_170}\n"

            f"📈 Rating ≥ 1.60: "
            f"{count_160}\n"

            f"📊 Rating ≥ 1.50: "
            f"{count_150}\n\n"

            f"📈 Средний Rating: "
            f"{average_rating_text}\n"

            f"🚀 Лучший Rating: "
            f"{best_rating_text}\n\n"

            f"🎯 K/D: "
            f"{result['kd']:.2f}\n"

            f"🔫 Kills: "
            f"{result['kills']}\n"

            f"💀 Deaths: "
            f"{result['deaths']}\n\n"

            f"🏆 Победы: "
            f"{result['wins']}\n"

            f"💀 Поражения: "
            f"{result['losses']}\n"

            f"📌 Winrate: "
            f"{result['winrate']:.1f}%"
        )

        await update.message.reply_text(
            message,
            reply_markup=main_keyboard(),
        )

    except Exception as e:

        print()
        print("========================================")
        print("STATS ERROR")
        print("ERROR:", repr(e))
        print("========================================")
        print()

        await update.message.reply_text(
            "FACEIT Stats:\n\n"
            "❌ Не удалось получить статистику.\n\n"
            "Проверь логи Render."
        )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):

    print()
    print("========== TELEGRAM ERROR ==========")
    print(repr(context.error))
    print("====================================")
    print()


# ============================================================
# HEALTH SERVER
# ============================================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        self.send_response(200)

        self.send_header(
            "Content-type",
            "text/plain",
        )

        self.end_headers()

        self.wfile.write(
            b"FACEIT Stats Bot is alive"
        )

    def log_message(
        self,
        format,
        *args,
    ):

        return


def start_health_server():

    port = int(
        os.getenv(
            "PORT",
            "10000",
        )
    )

    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler,
    )

    print(
        f"Health server started on port {port}"
    )

    server.serve_forever()


# ============================================================
# MAIN
# ============================================================

def main():

    init_db()

    # --------------------------------------------------------
    # HEALTH SERVER
    # --------------------------------------------------------

    health_thread = threading.Thread(
        target=start_health_server,
        daemon=True,
    )

    health_thread.start()

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_nickname,
        )
    )

    application.add_error_handler(
        error_handler
    )

    print()
    print("==============================")
    print("FACEIT Stats Bot started")
    print("==============================")
    print()

    application.run_polling(
        drop_pending_updates=True
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
