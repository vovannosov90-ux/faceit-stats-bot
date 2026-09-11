import os
import re
import time
import threading
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
# HTTP-СЕРВЕР ДЛЯ RENDER
# =========================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        self.send_response(200)

        self.send_header(
            "Content-type",
            "text/plain"
        )

        self.end_headers()

        self.wfile.write(
            b"FACEIT Stats Bot is running"
        )

    def log_message(self, format, *args):
        return


def start_health_server():

    port = int(
        os.getenv(
            "PORT",
            "10000"
        )
    )

    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler
    )

    print(
        f"HTTP health server started on port {port}"
    )

    server.serve_forever()


# =========================
# FACEIT API
# =========================

def faceit_get(
    url,
    params=None,
    retries=3
):

    headers = {
        "Authorization":
            f"Bearer {FACEIT_API_KEY}",

        "Content-Type":
            "application/json",
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

                time.sleep(
                    2 + attempt * 2
                )

                continue

        response.raise_for_status()

        return response.json()

    raise RuntimeError(
        "FACEIT API не ответил"
    )


# =========================
# ИГРОК
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
# ИСТОРИЯ МАТЧЕЙ
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

    return data.get(
        "items",
        []
    )


# =========================
# СТАТИСТИКА ИГРОКА
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
# ЧИСЛО
# =========================

def get_number(
    stats,
    names
):

    if not isinstance(stats, dict):
        return None

    # Сначала точное совпадение

    for name in names:

        if name in stats:

            try:

                return float(
                    str(
                        stats[name]
                    ).replace(",", ".")
                )

            except (
                ValueError,
                TypeError
            ):

                pass

    # Потом без учёта регистра

    lower_stats = {
        str(k).lower(): v
        for k, v in stats.items()
    }

    for name in names:

        key = name.lower()

        if key in lower_stats:

            try:

                return float(
                    str(
                        lower_stats[key]
                    ).replace(",", ".")
                )

            except (
                ValueError,
                TypeError
            ):

                pass

    return None


# =========================
# СТРОКА
# =========================

def get_string(
    stats,
    names
):

    if not isinstance(stats, dict):
        return None

    for name in names:

        if name in stats:

            return str(
                stats[name]
            )

    lower_stats = {
        str(k).lower(): v
        for k, v in stats.items()
    }

    for name in names:

        key = name.lower()

        if key in lower_stats:

            return str(
                lower_stats[key]
            )

    return None


# =========================
# АНАЛИЗ СТАТИСТИКИ
# =========================

def analyze_player_stats(
    stats_data
):

    items = stats_data.get(
        "items",
        []
    )

    ratings = []

    kills_total = 0
    deaths_total = 0

    wins = 0
    losses = 0

    analyzed = 0
    errors = 0

    for item in items:

        stats = item.get(
            "stats",
            {}
        )

        if not isinstance(
            stats,
            dict
        ):

            errors += 1

            continue

        # =====================
        # DEBUG
        # =====================

        if analyzed == 0:

            print(
                "FACEIT PLAYER STATS:"
            )

            print(
                stats
            )

        # =====================
        # RATING
        # =====================

        rating = get_number(
            stats,
            [
                "Rating",
                "rating",
                "Player Rating",
                "player_rating",
                "Player rating",
                "Average Rating",
                "average_rating"
            ]
        )

        if rating is not None:

            ratings.append(
                rating
            )

        # =====================
        # KILLS
        # =====================

        kills = get_number(
            stats,
            [
                "Kills",
                "kills",
                "Kill",
                "kill"
            ]
        )

        if kills is not None:

            kills_total += kills

        # =====================
        # DEATHS
        # =====================

        deaths = get_number(
            stats,
            [
                "Deaths",
                "deaths",
                "Death",
                "death"
            ]
        )

        if deaths is not None:

            deaths_total += deaths

        # =====================
        # RESULT
        # =====================

        result = get_string(
            stats,
            [
                "Result",
                "result",
                "Match Result",
                "match_result",
                "Winner",
                "winner"
            ]
        )

        if result:

            result_lower = (
                result.lower()
            )

            if result_lower in [
                "1",
                "win",
                "won",
                "winner"
            ]:

                wins += 1

            elif result_lower in [
                "0",
                "loss",
                "lost",
                "lose"
            ]:

                losses += 1

        analyzed += 1

    return {

        "total":
            len(items),

        "analyzed":
            analyzed,

        "errors":
            errors,

        "ratings":
            ratings,

        "kills":
            kills_total,

        "deaths":
            deaths_total,

        "wins":
            wins,

        "losses":
            losses
    }


# =========================
# ОТЧЁТ
# =========================

def make_report(
    nickname,
    data
):

    ratings = data["ratings"]

    if ratings:

        avg_rating = (
            sum(ratings)
            / len(ratings)
        )

        best_rating = max(
            ratings
        )

        rating_150 = sum(
            r >= 1.50
            for r in ratings
        )

        rating_160 = sum(
            r >= 1.60
            for r in ratings
        )

        rating_170 = sum(
            r >= 1.70
            for r in ratings
        )

        rating_180 = sum(
            r >= 1.80
            for r in ratings
        )

    else:

        avg_rating = None
        best_rating = None

        rating_150 = 0
        rating_160 = 0
        rating_170 = 0
        rating_180 = 0

    # =====================
    # K/D
    # =====================

    if data["deaths"] > 0:

        kd = (
            data["kills"]
            / data["deaths"]
        )

    else:

        kd = None

    # =====================
    # WINRATE
    # =====================

    wins = data["wins"]
    losses = data["losses"]

    played = wins + losses

    if played > 0:

        winrate = (
            wins
            / played
            * 100
        )

    else:

        winrate = None

    # =====================
    # ОТЧЁТ
    # =====================

    report = (
        f"🎮 <b>FACEIT Stats — "
        f"{nickname}</b>\n\n"

        f"📊 Последних матчей: "
        f"<b>{data['total']}</b>\n"

        f"🔎 Обработано матчей: "
        f"<b>{data['analyzed']}</b>\n\n"

        f"🔥 Rating ≥ 1.80: "
        f"<b>{rating_180}</b>\n"

        f"⚡ Rating ≥ 1.70: "
        f"<b>{rating_170}</b>\n"

        f"📈 Rating ≥ 1.60: "
        f"<b>{rating_160}</b>\n"

        f"📊 Rating ≥ 1.50: "
        f"<b>{rating_150}</b>\n\n"
    )

    if avg_rating is not None:

        report += (
            f"📈 Средний Rating: "
            f"<b>{avg_rating:.2f}</b>\n"
        )

    else:

        report += (
            "📈 Средний Rating: "
            "<b>—</b>\n"
        )

    if best_rating is not None:

        report += (
            f"🚀 Лучший Rating: "
            f"<b>{best_rating:.2f}</b>\n"
        )

    else:

        report += (
            "🚀 Лучший Rating: "
            "<b>—</b>\n"
        )

    if kd is not None:

        report += (
            f"🎯 K/D: "
            f"<b>{kd:.2f}</b>\n"
        )

    else:

        report += (
            "🎯 K/D: "
            "<b>—</b>\n"
        )

    report += (
        f"🔫 Kills: "
        f"<b>{int(data['kills'])}</b>\n"

        f"💀 Deaths: "
        f"<b>{int(data['deaths'])}</b>\n\n"

        f"🏆 Победы: "
        f"<b>{wins}</b>\n"

        f"💀 Поражения: "
        f"<b>{losses}</b>\n"
    )

    if winrate is not None:

        report += (
            f"📌 Winrate: "
            f"<b>{winrate:.1f}%</b>\n"
        )

    else:

        report += (
            "📌 Winrate: "
            "<b>—</b>\n"
        )

    if data["errors"] > 0:

        report += (
            f"\n⚠️ Ошибок: "
            f"<b>{data['errors']}</b>"
        )

    return report


# =========================
# ПОИСК NICKNAME
# =========================

def extract_nickname(text):

    text = text.strip()

    match = re.search(
        r"(?:https?://)?"
        r"(?:www\.)?"
        r"faceit\.com/"
        r"(?:[a-z]{2}/)?"
        r"players/"
        r"([^/?#\s\)\]]+)",
        text,
        re.IGNORECASE
    )

    if match:

        return match.group(1)

    if re.fullmatch(
        r"[A-Za-z0-9_.-]{2,50}",
        text
    ):

        return text

    return None


# =========================
# START
# =========================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(

        "🎮 <b>FACEIT Stats</b>\n\n"

        "Отправь мне:\n\n"

        "• ссылку на FACEIT профиль\n"
        "или\n"
        "• просто FACEIT ник\n\n"

        "Например:\n"
        "<code>TheRasca1</code>",

        parse_mode="HTML"
    )


