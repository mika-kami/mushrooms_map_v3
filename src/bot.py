import os
from dotenv import load_dotenv
from datetime import time
from telegram import Update
from telegram.ext import Application, CallbackContext, CommandHandler
from src.config import TELEGRAM_TOKEN, UPD1_TIME_UTC, UPD2_TIME_UTC, GEOJSON_DIR, KML_DIR, CROP_PARAMS
from src.image_processor import (
    download_image,
    create_comparison_map,
    get_latest_image_path,
    get_coordinates_for_pixel,
    get_pixel_for_coordinates,
    crop_processed_image,
    RAW_DIR,
    PROCESSED_DIR,
)
from src.geo_processor import GeoProcessor

# Load environment variables from .env file
load_dotenv()
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

# Initialize geo processor
geo_processor = GeoProcessor()


async def start(update: Update, context: CallbackContext):
    """Handler for the /start command."""
    await update.message.reply_text(
        "Welcome to the Mushroom Map Bot! 🍄\n\n"
        "Available commands:\n"
        "/raw - Show the newest raw map image\n"
        "/map - Show the latest comparison result\n"
        "/coords <x> <y> - Get coordinates for pixel position (cropped image)\n"
        "/pixel <lon> <lat> - Get pixel position for coordinates (cropped image)\n"
        "/geojson - Get the latest GeoJSON file\n"
        "/kml - Get the latest KML file\n"
        "/info <lon> <lat> - Get mushroom info for coordinates\n"
        "/crop - Manually crop the latest processed image"
    )


async def run_job(context: CallbackContext):
    """Downloads and processes images, then sends a report with geographic data."""
    job = context.job
    await context.bot.send_message(job.chat_id, text="Starting mushroom map update...")

    # Download new image
    download_image()

    # Process comparison map (includes cropping)
    processed_map_path = create_comparison_map()

    if processed_map_path:
        await context.bot.send_message(
            job.chat_id, text="The latest comparison map uploading (cropped and processed)..."
        )

        with open(processed_map_path, "rb") as photo_file:
            await context.bot.send_photo(job.chat_id, photo=photo_file)

        # Also send geographic data information
        await _send_geographic_info(context.bot, job.chat_id)
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
            await update.message.reply_photo(photo=photo_file, caption="Cropped and processed mushroom map")
    else:
        await update.message.reply_text(
            "No processed map found. Use /run to create one."
        )


async def crop_command(update: Update, context: CallbackContext):
    """
    Handler for the /crop command.
    Manually crop the latest processed image.
    Restricted to admin user.
    """
    # Check if the user sending the command is the admin
    user_id = update.message.from_user.id
    if str(user_id) != str(ADMIN_CHAT_ID):
        await update.message.reply_text(
            "Sorry, you are not authorized to use this command."
        )
        return

    latest_processed = get_latest_image_path(PROCESSED_DIR)
    if not latest_processed:
        await update.message.reply_text("No processed image found to crop.")
        return

    await update.message.reply_text("Cropping latest processed image...")

    # Perform cropping
    result = crop_processed_image(latest_processed)

    if result:
        await update.message.reply_text(
            f"Image cropped successfully!\n"
            f"Crop parameters: Left={CROP_PARAMS['left']}, Right={CROP_PARAMS['right']}, "
            f"Top={CROP_PARAMS['top']}, Bottom={CROP_PARAMS['bottom']}"
        )

        # Send the cropped image
        with open(latest_processed, "rb") as photo_file:
            await update.message.reply_photo(photo=photo_file, caption="Newly cropped image")
    else:
        await update.message.reply_text("Failed to crop the image.")


