import os
import re
import time
import threading
import json
import requests

from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# =========================
# НАСТРОЙКИ
# =========================

TOKEN = os.getenv("TOKEN")
FACEIT_API_KEY = os.getenv("FACEIT_API_KEY")

FACEIT_API = "https://open.faceit.com/data/v4"

MATCH_LIMIT = 100


# =========================
# HTTP HEALTH SERVER
# =========================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"FACEIT Stats Bot is running")

    def log_message(self, format, *args):
        return


def start_health_server():
    port = int(os.getenv("PORT", "10000"))

    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler
    )

    print(f"HTTP health server started on port {port}")

    server.serve_forever()


# =========================
# FACEIT API
# =========================

def faceit_get(url, params=None, retries=3):

    headers = {
        "Authorization": f"Bearer {FACEIT_API_KEY}",
        "Content-Type": "application/json",
    }

    for attempt in range(retries):

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=30
        )

        if response.status_code == 429:

            if attempt < retries - 1:
                time.sleep(2 + attempt * 2)
                continue

        response.raise_for_status()

        return response.json()

    raise RuntimeError("FACEIT API не ответил")


# =========================
# PLAYER
# =========================

def get_player(nickname):

    return faceit_get(
        f"{FACEIT_API}/players",
        {
            "nickname": nickname,
            "game": "cs2"
        }
    )


# =========================
# MATCH HISTORY
# =========================

def get_matches(player_id):

    data = faceit_get(
        f"{FACEIT_API}/players/{player_id}/history",
        {
            "game": "cs2",
            "limit": MATCH_LIMIT,
            "offset": 0
        }
    )

    return data.get("items", [])


# =========================
# PLAYER MATCH STATS
# =========================

def get_player_match_stats(player_id):

    return faceit_get(
        f"{FACEIT_API}/players/{player_id}/games/cs2/stats",
        {
            "limit": MATCH_LIMIT,
            "offset": 0
        }
    )


# =========================
# MATCH DETAILS
# =========================

def get_match_details(match_id):

    return faceit_get(
        f"{FACEIT_API}/matches/{match_id}"
    )


# =========================
# ANALYZE STATS
# =========================

def analyze_player_stats(stats_data, player_id):

    ratings = []

    total_kills = 0
    total_deaths = 0

    wins = 0
    losses = 0

    analyzed = 0

    items = stats_data.get("items", [])

    for stats in items:

        # DEBUG — смотрим структуру первого матча
        if analyzed == 0:

            print("========== FACEIT PLAYER STATS ==========")

            print(
                json.dumps(
                    stats,
                    ensure_ascii=False,
                    indent=2
                )
            )

            print("=========================================")

        # =========================
        # KILLS
        # =========================

        try:
            total_kills += int(
                stats.get("Kills", 0)
            )
        except:
            pass

        # =========================
        # DEATHS
        # =========================

        try:
            total_deaths += int(
                stats.get("Deaths", 0)
            )
        except:
            pass

        # =========================
        # RESULT
        # =========================

        result = str(
            stats.get("Result", "")
        )

        if result == "1":
            wins += 1

        elif result == "0":
            losses += 1

        # =========================
        # RATING
        # =========================

        possible_rating_fields = [
            "Rating",
            "rating",
            "Player Rating",
            "player_rating",
            "Player rating",
            "Average Rating",
            "average_rating"
        ]

        rating_value = None

        for field in possible_rating_fields:

            if field in stats:

                try:
                    rating_value = float(
                        stats[field]
                    )
                    break

                except:
                    pass

        if rating_value is not None:
            ratings.append(rating_value)

        analyzed += 1

    return {
        "ratings": ratings,
        "kills": total_kills,
        "deaths": total_deaths,
        "wins": wins,
        "losses": losses,
        "analyzed": analyzed
    }


# =========================
# DEBUG NEW FACEIT RATING
# =========================

def debug_match_rating(matches):

    if not matches:
        return

    test_match_id = matches[0].get("match_id")

    if not test_match_id:
        return

    try:

        test_match = get_match_details(
            test_match_id
        )

        print()
        print("========== FACEIT MATCH DEBUG ==========")
        print("MATCH ID:", test_match_id)

        detailed_results = test_match.get(
            "detailed_results",
            []
        )

        print(
            json.dumps(
                detailed_results,
                ensure_ascii=False,
                indent=2
            )[:15000]
        )

        print("========================================")
        print()

    except Exception as e:

        print(
            "Ошибка получения match details:",
            e
        )


# =========================
# TELEGRAM /START
# =========================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "🎮 FACEIT Stats Bot\n\n"
        "Отправь FACEIT ник или ссылку на профиль.\n\n"
        "Например:\n"
        "TheRasca1"
    )