# =========================
# СООБЩЕНИЕ
# =========================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = update.message.text.strip()

    nickname = extract_nickname(
        text
    )

    if not nickname:

        await update.message.reply_text(

            "❌ Не смог определить "
            "FACEIT ник."
        )

        return

    try:

        await update.message.reply_text(

            f"🔎 Ищу игрока "
            f"<b>{nickname}</b>...",

            parse_mode="HTML"
        )

        player = get_player(
            nickname
        )

        player_id = player.get(
            "player_id"
        )

        if not player_id:

            await update.message.reply_text(
                "❌ Игрок не найден."
            )

            return

        real_nickname = player.get(
            "nickname",
            nickname
        )

        await update.message.reply_text(

            f"✅ Игрок найден: "
            f"<b>{real_nickname}</b>\n\n"

            f"📊 Получаю последние "
            f"{MATCH_LIMIT} матчей...",

            parse_mode="HTML"
        )

        stats_data = get_player_match_stats(
            player_id
        )

        await update.message.reply_text(

            "🔍 Получаю статистику FACEIT...\n\n"
            "⏳ Подожди несколько секунд.",

            parse_mode="HTML"
        )

        data = analyze_player_stats(
            stats_data
        )

        report = make_report(
            real_nickname,
            data
        )

        await update.message.reply_text(
            report,
            parse_mode="HTML"
        )

    except requests.exceptions.HTTPError as e:

        await update.message.reply_text(

            "❌ Ошибка FACEIT API:\n"
            f"<code>{e}</code>",

            parse_mode="HTML"
        )

    except Exception as e:

        await update.message.reply_text(

            "❌ Ошибка:\n"
            f"<code>{e}</code>",

            parse_mode="HTML"
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
            filters.TEXT
            & ~filters.COMMAND,
            handle_message
        )
    )

    print(
        "FACEIT Stats Bot started"
    )

    health_thread = threading.Thread(
        target=start_health_server,
        daemon=True
    )

    health_thread.start()

    app.run_polling()


# =========================
# ЗАПУСК
# =========================

if __name__ == "__main__":

    main()