async def coords_command(update: Update, context: CallbackContext):
    """
    Handler for the /coords command.
    Converts pixel coordinates to geographic coordinates.
    Note: Coordinates are for the CROPPED image.
    Usage: /coords <x> <y>
    """
    if len(context.args) != 2:
        await update.message.reply_text(
            "Usage: /coords <x> <y>\n"
            "Example: /coords 250 180\n"
            "Note: Coordinates are for the cropped image area only."
        )
        return

    try:
        x = int(context.args[0])
        y = int(context.args[1])

        coordinates = get_coordinates_for_pixel(x, y)
        if coordinates:
            lon, lat = coordinates
            await update.message.reply_text(
                f"Pixel ({x}, {y}) in cropped image corresponds to:\n"
                f"Longitude: {lon:.6f}°\n"
                f"Latitude: {lat:.6f}°\n"
                f"Location: {lat:.6f}°N, {lon:.6f}°E"
            )
        else:
            await update.message.reply_text("Error converting coordinates.")

    except ValueError:
        await update.message.reply_text("Please provide valid integer coordinates.")
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")


async def pixel_command(update: Update, context: CallbackContext):
    """
    Handler for the /pixel command.
    Converts geographic coordinates to pixel coordinates.
    Note: Returns coordinates for the CROPPED image.
    Usage: /pixel <longitude> <latitude>
    """
    if len(context.args) != 2:
        await update.message.reply_text(
            "Usage: /pixel <longitude> <latitude>\n"
            "Example: /pixel 14.4378 50.0755\n"
            "Note: Returns pixel coordinates for the cropped image."
        )
        return

    try:
        lon = float(context.args[0])
        lat = float(context.args[1])

        pixel_coords = get_pixel_for_coordinates(lon, lat)
        if pixel_coords:
            x, y = pixel_coords
            await update.message.reply_text(
                f"Coordinates ({lon:.6f}°, {lat:.6f}°) correspond to:\n"
                f"Pixel X: {x} (in cropped image)\n"
                f"Pixel Y: {y} (in cropped image)"
            )
        else:
            await update.message.reply_text("Error converting coordinates.")

    except ValueError:
        await update.message.reply_text("Please provide valid decimal coordinates.")
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")


async def geojson_command(update: Update, context: CallbackContext):
    """Handler for the /geojson command."""
    try:
        # Find the latest GeoJSON file
        if not os.path.exists(GEOJSON_DIR):
            await update.message.reply_text("No GeoJSON files available.")
            return

        geojson_files = [f for f in os.listdir(GEOJSON_DIR) if f.endswith('.geojson')]
        if not geojson_files:
            await update.message.reply_text("No GeoJSON files found. Use /run to generate one.")
            return

        latest_geojson = max(
            [os.path.join(GEOJSON_DIR, f) for f in geojson_files],
            key=os.path.getmtime
        )

        with open(latest_geojson, "rb") as file:
            await update.message.reply_document(
                document=file,
                filename=os.path.basename(latest_geojson),
                caption="Latest mushroom areas GeoJSON file (based on cropped image)"
            )

    except Exception as e:
        await update.message.reply_text(f"Error retrieving GeoJSON: {str(e)}")


async def kml_command(update: Update, context: CallbackContext):
    """Handler for the /kml command."""
    try:
        # Find the latest KML file
        if not os.path.exists(KML_DIR):
            await update.message.reply_text("No KML files available.")
            return

        kml_files = [f for f in os.listdir(KML_DIR) if f.endswith('.kml')]
        if not kml_files:
            await update.message.reply_text("No KML files found. Use /run to generate one.")
            return

        latest_kml = max(
            [os.path.join(KML_DIR, f) for f in kml_files],
            key=os.path.getmtime
        )

        with open(latest_kml, "rb") as file:
            await update.message.reply_document(
                document=file,
                filename=os.path.basename(latest_kml),
                caption="Latest mushroom areas KML file (compatible with Google Earth, based on cropped image)"
            )

    except Exception as e:
        await update.message.reply_text(f"Error retrieving KML: {str(e)}")


