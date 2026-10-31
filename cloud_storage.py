import urequests
import ujson
import hashlib
import time
import ntptime
import gc
import ubinascii


# ============================================================
# GOOGLE CLOUD STORAGE — V4 SIGNED REQUESTS
# ============================================================

HOST = "storage.googleapis.com"


def _sha256(data):
    return ubinascii.hexlify(hashlib.sha256(data).digest()).decode()


def _hmac_sha256(key, message):
    # HMAC-SHA256 implemented for MicroPython.
    # The Google HMAC secret is used as-is; do NOT Base64-decode it.

    if len(key) > 64:
        key = hashlib.sha256(key).digest()

    key_block = bytearray(64)
    key_block[:len(key)] = key

    inner_pad = bytearray(64)
    outer_pad = bytearray(64)

    for i in range(64):
        inner_pad[i] = key_block[i] ^ 0x36
        outer_pad[i] = key_block[i] ^ 0x5c

    inner = hashlib.sha256(bytes(inner_pad) + message).digest()
    return hashlib.sha256(bytes(outer_pad) + inner).digest()


def _signing_key(secret, date, region):
    key = ("GOOG4" + secret).encode()

    key = _hmac_sha256(key, date.encode())
    key = _hmac_sha256(key, region.encode())
    key = _hmac_sha256(key, b"storage")
    key = _hmac_sha256(key, b"goog4_request")

    return key


def sync_time():
    # Google V4 signing requires an accurate UTC clock.
    try:
        ntptime.settime()
        now = time.gmtime()
        print(
            "[Cloud] UTC clock synchronized:",
            "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
                now[0], now[1], now[2],
                now[3], now[4], now[5]
            )
        )
        return True

    except Exception as e:
        print("[Cloud] Clock synchronization failed:", e)
        return False


def _request(method, access_id, secret, bucket, region,
             object_name, payload=None):

    response = None

    try:
        if payload is None:
            payload = b""

        payload_hash = _sha256(payload)

        now = time.gmtime()
        timestamp = (
            "{:04d}{:02d}{:02d}T{:02d}{:02d}{:02d}Z".format(
                now[0], now[1], now[2],
                now[3], now[4], now[5]
            )
        )
        date = timestamp[:8]

        # For the first test, use a simple object name such as
        # test_esp.json or esp1.json.
        uri = "/" + bucket + "/" + object_name
        url = "https://" + HOST + uri

        
        canonical_headers = (
            "host:" + HOST + "\n"
            "x-goog-content-sha256:" + payload_hash + "\n"
            "x-goog-date:" + timestamp + "\n"
        )

        signed_headers = "host;x-goog-content-sha256;x-goog-date"

        canonical_request = (
            method + "\n" +
            uri + "\n" +
            "\n" +
            canonical_headers +
            "\n" +
            signed_headers + "\n" +
            payload_hash
        )

        scope = date + "/" + region + "/storage/goog4_request"

        string_to_sign = (
            "GOOG4-HMAC-SHA256\n" +
            timestamp + "\n" +
            scope + "\n" +
            _sha256(canonical_request.encode())
        )

        signing_key = _signing_key(secret, date, region)
        signature = ubinascii.hexlify(
            _hmac_sha256(signing_key, string_to_sign.encode())
        ).decode()

        authorization = (
            "GOOG4-HMAC-SHA256 "
            "Credential=" + access_id + "/" + scope +
            ", SignedHeaders=" + signed_headers +
            ", Signature=" + signature
        )

        headers = {
            "Content-Type": "application/json",
            "Host": HOST,
            "x-goog-content-sha256": payload_hash,
            "x-goog-date": timestamp,
            "Authorization": authorization
        }

        if method == "PUT":
            response = urequests.put(
                url, data=payload, headers=headers
            )
        elif method == "GET":
            response = urequests.get(url, headers=headers)
        else:
            raise ValueError("Unsupported HTTP method")

        status = response.status_code

        if status not in (200, 201):
            print("[Cloud] HTTP status:", status)
            try:
                print("[Cloud] Response:", response.text[:300])
            except:
                pass
            return None

        if method == "GET":
            return response.text

        return True

    except Exception as e:
        print("[Cloud] Request error:", e)
        return None

    finally:
        if response is not None:
            try:
                response.close()
            except:
                pass

        gc.collect()


def write_json(access_id, secret, bucket, region,
               object_name, data):

    body = ujson.dumps(data).encode()

    result = _request(
        "PUT", access_id, secret, bucket, region,
        object_name, body
    )

    if result:
        print("[Cloud] JSON written:", object_name)
        return True

    return False


def read_json(access_id, secret, bucket, region, object_name):

    result = _request(
        "GET", access_id, secret, bucket, region,
        object_name
    )

    if result is None:
        return None

    try:
        data = ujson.loads(result)
        print("[Cloud] JSON read:", object_name)
        return data

    except Exception as e:
        print("[Cloud] JSON decode error:", e)
        return None