# =========================
# HANDLE MESSAGE
# =========================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    nickname = update.message.text.strip()

    # =========================
    # FACEIT URL
    # =========================

    match = re.search(
        r"faceit\.com/(?:[a-z]{2}/)?players/([^/?]+)",
        nickname,
        re.IGNORECASE
    )

    if match:
        nickname = match.group(1)

    # =========================
    # ЗАГРУЗКА PLAYER
    # =========================

    try:

        player = get_player(nickname)

    except Exception as e:

        await update.message.reply_text(
            "❌ Не удалось найти игрока FACEIT.\n\n"
            "Проверь ник или ссылку."
        )

        print("PLAYER ERROR:", e)

        return

    player_id = player.get("player_id")

    real_nickname = player.get(
        "nickname",
        nickname
    )

    if not player_id:

        await update.message.reply_text(
            "❌ Не удалось получить ID игрока."
        )

        return

    # =========================
    # MATCH HISTORY
    # =========================

    try:

        matches = get_matches(
            player_id
        )

    except Exception as e:

        await update.message.reply_text(
            "❌ Ошибка получения матчей FACEIT."
        )

        print("MATCH HISTORY ERROR:", e)

        return

    # =========================
    # DEBUG MATCH DETAILS
    # =========================

    debug_match_rating(matches)

    # =========================
    # PLAYER STATS
    # =========================

    try:

        stats_data = get_player_match_stats(
            player_id
        )

    except Exception as e:

        await update.message.reply_text(
            "❌ Ошибка получения статистики FACEIT."
        )

        print("PLAYER STATS ERROR:", e)

        return

    # =========================
    # ANALYZE
    # =========================

    result = analyze_player_stats(
        stats_data,
        player_id
    )

    ratings = result["ratings"]

    kills = result["kills"]
    deaths = result["deaths"]

    wins = result["wins"]
    losses = result["losses"]

    analyzed = result["analyzed"]

    # =========================
    # RATING
    # =========================

    if ratings:

        average_rating = (
            sum(ratings) / len(ratings)
        )

        best_rating = max(ratings)

        rating_180 = sum(
            1 for r in ratings
            if r >= 1.80
        )

        rating_170 = sum(
            1 for r in ratings
            if r >= 1.70
        )

        rating_160 = sum(
            1 for r in ratings
            if r >= 1.60
        )

        rating_150 = sum(
            1 for r in ratings
            if r >= 1.50
        )

    else:

        average_rating = None
        best_rating = None

        rating_180 = 0
        rating_170 = 0
        rating_160 = 0
        rating_150 = 0

    # =========================
    # K/D
    # =========================

    if deaths > 0:

        kd = kills / deaths

    else:

        kd = 0

    # =========================
    # WINRATE
    # =========================

    total_games = wins + losses

    if total_games > 0:

        winrate = (
            wins / total_games
        ) * 100

    else:

        winrate = 0

    # =========================
    # FORMAT RATING
    # =========================

    if average_rating is not None:

        average_rating_text = (
            f"{average_rating:.2f}"
        )

        best_rating_text = (
            f"{best_rating:.2f}"
        )

    else:

        average_rating_text = "—"
        best_rating_text = "—"

    # =========================
    # RESPONSE
    # =========================

    text = (
        f"🎮 FACEIT Stats — {real_nickname}\n\n"

        f"📊 Последних матчей: {len(matches)}\n"
        f"🔎 Обработано матчей: {analyzed}\n\n"

        f"🔥 Rating ≥ 1.80: {rating_180}\n"
        f"⚡ Rating ≥ 1.70: {rating_170}\n"
        f"📈 Rating ≥ 1.60: {rating_160}\n"
        f"📊 Rating ≥ 1.50: {rating_150}\n\n"

        f"📈 Средний Rating: {average_rating_text}\n"
        f"🚀 Лучший Rating: {best_rating_text}\n"
        f"🎯 K/D: {kd:.2f}\n"
        f"🔫 Kills: {kills}\n"
        f"💀 Deaths: {deaths}\n\n"

        f"🏆 Победы: {wins}\n"
        f"💀 Поражения: {losses}\n"
        f"📌 Winrate: {winrate:.1f}%"
    )

    await update.message.reply_text(
        text
    )


# =========================
# MAIN
# =========================

def main():

    if not TOKEN:
        raise RuntimeError(
            "TOKEN не найден"
        )

    if not FACEIT_API_KEY:
        raise RuntimeError(
            "FACEIT_API_KEY не найден"
        )

    app = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    print("FACEIT Stats Bot started")

    # =========================
    # RENDER HEALTH SERVER
    # =========================

    health_thread = threading.Thread(
        target=start_health_server,
        daemon=True
    )

    health_thread.start()

    # =========================
    # TELEGRAM
    # =========================

    app.run_polling()


if __name__ == "__main__":
    main()
