# wifi_connect.py — autonomous WiFi manager (ESP32 MicroPython v1.28+)
# will keep trying to connect and check for wifi and internet if not it reconnect
# USAGE:
#        from wifi_connect import wifi_loop
#        MyNetwork = "Rassi Net3"
#        MyPassword = "H******t"
#
#        while True:
#           wifi_loop(MyNetwork, MyPassword)
#
#           Your system runs freely here (MQTT, sensors, UI, etc.)
#           
#           time.sleep_ms(100)
#
# # ───── 1. WAIT FOR WIFI AT STARTUP ─────
#
# print("[System] Connecting to WiFi...")
#
# while not wifi_loop(MyNetwork, MyPassword):
#    
#     time.sleep_ms(500)
#
# print("[System] WiFi connected!")
#
#


# wifi_connect.py — tolerant Wi-Fi manager
# Compatible with MicroPython on ESP32

import network
import time
import socket
from machine import Pin

_STA = getattr(network.WLAN, "IF_STA", network.STA_IF)
wlan = network.WLAN(_STA)

onboard_led = Pin(2, Pin.OUT)
onboard_led.off()

# Reconnection timing
_last_attempt = 0
_retry_interval = 5000

# Internet health checking
_last_health_check = 0
_health_interval = 10000
_health_failures = 0
_MAX_HEALTH_FAILURES = 3

_connecting = False


def wifi_loop(ssid, password, power_save=False):
    """
    Call repeatedly from main.py.

    A temporary Internet failure is tolerated.
    Three consecutive failed health checks trigger reconnection.
    """

    global _last_attempt, _connecting
    global _last_health_check, _health_failures

    now = time.ticks_ms()

    # Wi-Fi connected
    if wlan.isconnected():

        if _connecting:
            pm = (
                network.WLAN.PM_PERFORMANCE
                if power_save
                else network.WLAN.PM_NONE
            )

            try:
                wlan.config(pm=pm)
            except Exception:
                pass

            print(
                "[WiFi] Connected! IP:", wlan.ifconfig()[0],
                "RSSI:", wlan.status("rssi"),
                "dBm Power Management:", pm
            )

            onboard_led.on()
            _connecting = False
            _health_failures = 0
            _last_health_check = now

        # Periodic Internet health check
        if time.ticks_diff(now, _last_health_check) >= _health_interval:
            _last_health_check = now

            if _internet_ok():
                if _health_failures:
                    print("[WiFi] Internet restored")
                _health_failures = 0

            else:
                _health_failures += 1

                print(
                    "[WiFi] Internet check failed:",
                    _health_failures,
                    "of", _MAX_HEALTH_FAILURES
                )

                if _health_failures >= _MAX_HEALTH_FAILURES:
                    print(
                        "[WiFi] Internet unavailable repeatedly; "
                        "reconnecting Wi-Fi"
                    )

                    onboard_led.off()
                    _force_reconnect(ssid, password)
                    _connecting = True
                    _last_attempt = now
                    _health_failures = 0

                    return False

        return True

    # Wi-Fi disconnected: retry periodically
    if time.ticks_diff(now, _last_attempt) >= _retry_interval:
        print("[WiFi] Wi-Fi disconnected; reconnecting...")
        onboard_led.off()

        _force_reconnect(ssid, password)

        _connecting = True
        _last_attempt = now

    return False


def _force_reconnect(ssid, password):
    """Restart the station interface and request a connection."""

    try:
        wlan.disconnect()
    except Exception:
        pass

    try:
        wlan.active(False)
        time.sleep_ms(100)
    except Exception:
        pass

    wlan.active(True)

    try:
        wlan.connect(ssid, password)
    except Exception as e:
        print("[WiFi] Connect request error:", e)



def _internet_ok(timeout=2):
    """
    Internet is considered available if ANY destination responds.
    All destinations require DNS resolution.
    Only return False if all destinations fail.
    The caller handles the three consecutive failed health checks.
    """
    targets = (
        ("www.google.com", 443),       # Google
        ("api.telegram.org", 443),     # Telegram
        ("www.cloudflare.com", 443),   # Cloudflare
        ("www.microsoft.com", 443),    # Microsoft
    )

    for host, port in targets:
        s = None
        try:
            addr = socket.getaddrinfo(host, port)[0][-1]
            s = socket.socket()
            s.settimeout(timeout)
            s.connect(addr)
            return True
        except Exception:
            pass
        finally:
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass

    return False
