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
        timeout=20
    )

    response.raise_for_status()
    return response.json()


def get_player(nickname):
    data = faceit_get(
        f"{FACEIT_API}/players",
        {"nickname": nickname}
    )

    return data


def get_matches(player_id, limit=100):
    data = faceit_get(
        f"{FACEIT_API}/players/{player_id}/history",
        {
            "game": "cs2",
            "limit": limit
        }
    )

    return data.get("items", [])


# =========================
# ПОЛУЧЕНИЕ NICKNAME
# =========================

def extract_nickname(text):
    text = text.strip()

    # Ссылка вида:
    # https://www.faceit.com/ru/players/TheRasca1
    match = re.search(
        r"faceit\.com/(?:[a-z]{2}/)?players/([^/?#]+)",
        text,
        re.IGNORECASE
    )

    if match:
        return match.group(1)

    # Если просто написали ник
    return text


# =========================
# КОМАНДЫ
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🎮 FACEIT Stats Bot\n\n"
        "Пришли мне ссылку на FACEIT-профиль.\n\n"
        "Например:\n"
        "https://www.faceit.com/ru/players/TheRasca1"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text.strip()

    nickname = extract_nickname(text)

    await update.message.reply_text(
        f"🔎 Ищу игрока {nickname}..."
    )

    try:
        player = get_player(nickname)

        player_id = player["player_id"]
        actual_nickname = player.get("nickname", nickname)

        matches = get_matches(player_id)

        await update.message.reply_text(
            f"✅ Игрок найден: {actual_nickname}\n"
            f"🎮 Найдено матчей: {len(matches)}\n\n"
            "Следующим шагом подключим "
            "расчёт MVP и рейтинга 1.80+."
        )

    except requests.HTTPError as e:

        await update.message.reply_text(
            "❌ Не удалось получить данные FACEIT.\n\n"
            "Проверь ссылку или попробуй ещё раз."
        )

    except Exception as e:

        print("ERROR:", e)

        await update.message.reply_text(
            "❌ Произошла ошибка при обработке профиля."
        )


# =========================
# ЗАПУСК
# =========================

def main():

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    print("FACEIT Stats Bot started!")

    app.run_polling()


if __name__ == "__main__":
    main()
