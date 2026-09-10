import os
import re
import requests

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
    data = faceit_get(
        f"{FACEIT_API}/players",
        {
            "nickname": nickname,
            "game": "cs2"
        }
    )

    return data


def get_matches(player_id):
    return faceit_get(
        f"{FACEIT_API}/players/{player_id}/history",
        {
            "game": "cs2",
            "limit": MATCH_LIMIT,
            "offset": 0
        }
    ).get("items", [])


def get_player_match_stats(player_id):
    """
    Получаем статистику самого игрока
    сразу за последние 100 матчей.
    """

    data = faceit_get(
        f"{FACEIT_API}/players/{player_id}/games/cs2/stats",
        {
            "limit": MATCH_LIMIT,
            "offset": 0
        }
    )

    return data.get("items", [])


# =========================
# ПОМОЩНИКИ
# =========================

def get_number(stats, names):
    """
    Ищет числовое значение по нескольким возможным названиям.
    """

    for name in names:
        if name in stats:
            value = stats[name]

            try:
                return float(str(value).replace(",", "."))
            except (ValueError, TypeError):
                pass

    return None


def get_string(stats, names):
    for name in names:
        if name in stats:
            return str(stats[name])

    return None


# =========================
# АНАЛИЗ
# =========================

def analyze_matches(items):

    ratings = []
    kds = []

    wins = 0
    losses = 0

    rating_150 = 0
    rating_160 = 0
    rating_170 = 0
    rating_180 = 0

    errors = 0

    for item in items:

        stats = item.get("stats", {})

        if not stats:
            errors += 1
            continue

        # -------------------------
        # RATING
        # -------------------------

        rating = get_number(
            stats,
            [
                "Rating",
                "rating",
                "Player Rating"
            ]
        )

        if rating is not None:

            ratings.append(rating)

            if rating >= 1.50:
                rating_150 += 1

            if rating >= 1.60:
                rating_160 += 1

            if rating >= 1.70:
                rating_170 += 1

            if rating >= 1.80:
                rating_180 += 1

        # -------------------------
        # K/D
        # -------------------------

        kd = get_number(
            stats,
            [
                "K/D Ratio",
                "K/D",
                "KD Ratio",
                "Kill/Death Ratio"
            ]
        )

        if kd is not None:
            kds.append(kd)

        # -------------------------
        # RESULT
        # -------------------------

        result = get_string(
            stats,
            [
                "Result",
                "result",
                "Match Result"
            ]
        )

        if result in ["1", "win", "Win", "WIN", "won"]:
            wins += 1

        elif result in ["0", "loss", "Loss", "LOSS", "lost"]:
            losses += 1

    return {
        "total": len(items),
        "analyzed": len(ratings),
        "errors": errors,

        "ratings": ratings,
        "kds": kds,

        "wins": wins,
        "losses": losses,

        "rating_150": rating_150,
        "rating_160": rating_160,
        "rating_170": rating_170,
        "rating_180": rating_180,
    }


# =========================
# ОТЧЁТ
# =========================

def make_report(nickname, data):

    ratings = data["ratings"]
    kds = data["kds"]

    if ratings:
        avg_rating = sum(ratings) / len(ratings)
        best_rating = max(ratings)
    else:
        avg_rating = None
        best_rating = None

    if kds:
        avg_kd = sum(kds) / len(kds)
    else:
        avg_kd = None

    wins = data["wins"]
    losses = data["losses"]

    played = wins + losses

    if played > 0:
        winrate = wins / played * 100
    else:
        winrate = None

    report = (
        f"🎮 <b>FACEIT Stats — {nickname}</b>\n\n"

        f"📊 Последних матчей: <b>{data['total']}</b>\n"
        f"🔎 Матчей с Rating: <b>{data['analyzed']}</b>\n\n"

        f"🔥 Rating ≥ 1.80: <b>{data['rating_180']}</b>\n"
        f"⚡ Rating ≥ 1.70: <b>{data['rating_170']}</b>\n"
        f"📈 Rating ≥ 1.60: <b>{data['rating_160']}</b>\n"
        f"📊 Rating ≥ 1.50: <b>{data['rating_150']}</b>\n\n"
    )

    if avg_rating is not None:
        report += f"📈 Средний Rating: <b>{avg_rating:.2f}</b>\n"
    else:
        report += "📈 Средний Rating: <b>—</b>\n"

    if best_rating is not None:
        report += f"🚀 Лучший Rating: <b>{best_rating:.2f}</b>\n"
    else:
        report += "🚀 Лучший Rating: <b>—</b>\n"

    if avg_kd is not None:
        report += f"🎯 Средний K/D: <b>{avg_kd:.2f}</b>\n"
    else:
        report += "🎯 Средний K/D: <b>—</b>\n"

    report += "\n"

    report += f"🏆 Победы: <b>{wins}</b>\n"
    report += f"💀 Поражения: <b>{losses}</b>\n"

    if winrate is not None:
        report += f"📌 Winrate: <b>{winrate:.1f}%</b>\n"
    else:
        report += "📌 Winrate: <b>—</b>\n"

    if data["errors"] > 0:
        report += f"\n⚠️ Не удалось обработать: <b>{data['errors']}</b>"

    return report


# =========================
# TELEGRAM
# =========================

def extract_nickname(text):

    text = text.strip()

    # FACEIT URL
    match = re.search(
        r"faceit\.com/(?:en/)?players/([^/?#]+)",
        text
    )

    if match:
        return match.group(1)

    # Просто ник
    if re.match(r"^[A-Za-z0-9_.-]+$", text):
        return text

    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

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


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text.strip()

    nickname = extract_nickname(text)

    if not nickname:
        await update.message.reply_text(
            "❌ Не смог определить FACEIT ник.\n\n"
            "Отправь ссылку на профиль или просто ник."
        )
        return

    try:

        await update.message.reply_text(
            f"🔎 Ищу игрока <b>{nickname}</b>...",
            parse_mode="HTML"
        )

        player = get_player(nickname)

        player_id = player.get("player_id")

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
            f"✅ Игрок найден: <b>{real_nickname}</b>\n\n"
            f"📊 Получаю последние {MATCH_LIMIT} матчей...",
            parse_mode="HTML"
        )

        # Получаем историю
        matches = get_matches(player_id)

        if not matches:
            await update.message.reply_text(
                "❌ Не удалось получить историю матчей."
            )
            return

        await update.message.reply_text(
            f"🎮 Найдено матчей: <b>{len(matches)}</b>\n\n"
            "🔍 Анализирую статистику игрока...",
            parse_mode="HTML"
        )

        # Получаем индивидуальную статистику
        stats = get_player_match_stats(player_id)

        if not stats:
            await update.message.reply_text(
                "❌ FACEIT не вернул статистику матчей."
            )
            return

        data = analyze_matches(stats)

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
            f"❌ Ошибка FACEIT API:\n"
            f"<code>{e}</code>",
            parse_mode="HTML"
        )

    except Exception as e:

        await update.message.reply_text(
            f"❌ Ошибка:\n"
            f"<code>{e}</code>",
            parse_mode="HTML"
        )


# =========================
# ЗАПУСК
# =========================

def main():

    if not TOKEN:
        raise RuntimeError("TOKEN не найден")

    if not FACEIT_API_KEY:
        raise RuntimeError("FACEIT_API_KEY не найден")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    print("FACEIT Stats Bot started")

    app.run_polling()


if __name__ == "__main__":
    main()
