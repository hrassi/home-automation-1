from pathlib import Path

# telegram_pythonista.py
# Telegram command sender for the Pythonista Home Automation console.
#
# This module only SENDS messages. It does not poll Telegram or receive updates.
# The Pythonista Controller bot sends a command addressed to the selected ESP bot.
# The ESP's own MicroPython code is responsible for receiving and executing it.

import requests


# ============================================================================
# 1. CONFIGURATION
# Edit this section when setting up the module.
# ============================================================================

# Token of @SamPythonistaControllerBot
CONTROLLER_BOT_TOKEN = "880**************Sk0"

# Map each console ESP ID to its Telegram bot username.
# Use the exact usernames of the ESP bots.
ESP_BOTS = {
    "esp1": "@SamEsp1Bot",
     "esp2": "@SamEsp2Bot",
     "esp3": "@SamEsp3Bot",
     "esp4": "@SamEsp4Bot",
}

REQUEST_TIMEOUT = 10


# ============================================================================
# 2. SENDING FUNCTION
# Example: send_message("esp1", "GPIO25 ON")
#
# Returns:
#   (True, confirmation_text) if Telegram accepts the request.
#   (False, error_text) if configuration, network, or Telegram reports an error.
#
# Important: "True" means Telegram accepted the send request. It does not prove
# that the ESP executed the command. The dashboard should display the confirmed
# GPIO state from Google Cloud, not assume the requested state was applied.
# ============================================================================

def send_message(esp_number, message):
    """Send a text command to the configured ESP bot."""
    if (
        not CONTROLLER_BOT_TOKEN
        or CONTROLLER_BOT_TOKEN == "PASTE_CONTROLLER_BOT_TOKEN_HERE"
    ):
        return False, "Controller bot token has not been configured."

    esp_id = str(esp_number).strip().lower()
    bot_username = ESP_BOTS.get(esp_id)

    if not bot_username:
        return False, "No Telegram bot is configured for {}.".format(esp_id)

    text = str(message).strip()
    if not text:
        return False, "Message is empty."

    url = "https://api.telegram.org/bot{}/sendMessage".format(
        CONTROLLER_BOT_TOKEN
    )

    try:
        response = requests.post(
            url,
            data={
                "chat_id": bot_username,
                "text": text,
            },
            timeout=REQUEST_TIMEOUT,
        )

        try:
            result = response.json()
        except Exception:
            return False, "Telegram returned a non-JSON response (HTTP {}).".format(
                response.status_code
            )

        if response.status_code == 200 and result.get("ok") is True:
            return True, "Telegram accepted the message for {}.".format(
                bot_username
            )

        error_code = result.get("error_code", response.status_code)
        description = result.get("description", "Unknown Telegram API error")
        return False, "Telegram error {}: {}".format(error_code, description)

    except Exception as exc:
        return False, "Could not contact Telegram: {}".format(exc)


# ============================================================================
# 3. STANDALONE TEST
# Run this file directly in Pythonista to send one harmless test message.
# Importing this module from dashboard.py does not run this test.
# ============================================================================
"""
if __name__ == "__main__":
    success, detail = send_message(
        "esp1",
        "TEST from Pythonista Controller"
    )
    print("SUCCESS:" if success else "FAILED:", detail)
"""
