```python
import os
import re
import time
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

# Небольшая пауза между запросами,
# чтобы не упираться в лимиты FACEIT API.
REQUEST_DELAY = 0.35


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

        # Если FACEIT временно ограничил запросы
        if response.status_code == 429:

            if attempt < retries - 1:
                time.sleep(2 + attempt * 2)
                continue

            response.raise_for_status()

        response.raise_for_status()

        return response.json()

    raise RuntimeError("FACEIT API не ответил")


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

    return data.get("items", [])


# =========================
# СТАТИСТИКА КОНКРЕТНОГО МАТЧА
# =========================

def get_match_stats(match_id):

    return faceit_get(
        f"{FACEIT_API}/matches/{match_id}/stats"
    )


# =========================
# ПОИСК ИГРОКА В СТАТИСТИКЕ
# =========================

def find_player_stats(match_data, player_id):

    rounds = match_data.get("rounds", [])

    for round_data in rounds:

        teams = round_data.get("teams", [])

        for team in teams:

            players = team.get("players", [])

            for player in players:

                if player.get("player_id") == player_id:

                    return {
                        "player_stats": player.get("player_stats", {}),
                        "team_stats": team.get("team_stats", {}),
                        "team_id": team.get("team_id")
                    }

    return None


# =========================
# ЧИСЛОВОЕ ЗНАЧЕНИЕ
# =========================

def get_number(stats, names):

    for name in names:

        if name in stats:

            value = stats[name]

            try:
                return float(
                    str(value).replace(",", ".")
                )

            except (ValueError, TypeError):
                pass

    # На всякий случай ищем без учёта регистра
    lower_stats = {
        str(k).lower(): v
        for k, v in stats.items()
    }

    for name in names:

        key = name.lower()

        if key in lower_stats:

            try:
                return float(
                    str(lower_stats[key]).replace(",", ".")
                )

            except (ValueError, TypeError):
                pass

    return None


# =========================
# СТРОКА
# =========================

def get_string(stats, names):

    for name in names:

        if name in stats:
            return str(stats[name])

    lower_stats = {
        str(k).lower(): v
        for k, v in stats.items()
    }

    for name in names:

        key = name.lower()

        if key in lower_stats:
            return str(lower_stats[key])

    return None


# =========================
# АНАЛИЗ
# =========================

def analyze_matches(
    player_id,
    matches
):

    ratings = []
    kds = []

    wins = 0
    losses = 0

    rating_150 = 0
    rating_160 = 0
    rating_170 = 0
    rating_180 = 0

    kills_total = 0
    deaths_total = 0

    analyzed = 0
    errors = 0

    for index, match in enumerate(matches):

        match_id = match.get("match_id")

        if not match_id:
            errors += 1
            continue

        try:

            match_data = get_match_stats(match_id)

            player_data = find_player_stats(
                match_data,
                player_id
            )

            if not player_data:
                errors += 1
                time.sleep(REQUEST_DELAY)
                continue

            stats = player_data["player_stats"]

            # -------------------------
            # RATING
            # -------------------------

            rating = get_number(
                stats,
                [
                    "Rating",
                    "rating",
                    "Player Rating",
                    "player_rating",
                    "Player rating"
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
            # KILLS
            # -------------------------

            kills = get_number(
                stats,
                [
                    "Kills",
                    "kills",
                    "Kill"
                ]
            )

            if kills is not None:
                kills_total += kills

            # -------------------------
            # DEATHS
            # -------------------------

            deaths = get_number(
                stats,
                [
                    "Deaths",
                    "deaths",
                    "Death"
                ]
            )

            if deaths is not None:
                deaths_total += deaths

            # -------------------------
            # K/D
            # -------------------------

            kd = get_number(
                stats,
                [
                    "K/D Ratio",
                    "K/D",
                    "KD Ratio",
                    "Kill/Death Ratio",
                    "kill_death_ratio"
                ]
            )

            if kd is not None:

                kds.append(kd)

            elif kills is not None and deaths is not None:

                if deaths > 0:
                    kds.append(kills / deaths)

            # -------------------------
            # RESULT
            # -------------------------

            result = get_string(
                stats,
                [
                    "Result",
                    "result",
                    "Match Result",
                    "match_result"
                ]
            )

            if result:

                result_lower = result.lower()

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

        except Exception as e:

            print(
                f"Ошибка обработки матча "
                f"{match_id}: {e}"
            )

            errors += 1

        time.sleep(REQUEST_DELAY)

    return {
        "total": len(matches),
        "analyzed": analyzed,
        "errors": errors,

        "ratings": ratings,
        "kds": kds,

        "wins": wins,
        "losses": losses,

        "kills": kills_total,
        "deaths": deaths_total,

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

    # -------------------------
    # RATING
    # -------------------------

    if ratings:

        avg_rating = sum(ratings) / len(ratings)
        best_rating = max(ratings)

    else:

        avg_rating = None
        best_rating = None

    # -------------------------
    # K/D
    # -------------------------

    if data["deaths"] > 0:

        total_kd = (
            data["kills"] /
            data["deaths"]
        )

    elif data["kills"] > 0:

        total_kd = float(data["kills"])

    else:

        total_kd = None

    # -------------------------
    # WINRATE
    # -------------------------

    wins = data["wins"]
    losses = data["losses"]

    played = wins + losses

    if played > 0:

        winrate = (
            wins /
            played *
            100
        )

    else:

        winrate = None

    # -------------------------
    # REPORT
    # -------------------------

    report = (
        f"🎮 <b>FACEIT Stats — {nickname}</b>\n\n"

        f"📊 Последних матчей: "
        f"<b>{data['total']}</b>\n"

        f"🔎 Обработано матчей: "
        f"<b>{data['analyzed']}</b>\n\n"

        f"🔥 Rating ≥ 1.80: "
        f"<b>{data['rating_180']}</b>\n"

        f"⚡ Rating ≥ 1.70: "
        f"<b>{data['rating_170']}</b>\n"

        f"📈 Rating ≥ 1.60: "
        f"<b>{data['rating_160']}</b>\n"

        f"📊 Rating ≥ 1.50: "
        f"<b>{data['rating_150']}</b>\n\n"
    )

    # -------------------------
    # AVG RATING
    # -------------------------

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

    # -------------------------
    # BEST RATING
    # -------------------------

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

    # -------------------------
    # K/D
    # -------------------------

    if total_kd is not None:

        report += (
            f"🎯 K/D: "
            f"<b>{total_kd:.2f}</b>\n"
        )

    else:

        report += (
            "🎯 K/D: "
            "<b>—</b>\n"
        )

    # -------------------------
    # KILLS / DEATHS
    # -------------------------

    report += (
        f"🔫 Kills: "
        f"<b>{int(data['kills'])}</b>\n"

        f"💀 Deaths: "
        f"<b>{int(data['deaths'])}</b>\n\n"
    )

    # -------------------------
    # WINS / LOSSES
    # -------------------------

    report += (
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

    # -------------------------
    # ERRORS
    # -------------------------

    if data["errors"] > 0:

        report += (
            f"\n⚠️ Не удалось обработать: "
            f"<b>{data['errors']}</b>"
        )

    return report


# =========================
# TELEGRAM
# =========================

def extract_nickname(text):

    text = text.strip()

    # Иногда Telegram присылает:
    # [https://faceit.com/...](https://faceit.com/...)
    # поэтому сначала ищем URL внутри любого текста.

    match = re.search(
        r"(?:https?://)?(?:www\.)?"
        r"faceit\.com/"
        r"(?:[a-z]{2}/)?"
        r"players/"
        r"([^/?#\s\)\]]+)",
        text,
        re.IGNORECASE
    )

    if match:

        nickname = match.group(1)

        return nickname

    # Просто ник

    if re.fullmatch(
        r"[A-Za-z0-9_.-]{2,50}",
        text
    ):

        return text

    return None


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


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = update.message.text.strip()

    nickname = extract_nickname(text)

    # =========================
    # НИК НЕ НАЙДЕН
    # =========================

    if not nickname:

        await update.message.reply_text(
            "❌ Не смог определить FACEIT ник.\n\n"

            "Отправь ссылку на профиль "
            "или просто ник."
        )

        return

    try:

        # =========================
        # ПОИСК ИГРОКА
        # =========================

        await update.message.reply_text(
            f"🔎 Ищу игрока "
            f"<b>{nickname}</b>...",
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

        # =========================
        # ИСТОРИЯ
        # =========================

        await update.message.reply_text(
            f"✅ Игрок найден: "
            f"<b>{real_nickname}</b>\n\n"

            f"📊 Получаю последние "
            f"{MATCH_LIMIT} матчей...",
            parse_mode="HTML"
        )

        matches = get_matches(player_id)

        if not matches:

            await update.message.reply_text(
                "❌ Не удалось получить "
                "историю матчей."
            )

            return

        # =========================
        # АНАЛИЗ
        # =========================

        await update.message.reply_text(
            f"🎮 Найдено матчей: "
            f"<b>{len(matches)}</b>\n\n"

            "🔍 Получаю статистику "
            "каждого матча...\n\n"

            "⏳ Это может занять "
            "около минуты.",
            parse_mode="HTML"
        )

        data = analyze_matches(
            player_id,
            matches
        )

        # =========================
        # ОТЧЁТ
        # =========================

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
# ЗАПУСК
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

    print(
        "FACEIT Stats Bot started"
    )

    app.run_polling()


if __name__ == "__main__":

    main()
```
