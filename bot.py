import os
import re
import requests
import time

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
# FACEIT API
# =========================

def faceit_get(url, params=None):
    headers = {
        "Authorization": f"Bearer {FACEIT_API_KEY}",
        "Content-Type": "application/json",
    }

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=30
    )

    response.raise_for_status()
    return response.json()


def get_player(nickname):
    return faceit_get(
        f"{FACEIT_API}/players",
        {"nickname": nickname}
    )


def get_matches(player_id, limit=MATCH_LIMIT):
    data = faceit_get(
        f"{FACEIT_API}/players/{player_id}/history",
        {
            "game": "cs2",
            "limit": limit,
            "offset": 0
        }
    )

    return data.get("items", [])


def get_match_stats(match_id):
    return faceit_get(
        f"{FACEIT_API}/matches/{match_id}/stats"
    )


# =========================
# ПОИСК ИГРОКА В СТАТИСТИКЕ
# =========================

def find_player_stats(match_stats, player_id):

    rounds = match_stats.get("rounds", [])

    for round_data in rounds:

        teams = round_data.get("teams", [])

        for team in teams:

            players = team.get("players", [])

            for player in players:

                if player.get("player_id") == player_id:
                    return {
                        "player": player,
                        "team": team,
                        "round": round_data
                    }

    return None


# =========================
# ИЗВЛЕЧЕНИЕ ЧИСЕЛ
# =========================

def to_float(value):

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_stat(stats, names):

    for name in names:

        if name in stats:
            value = to_float(stats[name])

            if value is not None:
                return value

    return None


# =========================
# АНАЛИЗ 100 МАТЧЕЙ
# =========================

def analyze_matches(player_id, matches, progress_callback=None):

    ratings = []
    kd_values = []

    rating_180 = 0

    wins = 0
    losses = 0

    analyzed = 0
    errors = 0

    for index, match in enumerate(matches, start=1):

        match_id = match.get("match_id")

        if not match_id:
            continue

        try:

            stats_data = get_match_stats(match_id)

            player_data = find_player_stats(
                stats_data,
                player_id
            )

            if not player_data:
                continue

            player = player_data["player"]

            stats = player.get("player_stats", {})

            # -------------------------
            # RATING
            # -------------------------

            rating = get_stat(
                stats,
                [
                    "Rating",
                    "rating",
                    "Player Rating",
                ]
            )

            if rating is not None:

                ratings.append(rating)

                if rating >= 1.80:
                    rating_180 += 1

            # -------------------------
            # K/D
            # -------------------------

            kd = get_stat(
                stats,
                [
                    "K/D Ratio",
                    "K/D",
                    "KD Ratio",
                    "Kill/Death Ratio",
                ]
            )

            if kd is not None:
                kd_values.append(kd)

            # -------------------------
            # РЕЗУЛЬТАТ
            # -------------------------

            team = player_data["team"]

            team_stats = team.get(
                "team_stats",
                {}
            )

            # В разных матчах структура может отличаться,
            # поэтому дополнительно смотрим match history.

            history_result = match.get("result")

            if history_result == "1":
                wins += 1

            elif history_result == "0":
                losses += 1

            analyzed += 1

            if progress_callback:
                progress_callback(index, len(matches))

            # Небольшая пауза, чтобы не долбить API слишком быстро.
            time.sleep(0.05)

        except Exception as e:

            errors += 1

            print(
                f"Ошибка матча {match_id}: {e}"
            )

    # =========================
    # СРЕДНИЕ ЗНАЧЕНИЯ
    # =========================

    average_rating = None

    if ratings:
        average_rating = sum(ratings) / len(ratings)

    average_kd = None

    if kd_values:
        average_kd = sum(kd_values) / len(kd_values)

    best_rating = None

    if ratings:
        best_rating = max(ratings)

    return {
        "total_matches": len(matches),
        "analyzed": analyzed,
        "errors": errors,
        "ratings": ratings,
        "average_rating": average_rating,
        "best_rating": best_rating,
        "rating_180": rating_180,
        "average_kd": average_kd,
        "wins": wins,
        "losses": losses,
    }


# =========================
# NICKNAME ИЗ ССЫЛКИ
# =========================

