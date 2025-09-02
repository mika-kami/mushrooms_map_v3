# Mushroom Growth Probability Bot

A Telegram bot that fetches daily mushroom growth probability maps, processes them to show growth trends over the last four days, and serves the results to users.

## Features

- **Daily x2 Image Fetching**: Automatically downloads a map image every day at 10:00 and 19:00 UTC.
- **Image Processing**: Identifies key areas on the map and creates a weighted composite image from the last four maps to highlight consistent growth areas.
- **Telegram Commands**:
  - `/start`: Shows a welcome message and lists available commands.
  - `/run`: Manually triggers the daily image download and processing job, available for admins only.
  - `/raw`: Displays the most recently downloaded raw map.
  - `/map`: Displays the latest processed composite map.

## Deployment

The bot is designed to be deployed on **AWS Lambda** and uses a CI/CD pipeline with **GitHub Actions** for automated deployments from the `master` branch.

## Setup

1.  **Clone the repository**:
    ```
    git clone <repository-url>
    cd mushroom-map-bot
    ```

2.  **Create a virtual environment**:
    ```
    python -m venv venv
    source venv/bin/activate
    ```

3.  **Install dependencies**:
    ```
    pip install -r requirements.txt
    ```

4.  **Configure environment variables**:
    Create a `.env` file in the root directory and add your Telegram Bot Token and Telegram ID of admin:
    ```
    TELEGRAM_TOKEN="bot_token_here"
    ADMIN_CHAT_ID="telegram_id"
    ```

5.  **Run the bot locally**:
    ```
    python src/bot.py
    ```
