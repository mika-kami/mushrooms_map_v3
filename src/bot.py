import os
import json
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from src.config import TELEGRAM_TOKEN
from src.image_processor import (
    download_image,
    create_comparison_map,
    get_latest_image_path,
    RAW_DIR,
    PROCESSED_DIR,
)

# Configure logging for Lambda
logger = logging.getLogger()
if logger.hasHandlers():
    logger.setLevel(logging.INFO)
else:
    logging.basicConfig(level=logging.INFO)

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /start command."""
    await update.message.reply_text(
        "Welcome to the Mushroom Map Bot!\n\n"
        "Available commands:\n"
        "/raw - Show the newest raw map image.\n"
        "/map - Show the latest comparison result."
    )


async def raw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /raw command."""
    latest_raw = get_latest_image_path(RAW_DIR)
    if latest_raw:
        with open(latest_raw, "rb") as photo_file:
            await update.message.reply_photo(photo=photo_file)
    else:
        await update.message.reply_text(
            "No raw images found. Use /run to download one."
        )


async def map_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /map command."""
    latest_processed = get_latest_image_path(PROCESSED_DIR)
    if latest_processed:
        with open(latest_processed, "rb") as photo_file:
            await update.message.reply_photo(photo=photo_file)
    else:
        await update.message.reply_text(
            "No processed map found. Use /run to create one."
        )


async def process_scheduled_job(bot_token: str, admin_chat_id: str):
    """
    Scheduled job handler: downloads images and sends updates.
    This runs when EventBridge triggers the Lambda function.
    """
    logger.info("Starting scheduled job")
    
    from telegram import Bot
    bot = Bot(token=bot_token)
    
    try:
        await bot.send_message(admin_chat_id, text="Starting scheduled update...")
        
        download_image()
        processed_map_path = create_comparison_map()
        
        if processed_map_path:
            await bot.send_message(
                admin_chat_id, text="The latest comparison map uploading..."
            )
            with open(processed_map_path, "rb") as photo_file:
                await bot.send_photo(admin_chat_id, photo=photo_file)
            logger.info("Successfully sent comparison map")
        else:
            await bot.send_message(
                admin_chat_id, text="Map processing failed. Not enough images?"
            )
            logger.warning("Map processing failed")
    except Exception as e:
        logger.error(f"Error in scheduled job: {str(e)}", exc_info=True)
        raise


async def process_telegram_update(event: dict):
    """
    Webhook handler: processes incoming Telegram updates.
    This runs when users interact with the bot.
    """
    logger.info("Processing Telegram webhook update")
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("raw", raw_command))
    application.add_handler(CommandHandler("map", map_command))
    
    # Parse the incoming update
    update_dict = json.loads(event["body"])
    
    async with application:
        update = Update.de_json(update_dict, application.bot)
        await application.process_update(update)
    
    logger.info("Successfully processed Telegram update")


def lambda_handler(event, context):
    """
    Main Lambda handler.
    Handles both webhook updates (API Gateway) and scheduled jobs (EventBridge).
    """
    logger.info(f"Received event: {json.dumps(event)}")
    
    try:
        # Check if this is a scheduled event from EventBridge
        if event.get("source") == "aws.events" or "detail-type" in event:
            logger.info("Detected EventBridge scheduled event")
            asyncio.run(process_scheduled_job(TELEGRAM_TOKEN, ADMIN_CHAT_ID))
            return {
                "statusCode": 200,
                "body": json.dumps("Scheduled job completed successfully")
            }
        
        # Otherwise, treat it as a Telegram webhook update from API Gateway
        elif "body" in event:
            logger.info("Detected Telegram webhook update")
            asyncio.run(process_telegram_update(event))
            return {
                "statusCode": 200,
                "body": json.dumps("Update processed successfully")
            }
        
        else:
            logger.error("Unknown event type")
            return {
                "statusCode": 400,
                "body": json.dumps("Unknown event type")
            }
    
    except Exception as e:
        logger.error(f"Error in lambda_handler: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps(f"Error: {str(e)}")
        }
