import os
import random
import gspread
import pytz
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from telegram import Bot, InputMediaPhoto, InputMediaVideo, InlineKeyboardMarkup, InlineKeyboardButton
from oauth2client.service_account import ServiceAccountCredentials
import html

# === НАСТРОЙКИ ===
SPREADSHEET_ID = "1TxBKBqwGB_kSx0ACfgMBuyOQ7Tefr3srQbS5jCxjpH4"
SHEET_NAME = "Telegram_Aliexpress"
LOG_SHEET_NAME = "Лог"
BOT_TOKEN = "8003597219:AAHYhGMZTZ3z2huBya1eNYL-HCJiGuFtqHc"
CHANNEL_ID = "@womenhitshop"
POST_TIMES = [("10", "00"), ("14", "30"), ("19", "00")]
LA_TZ = pytz.timezone("Europe/Moscow")

# === GOOGLE SHEETS ===
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
log_sheet = client.open_by_key(SPREADSHEET_ID).worksheet(LOG_SHEET_NAME)

# === TELEGRAM BOT ===
bot = Bot(token=BOT_TOKEN)


def post_from_sheet():
    try:
        rows = sheet.get_all_records()
        if not rows:
            print("❌ Таблица пуста.")
            return

        unpublished = [i for i, row in enumerate(rows) if str(row.get("Опубликовано", "")).strip().lower() != "да"]
        if not unpublished:
            print("✅ Все товары уже опубликованы.")
            return

        row_index = random.choice(unpublished)
        row = rows[row_index]

        title = str(row.get("Название", "")).strip()
        desc = str(row.get("Описание", "")).strip()
        link = str(row.get("Ссылка", "")).strip()
        media_field = str(row.get("Медиа", "")).strip()

        media_urls = [url.strip() for url in media_field.split(",") if url.strip()]
        if not media_urls:
            print("❌ Нет медиа для публикации.")
            return

        title = html.escape(title)
        desc = html.escape(desc)
        caption = f"<b>{title}</b>"
        if desc:
            caption += f"\n\n{desc}"
        if link:
            caption += f'\n\n<a href="{link}">🛒 Перейти по ссылке</a>'
        if len(caption) > 1024:
            caption = caption[:1020] + "..."

        reply_markup = None
        if link:
            button = InlineKeyboardButton("🛒 Перейти по ссылке", url=link)
            reply_markup = InlineKeyboardMarkup([[button]])

        if len(media_urls) > 1:
            media_group = []
            for i, url in enumerate(media_urls):
                media = (InputMediaVideo if url.lower().endswith(('.mp4', '.mov', '.webm'))
                         else InputMediaPhoto)(media=url, caption=caption if i == 0 else None, parse_mode="HTML")
                media_group.append(media)

            bot.send_media_group(chat_id=CHANNEL_ID, media=media_group)


            if reply_markup:
                bot.send_message(chat_id=CHANNEL_ID, text="🛍️ Товар доступен по ссылке:", reply_markup=reply_markup)
        else:
            media_url = media_urls[0]
            if media_url.lower().endswith(('.mp4', '.mov', '.webm')):
                bot.send_video(chat_id=CHANNEL_ID, video=media_url, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
            else:
                bot.send_photo(chat_id=CHANNEL_ID, photo=media_url, caption=caption, parse_mode="HTML", reply_markup=reply_markup)

        # Обновление "Опубликовано"
        publish_col_index = list(row.keys()).index("Опубликовано") + 1
        sheet.update_cell(row_index + 2, publish_col_index, "да")
        # Окрашиваем всю строку в жёлтый цвет
        from gspread_formatting import CellFormat, Color, format_cell_range

        yellow_fill = CellFormat(
            backgroundColor=Color(1, 1, 0.6)  # светло-жёлтый
        )

        format_cell_range(
            sheet,
            f"A{row_index+2}:E{row_index+2}",  # предполагаем, что у вас 5 нужных колонок
            yellow_fill
        )


        # Лог в отдельный лист
        log_row = [
            row.get("Название", ""),
            row.get("Описание", ""),
            row.get("Ссылка", ""),
            row.get("Медиа", ""),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ]
        log_sheet.append_row(log_row)


        print("✅ Пост успешно отправлен.")

    except Exception as e:
        print(f"❌ Ошибка при отправке поста: {e}")


# === FLASK ===
app = Flask(__name__)


@app.route("/")
def home():
    return "✅ Бот онлайн и ждёт расписания."


@app.route("/post-now")
def post_now():
    post_from_sheet()
    return "✅ Тест-пост отправлен."


# === РАСПИСАНИЕ ===
scheduler = BackgroundScheduler(timezone=LA_TZ)


def schedule_posts():
    for hour, minute in POST_TIMES:
        scheduler.add_job(post_from_sheet, "cron", hour=int(hour), minute=int(minute))
        print(f"🕒 Пост в {hour}:{minute} LA запланирован")


schedule_posts()
scheduler.start()

# === ЗАПУСК ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
