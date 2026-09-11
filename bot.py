import os
import json
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.request import Request, urlopen
from urllib.parse import quote

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# =========================================================
# НАСТРОЙКИ
# =========================================================

TOKEN = os.getenv("TOKEN")
FACEIT_API_KEY = os.getenv("FACEIT_API_KEY")

MAX_PLAYERS = 10
DB_NAME = "cs_team.db"

FACEIT_API_URL = "https://open.faceit.com/data/v4"


# =========================================================
# ПРОВЕРКА ENV
# =========================================================

if not TOKEN:
    raise RuntimeError("Не задан TOKEN")

if not FACEIT_API_KEY:
    raise RuntimeError("Не задан FACEIT_API_KEY")


# =========================================================
# DATABASE
# =========================================================

def init_db():
    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            telegram_id INTEGER PRIMARY KEY,
            nickname TEXT NOT NULL,
            faceit_id TEXT
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# FACEIT API
# =========================================================

def faceit_get(endpoint):
    url = FACEIT_API_URL + endpoint

    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {FACEIT_API_KEY}",
            "Accept": "application/json",
        },
    )

    with urlopen(request, timeout=20) as response:
        data = response.read().decode("utf-8")

    return json.loads(data)


# =========================================================
# PLAYER
# =========================================================

def get_player(nickname):

    endpoint = f"/players?nickname={quote(nickname)}"

    data = faceit_get(endpoint)

    return data


# =========================================================
# MATCH HISTORY
# =========================================================

def get_matches(player_id, limit=100):

    endpoint = (
        f"/players/{player_id}/games/cs2/matches"
        f"?offset=0&limit={limit}"
    )

    return faceit_get(endpoint)


# =========================================================
# PLAYER MATCH STATS
# =========================================================

def get_player_match_stats(player_id):

    endpoint = f"/players/{player_id}/games/cs2/stats"

    return faceit_get(endpoint)


# =========================================================
# MATCH DETAILS
# =========================================================

def get_match_details(match_id):

    endpoint = f"/matches/{match_id}"

    return faceit_get(endpoint)


# =========================================================
# MATCH STATS
# =========================================================

def get_match_stats(match_id):

    endpoint = f"/matches/{match_id}/stats"

    return faceit_get(endpoint)


# =========================================================
# DEBUG MATCH RATING
#
# САМОЕ ВАЖНОЕ:
# смотрим teams -> stats -> rating
# =========================================================

def debug_match_rating(matches):

    if not matches:
        return

    test_match_id = matches[0].get("match_id")

    if not test_match_id:
        print("DEBUG: match_id не найден")
        return

    try:

        test_match = get_match_details(test_match_id)

        print()
        print(
            "========== FACEIT MATCH RATING DEBUG =========="
        )

        print(
            "MATCH ID:",
            test_match_id
        )

        print()
        print("TEAMS:")

        teams = test_match.get(
            "teams",
            {}
        )

        print(
            json.dumps(
                teams,
                ensure_ascii=False,
                indent=2
            )[:30000]
        )

        print(
            "================================================"
        )

        print()

    except Exception as e:

        print(
            "Ошибка получения match details:",
            e
        )


# =========================================================
# DEBUG MATCH STATS
# =========================================================

def debug_match_stats(matches):

    if not matches:
        return

    test_match_id = matches[0].get("match_id")

    if not test_match_id:
        return

    try:

        stats = get_match_stats(test_match_id)

        print()
        print(
            "========== FACEIT MATCH STATS DEBUG =========="
        )

        print(
            "MATCH ID:",
            test_match_id
        )

        print()

        print(
            json.dumps(
                stats,
                ensure_ascii=False,
                indent=2
            )[:30000]
        )

        print(
            "================================================"
        )

        print()

    except Exception as e:

        print(
            "Ошибка получения match stats:",
            e
        )


# =========================================================
# DEBUG PLAYER STATS
# =========================================================

def debug_player_stats(player_id):

    try:

        stats = get_player_match_stats(player_id)

        print()
        print(
            "========== FACEIT PLAYER STATS =========="
        )

        print(
            json.dumps(
                stats,
                ensure_ascii=False,
                indent=2
            )[:30000]
        )

        print(
            "=========================================="
        )

        print()

    except Exception as e:

        print(
            "Ошибка получения player stats:",
            e
        )


# =========================================================
# NORMALIZE STATS
# =========================================================

def normalize_stats(item):

    stats = item.get("stats", {})

    # Иногда FACEIT возвращает:
    #
    # {
    #     "stats": {
    #         "stats": {
    #             ...
    #         }
    #     }
    # }

    if (
        isinstance(stats, dict)
        and isinstance(stats.get("stats"), dict)
    ):
        stats = stats["stats"]

    return stats


# =========================================================
# ANALYZE PLAYER STATS
# =========================================================

