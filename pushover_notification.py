# pushover_notification.py
# MicroPython module for sending one Pushover notification over HTTPS.
#
# Copy this file to the ESP32 filesystem.
# Import it only when a notification is needed, then remove it from
# sys.modules in the calling script and run gc.collect().
#
# IMPORTANT:
#   1. Replace USER_KEY and API_TOKEN below with your Pushover credentials.
#   2. This module does not change Wi-Fi, Google Cloud, Telegram, or GPIO code.
#   3. True means Pushover accepted the request, not that the phone displayed it.

import gc

# ------------------------- USER CONFIGURATION -------------------------

USER_KEY = "u6***ukg"
API_TOKEN = "axz***w4nr"

REQUEST_TIMEOUT_SECONDS = 5
PUSHOVER_URL = "https://api.pushover.net/1/messages.json"

# ---------------------------------------------------------------------


def _url_encode(value):
    """Percent-encode a string for application/x-www-form-urlencoded."""
    if not isinstance(value, str):
        value = str(value)

    encoded = []
    for byte in value.encode("utf-8"):
        if (
            48 <= byte <= 57 or
            65 <= byte <= 90 or
            97 <= byte <= 122 or
            byte in (45, 46, 95, 126)
        ):
            encoded.append(chr(byte))
        elif byte == 32:
            encoded.append("+")
        else:
            encoded.append("%%%02X" % byte)

    return "".join(encoded)


def send_notification(title, message):
    """
    Send one Pushover notification.
    Returns True if Pushover returns HTTP 200; otherwise returns False.

    The installed MicroPython urequests implementation must support the
    timeout keyword. If it does not, this function fails safely rather
    than retrying with no timeout.
    """
    if (
        USER_KEY.startswith("PASTE_") or
        API_TOKEN.startswith("PASTE_") or
        not USER_KEY or
        not API_TOKEN
    ):
        print("[Pushover] Configure USER_KEY and API_TOKEN first.")
        return False

    try:
        import urequests
    except ImportError:
        print("[Pushover] urequests module is not available.")
        return False

    response = None
    try:
        form_data = (
            "token=" + _url_encode(API_TOKEN) +
            "&user=" + _url_encode(USER_KEY) +
            "&title=" + _url_encode(title) +
            "&message=" + _url_encode(message)
        )

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Connection": "close",
        }

        # Do not retry without timeout: that could block the main loop
        # for an unbounded period on a urequests version without timeout.
        response = urequests.post(
            PUSHOVER_URL,
            data=form_data,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        status_code = getattr(response, "status_code", None)
        if status_code == 200:
            print("[Pushover] Notification accepted.")
            return True

        print("[Pushover] HTTP response:", status_code)
        return False

    except TypeError as exc:
        print("[Pushover] This urequests version may not support timeout=5.")
        print("[Pushover] No request was retried without a timeout.")
        print("[Pushover] Details:", exc)
        return False

    except Exception as exc:
        print("[Pushover] Send failed:", exc)
        return False

    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
        response = None
        gc.collect()