async def info_command(update: Update, context: CallbackContext):
    """
    Handler for the /info command.
    Get mushroom information for specific coordinates.
    Usage: /info <longitude> <latitude>
    """
    if len(context.args) != 2:
        await update.message.reply_text(
            "Usage: /info <longitude> <latitude>\n"
            "Example: /info 14.4378 50.0755"
        )
        return

    try:
        lon = float(context.args[0])
        lat = float(context.args[1])

        # Find the latest GeoJSON file
        if not os.path.exists(GEOJSON_DIR):
            await update.message.reply_text("No geographic data available.")
            return

        geojson_files = [f for f in os.listdir(GEOJSON_DIR) if f.endswith('.geojson')]
        if not geojson_files:
            await update.message.reply_text("No geographic data found. Use /run to generate.")
            return

        latest_geojson = max(
            [os.path.join(GEOJSON_DIR, f) for f in geojson_files],
            key=os.path.getmtime
        )

        # Get region information
        region_info = geo_processor.get_region_info(lon, lat, latest_geojson)

        if region_info and region_info.get("found"):
            props = region_info["properties"]
            await update.message.reply_text(
                f"🍄 Mushroom Information for {lat:.6f}°N, {lon:.6f}°E:\n\n"
                f"Probability: {props.get('mushroom_probability', 'Unknown')}\n"
                f"Area: {props.get('area_pixels', 'Unknown')} pixels\n"
                f"Date: {props.get('date', 'Unknown')}\n"
                f"Region ID: {props.get('id', 'Unknown')}\n"
                f"Note: Data based on cropped image analysis"
            )
        else:
            await update.message.reply_text(
                f"No mushroom data found for coordinates {lat:.6f}°N, {lon:.6f}°E"
            )

    except ValueError:
        await update.message.reply_text("Please provide valid decimal coordinates.")
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")


async def _send_geographic_info(bot, chat_id):
    """Send information about the latest geographic files."""
    try:
        messages = []

        # Check GeoJSON
        if os.path.exists(GEOJSON_DIR):
            geojson_files = [f for f in os.listdir(GEOJSON_DIR) if f.endswith('.geojson')]
            if geojson_files:
                latest_geojson = max(
                    [os.path.join(GEOJSON_DIR, f) for f in geojson_files],
                    key=os.path.getmtime
                )

                import json
                with open(latest_geojson, 'r', encoding='utf-8') as f:
                    geojson_data = json.load(f)

                total_features = geojson_data.get('metadata', {}).get('total_features', 0)
                date = geojson_data.get('metadata', {}).get('date', 'Unknown')

                messages.append(
                    f"📍 Geographic Data Generated (from cropped image):\n"
                    f"Date: {date}\n"
                    f"Total mushroom areas found: {total_features}\n"
                    f"Crop applied: {CROP_PARAMS['left']}px left, {CROP_PARAMS['right']}px right, "
                    f"{CROP_PARAMS['top']}px top, {CROP_PARAMS['bottom']}px bottom\n"
                    f"Use /geojson to download GeoJSON data\n"
                    f"Use /kml to download KML data (Google Earth compatible)"
                )

        # Check KML
        if os.path.exists(KML_DIR):
            kml_files = [f for f in os.listdir(KML_DIR) if f.endswith('.kml')]
            if kml_files:
                messages.append("🌍 KML file also generated for Google Earth compatibility")

        # Send messages
        for message in messages:
            await bot.send_message(chat_id, message)

    except Exception as e:
        print(f"Error sending geographic info: {e}")


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
        .read_timeout(60)
        .write_timeout(60)
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

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("run", run_command))
    application.add_handler(CommandHandler("raw", raw_command))
    application.add_handler(CommandHandler("map", map_command))
    application.add_handler(CommandHandler("coords", coords_command))
    application.add_handler(CommandHandler("pixel", pixel_command))
    application.add_handler(CommandHandler("geojson", geojson_command))
    application.add_handler(CommandHandler("kml", kml_command))
    application.add_handler(CommandHandler("crop", crop_command))  # New crop command
    application.add_handler(CommandHandler("info", info_command))

    print("Bot is running with geographic features, KML export, and image cropping... Press Ctrl+C to stop.")
    application.run_polling()


if __name__ == "__main__":
    main()