def analyze_player_stats(stats_data):

    total_kills = 0
    total_deaths = 0

    wins = 0
    losses = 0

    processed = 0

    ratings = []

    for item in stats_data:

        stats = normalize_stats(item)

        if not isinstance(stats, dict):
            continue

        processed += 1

        # -------------------------
        # KILLS
        # -------------------------

        try:
            kills = int(
                float(
                    stats.get("Kills", 0)
                )
            )
        except:
            kills = 0

        # -------------------------
        # DEATHS
        # -------------------------

        try:
            deaths = int(
                float(
                    stats.get("Deaths", 0)
                )
            )
        except:
            deaths = 0

        total_kills += kills
        total_deaths += deaths

        # -------------------------
        # RESULT
        # -------------------------

        result = str(
            stats.get("Result", "")
        )

        if result == "1":
            wins += 1

        elif result == "0":
            losses += 1

        # -------------------------
        # RATING
        # -------------------------

        rating_value = (
            stats.get("Rating")
            or stats.get("rating")
        )

        if rating_value is not None:

            try:

                rating = float(
                    rating_value
                )

                ratings.append(
                    rating
                )

            except:
                pass

    # =====================================================
    # CALCULATIONS
    # =====================================================

    if total_deaths > 0:

        kd = (
            total_kills /
            total_deaths
        )

    else:

        kd = 0

    if ratings:

        average_rating = (
            sum(ratings) /
            len(ratings)
        )

        best_rating = max(
            ratings
        )

    else:

        average_rating = None
        best_rating = None

    return {
        "processed": processed,
        "kills": total_kills,
        "deaths": total_deaths,
        "kd": kd,
        "wins": wins,
        "losses": losses,
        "ratings": ratings,
        "average_rating": average_rating,
        "best_rating": best_rating,
    }


# =========================================================
# TELEGRAM KEYBOARD
# =========================================================

keyboard = [
    [
        "📊 Моя статистика",
    ],
    [
        "➕ Добавить игрока",
    ],
]


reply_markup = ReplyKeyboardMarkup(
    keyboard,
    resize_keyboard=True
)


# =========================================================
# START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🎮 FACEIT Stats Bot\n\n"
        "Добавь свой FACEIT ник и я покажу статистику.",
        reply_markup=reply_markup
    )


# =========================================================
# ADD PLAYER
# =========================================================

async def add_player(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "Напиши свой FACEIT ник.\n\n"
        "Например:\n"
        "TheRasca1"
    )

    context.user_data["waiting_nickname"] = True


# =========================================================
# SAVE PLAYER
# =========================================================

def save_player(
    telegram_id,
    nickname,
    faceit_id
):

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
            faceit_id
        )
    )

    conn.commit()
    conn.close()


# =========================================================
# GET SAVED PLAYER
# =========================================================