def extract_nickname(text):

    text = text.strip()

    match = re.search(
        r"faceit\.com/(?:[a-z]{2}/)?players/([^/?#]+)",
        text,
        re.IGNORECASE
    )

    if match:
        return match.group(1)

    return text


# =========================
# ФОРМАТИРОВАНИЕ
# =========================

def format_number(value):

    if value is None:
        return "—"

    return f"{value:.2f}"


def make_report(nickname, result):

    total = result["total_matches"]
    analyzed = result["analyzed"]

    average_rating = result["average_rating"]
    best_rating = result["best_rating"]

    rating_180 = result["rating_180"]

    average_kd = result["average_kd"]

    text = (
        f"🎮 <b>FACEIT Stats — {nickname}</b>\n\n"

        f"📊 Последние матчей: <b>{total}</b>\n"
        f"🔎 Обработано: <b>{analyzed}</b>\n\n"

        f"🔥 Rating ≥ 1.80: <b>{rating_180}</b>\n"
        f"📈 Средний Rating: <b>"
        f"{format_number(average_rating)}</b>\n"
        f"🚀 Лучший Rating: <b>"
        f"{format_number(best_rating)}</b>\n\n"

        f"🎯 Средний K/D: <b>"
        f"{format_number(average_kd)}</b>\n\n"

        f"🏆 Победы: <b>{result['wins']}</b>\n"
        f"💀 Поражения: <b>{result['losses']}</b>\n"
    )

    if result["errors"]:

        text += (
            f"\n⚠️ Ошибок при получении статистики: "
            f"<b>{result['errors']}</b>"
        )

    return text


# =========================
# START
# =========================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "🎮 FACEIT Stats Bot\n\n"
        "Пришли ссылку на FACEIT-профиль.\n\n"
        "Например:\n"
        "https://www.faceit.com/ru/players/TheRasca1"
    )


# =========================
# ОБРАБОТКА СООБЩЕНИЯ
# =========================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = update.message.text.strip()

    nickname = extract_nickname(text)

    status_message = await update.message.reply_text(
        f"🔎 Ищу игрока <b>{nickname}</b>...",
        parse_mode="HTML"
    )

    try:

        # -------------------------
        # ИГРОК
        # -------------------------

        player = get_player(nickname)

        player_id = player["player_id"]

        actual_nickname = player.get(
            "nickname",
            nickname
        )

        # -------------------------
        # МАТЧИ
        # -------------------------

        await status_message.edit_text(
            f"✅ Игрок найден: <b>{actual_nickname}</b>\n\n"
            f"📥 Загружаю последние {MATCH_LIMIT} матчей...",
            parse_mode="HTML"
        )

        matches = get_matches(
            player_id,
            MATCH_LIMIT
        )

        if not matches:

            await status_message.edit_text(
                "❌ Не удалось найти матчи CS2."
            )

            return

        # -------------------------
        # АНАЛИЗ
        # -------------------------

        await status_message.edit_text(
            f"📊 Найдено матчей: <b>{len(matches)}</b>\n\n"
            "🔍 Анализирую статистику матчей...\n"
            "Это может занять немного времени.",
            parse_mode="HTML"
        )

        result = analyze_matches(
            player_id,
            matches
        )

        # -------------------------
        # ОТЧЁТ
        # -------------------------

        report = make_report(
            actual_nickname,
            result
        )

        await status_message.edit_text(
            report,
            parse_mode="HTML"
        )

    except requests.HTTPError as e:

        print("FACEIT HTTP ERROR:", e)

        await status_message.edit_text(
            "❌ FACEIT API вернул ошибку.\n\n"
            "Проверь API key и попробуй ещё раз."
        )

    except Exception as e:

        print("ERROR:", e)

        await status_message.edit_text(
            "❌ Произошла ошибка при обработке профиля.\n\n"
            "Посмотри логи Render — там будет подробность."
        )


# =========================
# ЗАПУСК
# =========================

def main():

    app = Application.builder().token(TOKEN).build()

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

    print(
        "FACEIT Stats Bot started!"
    )

    app.run_polling()


if __name__ == "__main__":
    main()
