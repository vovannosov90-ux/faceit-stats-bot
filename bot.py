```python
import os
import json
import sqlite3
import threading
import time

from urllib.request import Request, urlopen
from urllib.parse import quote
from urllib.error import HTTPError, URLError
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
# ПРОВЕРКА
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
    print("================================================")
    print("FACEIT API REQUEST")
    print("URL:", url)
    print("================================================")

    try:

        request = Request(
            url,
            headers={
                "Authorization": f"Bearer {FACEIT_API_KEY}",
                "Accept": "application/json",
                "User-Agent": "FACEIT-Stats-Bot/1.0",
            },
            method="GET",
        )

        with urlopen(
            request,
            timeout=20,
        ) as response:

            raw = response.read().decode(
                "utf-8"
            )

            print(
                "STATUS:",
                response.status,
            )

            print(
                "RESPONSE LENGTH:",
                len(raw),
            )

            print("================================================")
            print()

            return json.loads(raw)

    except HTTPError as e:

        try:
            body = e.read().decode(
                "utf-8",
                errors="replace",
            )
        except Exception:
            body = ""

        print()
        print("================================================")
        print("FACEIT HTTP ERROR")
        print("STATUS:", e.code)
        print("URL:", url)
        print("BODY:", body[:5000])
        print("================================================")
        print()

        raise

    except URLError as e:

        print()
        print("================================================")
        print("FACEIT URL ERROR")
        print("URL:", url)
        print("ERROR:", repr(e))
        print("================================================")
        print()

        raise

    except Exception as e:

        print()
        print("================================================")
        print("FACEIT API ERROR")
        print("URL:", url)
        print("ERROR:", repr(e))
        print("================================================")
        print()

        raise


# ============================================================
# PLAYER
# ============================================================

def get_player(nickname):

    endpoint = (
        f"/players?nickname={quote(nickname)}"
    )

    return faceit_get(endpoint)


# ============================================================
# PLAYER HISTORY
# ============================================================

def get_matches(
    player_id,
    limit=100,
):

    endpoint = (
        f"/players/{player_id}/history"
        f"?game=cs2"
        f"&limit={limit}"
    )

    data = faceit_get(endpoint)

    return data.get(
        "items",
        [],
    )


# ============================================================
# PLAYER MATCH STATS
# ============================================================

def get_player_match_stats(
    player_id,
    limit=100,
):

    endpoint = (
        f"/players/{player_id}/games/cs2/stats"
        f"?limit={limit}"
    )

    data = faceit_get(endpoint)

    return data.get(
        "items",
        [],
    )


# ============================================================
# MATCH DETAILS
# ============================================================

def get_match_details(match_id):

    endpoint = (
        f"/matches/{match_id}"
    )

    return faceit_get(endpoint)


# ============================================================
# GET MATCH RATING
# ============================================================

def get_match_rating(
    match_id,
    player_id,
):

    print()
    print("------------------------------------------------")
    print("RATING CHECK")
    print("MATCH:", match_id)
    print("PLAYER:", player_id)
    print("------------------------------------------------")

    try:

        match = get_match_details(
            match_id
        )

    except Exception as e:

        print(
            "RATING: ошибка получения match details:",
            repr(e),
        )

        return None

    # --------------------------------------------------------
    # DETAILED RESULTS
    # --------------------------------------------------------

    detailed_results = match.get(
        "detailed_results",
        [],
    )

    print(
        "DETAILED RESULTS COUNT:",
        len(detailed_results),
    )

    # --------------------------------------------------------
    # ПЕЧАТАЕМ СТРУКТУРУ
    # --------------------------------------------------------

    if detailed_results:

        print(
            "FIRST DETAILED RESULT:"
        )

        print(
            json.dumps(
                detailed_results[0],
                ensure_ascii=False,
                indent=2,
            )[:15000]
        )

    # --------------------------------------------------------
    # ИЩЕМ RATING
    # --------------------------------------------------------

    for result in detailed_results:

        stats = result.get(
            "stats",
            {},
        )

        rating = stats.get(
            "rating"
        )

        if rating is not None:

            print(
                "FOUND RATING:",
                rating,
            )

            player_found = False

            membership = result.get(
                "membership"
            )

            result_player_id = result.get(
                "player_id"
            )

            if (
                result_player_id
                and result_player_id == player_id
            ):
                player_found = True

            if membership == player_id:
                player_found = True

            print(
                "PLAYER MATCH:",
                player_found,
            )

            return float(rating)

    # --------------------------------------------------------
    # ДОПОЛНИТЕЛЬНО ПРОВЕРЯЕМ TEAMS
    # --------------------------------------------------------

    teams = match.get(
        "teams",
        {}
    )

    if teams:

        print()
        print("MATCH TEAMS FOUND:")

        print(
            json.dumps(
                teams,
                ensure_ascii=False,
                indent=2,
            )[:15000]
        )

        print()

        if isinstance(
            teams,
            dict,
        ):

            for team_name, team_data in teams.items():

                if not isinstance(
                    team_data,
                    dict,
                ):
                    continue

                team_stats = team_data.get(
                    "stats",
                    {},
                )

                team_rating = team_stats.get(
                    "rating"
                )

                if team_rating is not None:

                    print(
                        "TEAM RATING FOUND:",
                        team_rating,
                        "TEAM:",
                        team_name,
                    )

    print(
        "RATING NOT FOUND FOR MATCH"
    )

    return None


# ============================================================
# ANALYZE
# ============================================================

def analyze_player_stats(
    player_id,
    limit=100,
):

    print()
    print("================================================")
    print("START ANALYZE")
    print("PLAYER:", player_id)
    print("LIMIT:", limit)
    print("================================================")
    print()

    # --------------------------------------------------------
    # MATCH HISTORY
    # --------------------------------------------------------

    matches = get_matches(
        player_id,
        limit=limit,
    )

    print(
        "MATCH HISTORY:",
        len(matches),
    )

    # --------------------------------------------------------
    # PLAYER STATS
    # --------------------------------------------------------

    player_stats = get_player_match_stats(
        player_id,
        limit=limit,
    )

    print(
        "PLAYER STATS:",
        len(player_stats),
    )

    player_stats = player_stats[:limit]

    # --------------------------------------------------------
    # ОСНОВНЫЕ ПОКАЗАТЕЛИ
    # --------------------------------------------------------

    kills = 0
    deaths = 0

    wins = 0
    losses = 0

    processed = 0

    ratings = []

    # --------------------------------------------------------
    # PLAYER STATS
    # --------------------------------------------------------

    for item in player_stats:

        stats = item.get(
            "stats",
            {}
        )

        if (
            isinstance(stats, dict)
            and isinstance(
                stats.get("stats"),
                dict,
            )
        ):

            stats = stats["stats"]

        if not isinstance(
            stats,
            dict,
        ):
            continue

        processed += 1

        # KILLS
        try:

            kills += int(
                stats.get(
                    "Kills",
                    0,
                )
            )

        except Exception:
            pass

        # DEATHS
        try:

            deaths += int(
                stats.get(
                    "Deaths",
                    0,
                )
            )

        except Exception:
            pass

        # RESULT
        result = str(
            stats.get(
                "Result",
                "",
            )
        )

        if result == "1":

            wins += 1

        elif result == "0":

            losses += 1

        # DIRECT RATING
        rating = stats.get(
            "Rating"
        )

        if rating is not None:

            try:

                ratings.append(
                    float(rating)
                )

            except Exception:
                pass

    # --------------------------------------------------------
    # НОВЫЙ RATING
    # --------------------------------------------------------

    print()
    print("================================================")
    print("SEARCHING FACEIT RATING")
    print("MATCHES TO CHECK:", len(matches))
    print("================================================")

    matches_to_check = matches[:20]

    checked_rating_matches = 0

    for index, match in enumerate(
        matches_to_check,
        start=1,
    ):

        match_id = match.get(
            "match_id"
        )

        if not match_id:
            continue

        print()
        print(
            f"[RATING {index}/{len(matches_to_check)}]"
        )

        print(
            "MATCH ID:",
            match_id,
        )

        rating = get_match_rating(
            match_id,
            player_id,
        )

        if rating is not None:

            ratings.append(
                rating
            )

            checked_rating_matches += 1

            print(
                ">>> RATING SAVED:",
                rating,
            )

        else:

            print(
                ">>> NO RATING"
            )

        time.sleep(0.15)

    print()
    print("================================================")
    print("RATING SEARCH FINISHED")

    print(
        "RATINGS FOUND:",
        len(ratings),
    )

    print(
        "MATCHES WITH RATING:",
        checked_rating_matches,
    )

    print("================================================")
    print()

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

    total_results = (
        wins + losses
    )

    if total_results > 0:

        winrate = (
            wins
            / total_results
        ) * 100

    else:

        winrate = 0

    # --------------------------------------------------------
    # RATING
    # --------------------------------------------------------

    if ratings:

        average_rating = (
            sum(ratings)
            / len(ratings)
        )

        best_rating = max(
            ratings
        )

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

        "average_rating":
            average_rating,

        "best_rating":
            best_rating,
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

    nickname = player[
        "nickname"
    ]

    player_id = player[
        "faceit_id"
    ]

    await update.message.reply_text(
        "FACEIT Stats:\n\n"
        "⏳ Загружаю статистику..."
    )

    try:

        result = analyze_player_stats(
            player_id,
            limit=100,
        )

        ratings = result[
            "ratings"
        ]

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

        average_rating = result[
            "average_rating"
        ]

        best_rating = result[
            "best_rating"
        ]

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
        print("================================================")
        print("STATS ERROR")
        print("ERROR:", repr(e))
        print("================================================")
        print()

        await update.message.reply_text(
            "FACEIT Stats:\n\n"
            "❌ Не удалось получить статистику.\n\n"
            "Проверь логи Render."
        )


# ============================================================
# NICKNAME / BUTTONS
# ============================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    text = (
        update.message.text.strip()
    )

    # --------------------------------------------------------
    # MY STATS
    # --------------------------------------------------------

    if text == "📊 Моя статистика":

        await show_stats(
            update,
            context,
        )

        return

    # --------------------------------------------------------
    # MY PROFILE
    # --------------------------------------------------------

    if text == "👤 Мой профиль":

        player = get_saved_player(
            update.effective_user.id
        )

        if not player:

            await update.message.reply_text(
                "❌ Профиль ещё не сохранён.\n\n"
                "Просто отправь свой FACEIT nickname.",
                reply_markup=main_keyboard(),
            )

            return

        await update.message.reply_text(
            f"👤 FACEIT профиль\n\n"
            f"🎮 Nickname: "
            f"{player['nickname']}\n\n"
            f"🆔 ID: "
            f"{player['faceit_id']}",
            reply_markup=main_keyboard(),
        )

        return

    # --------------------------------------------------------
    # NICKNAME
    # --------------------------------------------------------

    nickname = text

    await update.message.reply_text(
        "⏳ Ищу игрока на FACEIT..."
    )

    try:

        player_data = get_player(
            nickname
        )

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
            f"Теперь нажми "
            f"«📊 Моя статистика».",
            reply_markup=main_keyboard(),
        )

    except Exception as e:

        print()
        print("================================================")
        print("PLAYER ERROR")
        print("ERROR:", repr(e))
        print("================================================")
        print()

        await update.message.reply_text(
            "❌ Не удалось найти игрока.\n\n"
            "Проверь nickname и попробуй ещё раз."
        )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):

    print()
    print("================================================")
    print("TELEGRAM ERROR")
    print("ERROR:", repr(context.error))
    print("================================================")
    print()


# ============================================================
# HEALTH SERVER
# ============================================================

class HealthHandler(
    BaseHTTPRequestHandler
):

    def do_GET(self):

        self.send_response(
            200
        )

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
        (
            "0.0.0.0",
            port,
        ),
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
            filters.TEXT
            & ~filters.COMMAND,
            handle_message,
        )
    )

    application.add_error_handler(
        error_handler
    )

    print()
    print("========================================")
    print("FACEIT Stats Bot started")
    print("========================================")
    print()

    application.run_polling(
        drop_pending_updates=True
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
```