def get_saved_player(telegram_id):

    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT nickname, faceit_id
        FROM players
        WHERE telegram_id = ?
        """,
        (telegram_id,)
    )

    row = cursor.fetchone()

    conn.close()

    return row


# =========================================================
# HANDLE TEXT
# =========================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    text = update.message.text.strip()

    telegram_id = update.effective_user.id

    # =====================================================
    # ADD NICKNAME
    # =====================================================

    if context.user_data.get(
        "waiting_nickname"
    ):

        nickname = text

        context.user_data[
            "waiting_nickname"
        ] = False

        await update.message.reply_text(
            "🔎 Ищу игрока на FACEIT..."
        )

        try:

            data = get_player(
                nickname
            )

            player = data.get(
                "player"
            )

            if not player:

                # Иногда API может вернуть
                # игрока напрямую

                if (
                    isinstance(
                        data,
                        dict
                    )
                    and data.get("player_id")
                ):
                    player = data

            if not player:

                await update.message.reply_text(
                    "❌ Игрок не найден."
                )

                return

            faceit_id = player.get(
                "player_id"
            )

            real_nickname = player.get(
                "nickname",
                nickname
            )

            if not faceit_id:

                await update.message.reply_text(
                    "❌ Не удалось получить FACEIT ID."
                )

                return

            save_player(
                telegram_id,
                real_nickname,
                faceit_id
            )

            await update.message.reply_text(
                f"✅ Игрок сохранён:\n\n"
                f"🎮 {real_nickname}",
                reply_markup=reply_markup
            )

        except Exception as e:

            print(
                "Ошибка поиска игрока:",
                e
            )

            await update.message.reply_text(
                "❌ Ошибка при обращении к FACEIT API."
            )

        return

    # =====================================================
    # MY STATS
    # =====================================================

    if text == "📊 Моя статистика":

        saved = get_saved_player(
            telegram_id
        )

        if not saved:

            await update.message.reply_text(
                "❌ Сначала добавь FACEIT ник.",
                reply_markup=reply_markup
            )

            return

        nickname, faceit_id = saved

        await update.message.reply_text(
            "⏳ Загружаю статистику..."
        )

        try:

            # =================================================
            # MATCH HISTORY
            # =================================================

            matches_data = get_matches(
                faceit_id,
                100
            )

            matches = matches_data.get(
                "items",
                []
            )

            # =================================================
            # DEBUG MATCH RATING
            # =================================================

            debug_match_rating(
                matches
            )

            # =================================================
            # DEBUG MATCH STATS
            # =================================================

            debug_match_stats(
                matches
            )

            # =================================================
            # PLAYER STATS
            # =================================================

            stats_data = (
                get_player_match_stats(
                    faceit_id
                )
            )

            # =================================================
            # DEBUG PLAYER STATS
            # =================================================

            debug_player_stats(
                faceit_id
            )

            # =================================================
            # ANALYZE
            # =================================================

            result = analyze_player_stats(
                stats_data
            )

            processed = result[
                "processed"
            ]

            kills = result[
                "kills"
            ]

            deaths = result[
                "deaths"
            ]

            kd = result[
                "kd"
            ]

            wins = result[
                "wins"
            ]

            losses = result[
                "losses"
            ]

            ratings = result[
                "ratings"
            ]

            average_rating = result[
                "average_rating"
            ]

            best_rating = result[
                "best_rating"
            ]

            # =================================================
            # RATING THRESHOLDS
            # =================================================

            rating_180 = sum(
                1
                for r in ratings
                if r >= 1.80
            )

            rating_170 = sum(
                1
                for r in ratings
                if r >= 1.70
            )

            rating_160 = sum(
                1
                for r in ratings
                if r >= 1.60
            )

            rating_150 = sum(
                1
                for r in ratings
                if r >= 1.50
            )

            # =================================================
            # FORMAT RATING
            # =================================================

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

            # =================================================
            # WINRATE
            # =================================================

            total_games = (
                wins + losses
            )

            if total_games > 0:

                winrate = (
                    wins /
                    total_games *
                    100
                )

            else:

                winrate = 0

            # =================================================
            # MESSAGE
            # =================================================

            message = (
                f"🎮 FACEIT Stats — {nickname}\n\n"

                f"📊 Последних матчей: "
                f"{len(matches)}\n"

                f"🔎 Обработано матчей: "
                f"{processed}\n\n"

                f"🔥 Rating ≥ 1.80: "
                f"{rating_180}\n"

                f"⚡ Rating ≥ 1.70: "
                f"{rating_170}\n"

                f"📈 Rating ≥ 1.60: "
                f"{rating_160}\n"

                f"📊 Rating ≥ 1.50: "
                f"{rating_150}\n\n"

                f"📈 Средний Rating: "
                f"{average_rating_text}\n"

                f"🚀 Лучший Rating: "
                f"{best_rating_text}\n\n"

                f"🎯 K/D: "
                f"{kd:.2f}\n"

                f"🔫 Kills: "
                f"{kills}\n"

                f"💀 Deaths: "
                f"{deaths}\n\n"

                f"🏆 Победы: "
                f"{wins}\n"

                f"💀 Поражения: "
                f"{losses}\n"

                f"📌 Winrate: "
                f"{winrate:.1f}%"
            )

            await update.message.reply_text(
                message,
                reply_markup=reply_markup
            )

        except Exception as e:

            print()
            print(
                "========== ERROR =========="
            )

            print(
                repr(e)
            )

            print(
                "============================"
            )

            await update.message.reply_text(
                "❌ Не удалось получить статистику.\n\n"
                "Проверь логи Render."
            )

        return

    # =====================================================
    # ADD PLAYER BUTTON
    # =====================================================

    if text == "➕ Добавить игрока":

        await add_player(
            update,
            context
        )

        return

    # =====================================================
    # UNKNOWN MESSAGE
    # =====================================================

    await update.message.reply_text(
        "Выбери действие на клавиатуре 👇",
        reply_markup=reply_markup
    )


# =========================================================
# HEALTH SERVER FOR RENDER
# =========================================================

class HealthHandler(
    BaseHTTPRequestHandler
):

    def do_GET(self):

        self.send_response(200)

        self.send_header(
            "Content-type",
            "text/plain"
        )

        self.end_headers()

        self.wfile.write(
            b"OK"
        )

    def log_message(
        self,
        format,
        *args
    ):
        return


def start_health_server():

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    server = HTTPServer(
        (
            "0.0.0.0",
            port
        ),
        HealthHandler
    )

    print(
        f"Health server started on port {port}"
    )

    server.serve_forever()


# =========================================================
# MAIN
# =========================================================

def main():

    init_db()

    # -----------------------------------------------------
    # Render health server
    # -----------------------------------------------------

    health_thread = threading.Thread(
        target=start_health_server,
        daemon=True
    )

    health_thread.start()

    # -----------------------------------------------------
    # Telegram
    # -----------------------------------------------------

    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            handle_message
        )
    )

    print(
        "======================================"
    )

    print(
        "FACEIT Stats Bot started"
    )

    print(
        "======================================"
    )

    application.run_polling(
        drop_pending_updates=True
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    main()
