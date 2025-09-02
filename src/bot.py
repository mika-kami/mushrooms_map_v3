import os
from dotenv import load_dotenv


from datetime import time
from telegram import Update
from telegram.ext import Application, CallbackContext, CommandHandler

from src.config import TELEGRAM_TOKEN, UPD1_TIME_UTC, UPD2_TIME_UTC
from src.image_processor import (
    download_image,
    create_comparison_map,
    get_latest_image_path,
    RAW_DIR,
    PROCESSED_DIR,
)

# Load environment variables from .env file
load_dotenv()

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")


async def start(update: Update, context: CallbackContext):
    """Handler for the /start command."""
    await update.message.reply_text(
        "Welcome to the Mushroom Map Bot!\n\n"
        "Available commands:\n"
        "/raw - Show the newest raw map image.\n"
        "/map - Show the latest comparison result."
    )


async def run_job(context: CallbackContext):
    """Downloads and processes images, then sends a report."""
    job = context.job
    await context.bot.send_message(job.chat_id, text="Starting...")

    download_image()
    processed_map_path = create_comparison_map()

    if processed_map_path:
        await context.bot.send_message(
            job.chat_id, text="The latest comparison map uploading..."
        )
        with open(processed_map_path, "rb") as photo_file:
            await context.bot.send_photo(job.chat_id, photo=photo_file)
    else:
        await context.bot.send_message(
            job.chat_id, text="Map processing failed. Not enough images?"
        )


async def run_command(update: Update, context: CallbackContext):
    """
    Handler for the /run command.
    Restricted to the admin user.
    """
    # Check if the user sending the command is the admin
    user_id = update.message.from_user.id
    if str(user_id) != str(ADMIN_CHAT_ID):
        await update.message.reply_text(
            "Sorry, you are not authorized to use this command."
        )
        return

    # If the user is authorized, proceed with the original logic
    chat_id = update.message.chat_id
    context.job_queue.run_once(
        run_job, 0, chat_id=chat_id, name=f"manual_run_{chat_id}"
    )
    await update.message.reply_text("Manual run triggered!")


async def raw_command(update: Update, context: CallbackContext):
    """Handler for the /raw command."""
    latest_raw = get_latest_image_path(RAW_DIR)
    if latest_raw:
        with open(latest_raw, "rb") as photo_file:
            await update.message.reply_photo(photo=photo_file)
    else:
        await update.message.reply_text(
            "No raw images found. Use /run to download one."
        )


async def map_command(update: Update, context: CallbackContext):
    """Handler for the /map command."""
    latest_processed = get_latest_image_path(PROCESSED_DIR)
    if latest_processed:
        with open(latest_processed, "rb") as photo_file:
            await update.message.reply_photo(photo=photo_file)
    else:
        await update.message.reply_text(
            "No processed map found. Use /run to create one."
        )


def main():
    """Starts the bot and schedules the daily job."""
    if not TELEGRAM_TOKEN or ADMIN_CHAT_ID == "YOUR_ADMIN_CHAT_ID":
        raise ValueError(
            "Please set TELEGRAM_TOKEN in .env and ADMIN_CHAT_ID in src/bot.py"
        )

    # Set timeouts directly on the ApplicationBuilder.
    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .connect_timeout(10)
        .read_timeout(30)
        .write_timeout(30)
        .build()
    )

    if not application.job_queue:
        print(
            "JobQueue not initialized. Ensure 'python-telegram-bot[job-queue]' is installed."
        )
        return

    # Schedule the job to run at 10:00 UTC
    application.job_queue.run_daily(
        run_job,
        time=time(hour=UPD1_TIME_UTC["hh"], minute=UPD1_TIME_UTC["mm"]),
        chat_id=ADMIN_CHAT_ID,
        name="mushroom_map_job_1000_UTC",
    )

    # Schedule the job to run again at 22:00 UTC
    application.job_queue.run_daily(
        run_job,
        time=time(hour=UPD2_TIME_UTC["hh"], minute=UPD2_TIME_UTC["mm"]),
        chat_id=ADMIN_CHAT_ID,
        name="mushroom_map_job_2000_UTC",
    )
    print(
        f"Scheduled jobs to run at {UPD1_TIME_UTC['hh']}:{UPD1_TIME_UTC['mm']:02d} and {UPD2_TIME_UTC['hh']}:{UPD2_TIME_UTC['mm']:02d} UTC."
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("run", run_command))
    application.add_handler(CommandHandler("raw", raw_command))
    application.add_handler(CommandHandler("map", map_command))

    print("Bot is running... Press Ctrl+C to stop.")
    application.run_polling()


if __name__ == "__main__":
    main()
