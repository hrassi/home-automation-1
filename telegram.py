
import urequests
import ujson
import gc



def send_notification(token, sam_chat_id, device_id, message):
    """
    Send an urgent notification to Sam's personal Telegram chat.
    """
    return send_telegram(
        token,
        sam_chat_id,
        device_id,
        message
    )



def send_telegram(token, chat_id, device_id, message):
    response = None

    try:
        url = "https://api.telegram.org/bot{}/sendMessage".format(token)

        payload = {
            "chat_id": chat_id,
            "text": "{}: {}".format(device_id, message)
        }

        headers = {
            "Content-Type": "application/json"
        }
        print("DEBUG payload:", ujson.dumps(payload))
        response = urequests.post(
            url,
            data=ujson.dumps(payload),
            headers=headers,
            timeout=10
        )

        print("Telegram send status:", response.status_code)

        if response.status_code != 200:
            try:
                print("Telegram error:", response.text)
            except Exception:
                print("Could not read Telegram error response")

        return response.status_code == 200

    except Exception as e:
        print("Telegram send error:", e)
        return False

    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass

        gc.collect()




def receive_telegram(token, offset):
    response = None

    try:
        import time

        url = (
            "https://api.telegram.org/bot{}/getUpdates"
            "?offset={}&limit=100&timeout=1"
        ).format(token, offset)

        response = urequests.get(url, timeout=10)

        if response.status_code != 200:
            print("Telegram receive status:", response.status_code)
            return None, offset

        data = response.json()

        if not data.get("ok"):
            return None, offset

        updates = data.get("result", [])

        if not updates:
            return None, offset

        # Always advance beyond every update returned.
        next_offset = updates[-1]["update_id"] + 1

        # Examine only the newest update in this batch.
        latest_update = updates[-1]
        message = latest_update.get("message", {})
        text = message.get("text")
        message_date = message.get("date")

        if not text or not isinstance(message_date, (int, float)):
            print("[Telegram] Latest update has no valid text message")
            return None, next_offset

        # Convert MicroPython's timestamp to Unix time.
        # MicroPython may use an epoch starting in 2000,
        # while Telegram uses the Unix epoch starting in 1970.
        current_time = time.time()
        
        print("DEBUG ESP time:", current_time)
        print("DEBUG Telegram time:", message_date)
        
        if current_time < 1000000000:
            current_time += 946684800

        age_seconds = current_time - message_date

        if age_seconds < -5 or age_seconds > 600:
            print(
                "[Telegram] Latest message ignored; age:",
                age_seconds,
                "seconds"
            )
            return None, next_offset

        chat = message.get("chat", {})
        print("Telegram received:", text)
        print("Incoming chat ID:", chat.get("id"))
        print("Message age:", age_seconds, "seconds")

        return text, next_offset

    except Exception as e:
        print("Telegram receive error:", e)
        return None, offset

    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass

        gc.collect()

