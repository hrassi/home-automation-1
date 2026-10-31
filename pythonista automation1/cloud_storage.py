'''
=====================================
Basic Fonctions of cloud_storage.py :
	
cloud_storage.write("test.txt", "Hello")  
#create/overwrite
cloud_storage.read("test.txt")                 # read
cloud_storage.exists("test.txt")               # check
cloud_storage.delete("test.txt")               # delete
cloud_storage.write_json("esp4.json", data)    # JSON create/overwrite
cloud_storage.read_json("esp4.json")            # JSON read

======================================
'''


import requests
import hashlib
import hmac
import datetime
from urllib.parse import quote
import json
import time

# ============================================================
# GOOGLE CLOUD STORAGE SETTINGS
# ============================================================


ACCESS_ID="GOOG***************EPWZ"
SECRET = "3YW************0j5u"

BUCKET = "sam_cloud_1"
REGION = "us-central1"

HOST = "storage.googleapis.com"
SERVICE = "storage"


# ============================================================
# INTERNAL FUNCTIONS
# ============================================================

def _encode(value):
    return quote(str(value), safe="")


def _hmac_sha256(key, message):
    return hmac.new(
        key,
        message.encode("utf-8"),
        hashlib.sha256
    ).digest()


def _signed_request(method, filename, data=None):

    now = datetime.datetime.utcnow()

    date = now.strftime("%Y%m%d")
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")

    path = "/" + BUCKET + "/" + quote(filename, safe="/")

    credential_scope = (
        date + "/" +
        REGION + "/" +
        SERVICE +
        "/goog4_request"
    )

    credential = ACCESS_ID + "/" + credential_scope

    params = {
        "X-Goog-Algorithm": "GOOG4-HMAC-SHA256",
        "X-Goog-Credential": credential,
        "X-Goog-Date": timestamp,
        "X-Goog-Expires": "900",
        "X-Goog-SignedHeaders": "host"
    }

    canonical_query = "&".join(
        _encode(k) + "=" + _encode(params[k])
        for k in sorted(params)
    )

    canonical_headers = "host:" + HOST + "\n"
    signed_headers = "host"

    # --------------------------------------------------------
    # Payload hash
    # --------------------------------------------------------

    if data is None:
        payload_hash = "UNSIGNED-PAYLOAD"
    else:
        if isinstance(data, str):
            data_bytes = data.encode("utf-8")
        else:
            data_bytes = data

        payload_hash = hashlib.sha256(data_bytes).hexdigest()

    # --------------------------------------------------------
    # Canonical request
    # --------------------------------------------------------

    canonical_request = (
        method + "\n" +
        path + "\n" +
        canonical_query + "\n" +
        canonical_headers + "\n" +
        signed_headers + "\n" +
        payload_hash
    )

    hashed_request = hashlib.sha256(
        canonical_request.encode("utf-8")
    ).hexdigest()

    # --------------------------------------------------------
    # String to sign
    # --------------------------------------------------------

    string_to_sign = (
        "GOOG4-HMAC-SHA256\n" +
        timestamp + "\n" +
        credential_scope + "\n" +
        hashed_request
    )

    # --------------------------------------------------------
    # Signing key
    # --------------------------------------------------------

    secret_bytes = SECRET.encode("utf-8")

    k_date = _hmac_sha256(
        b"GOOG4" + secret_bytes,
        date
    )

    k_region = _hmac_sha256(
        k_date,
        REGION
    )

    k_service = _hmac_sha256(
        k_region,
        SERVICE
    )

    k_signing = _hmac_sha256(
        k_service,
        "goog4_request"
    )

    signature = hmac.new(
        k_signing,
        string_to_sign.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    # --------------------------------------------------------
    # Final URL
    # --------------------------------------------------------

    url = (
        "https://" +
        HOST +
        path +
        "?" +
        canonical_query +
        "&X-Goog-Signature=" +
        signature
    )

    # --------------------------------------------------------
    # Perform request
    # --------------------------------------------------------

    headers = {}

    if data is not None:
        headers["x-goog-content-sha256"] = payload_hash
        headers["Content-Type"] = "text/plain"

    return requests.request(
        method,
        url,
        data=data,
        headers=headers
    )


# ============================================================
# PUBLIC FUNCTIONS
# ============================================================

def write(filename, data):
    """
    Create a file or overwrite it if it already exists.

    Example:
        cloud_storage.write(
            "test.txt",
            "Hello from Pythonista!"
        )

    Returns:
        True  = success
        False = failed
    """

    response = _signed_request(
        "PUT",
        filename,
        data
    )

    success = response.status_code in (200, 201)

    response.close()

    return success


def read(filename):
    time.sleep(0.05)
    """
    Read a file from Google Cloud Storage.

    Returns:
        File contents as text
        None if the server returns a non-200 status.
        Raises an exception if the request fails.
    """

    try:
        response = _signed_request("GET", filename)
        time.sleep(0.05)

        if response.status_code == 200:
            result = response.text
            response.close()
            time.sleep(0.05)
            return result

        response.close()
        time.sleep(0.05)
        return None

    except Exception:
        time.sleep(0.05)
        raise


def read_json(filename):
    """
    Read a JSON file and return a Python object.

    Returns:
        dict/list/etc. on success
        None if the file cannot be read or JSON is invalid.
        Raises request exceptions to the caller.
    """

    try:
        data = read(filename)

        if data is None:
            return None

        try:
            return json.loads(data)

        except Exception:
            return None

    except Exception:
        raise


"""
def read(filename):
    
    Read a file from Google Cloud Storage.
    Print diagnostic information for debugging.
    

    print("\n========== CLOUD READ DEBUG ==========")
    print("Filename:", repr(filename))

    try:
        response = _signed_request("GET", filename)

        print("HTTP status:", response.status_code)
        print("Response headers:", response.headers)

        if response.status_code == 200:
            result = response.text

            print("Downloaded content type:", type(result))
            print("Downloaded content length:", len(result))
            print("Downloaded content:")
            print(repr(result))

            response.close()

            print("========== CLOUD READ SUCCESS ==========\n")
            return result

        print("Cloud returned an error response:")
        print(repr(response.text))

        response.close()

        print("========== CLOUD READ FAILED ==========\n")
        return None

    except Exception as error:
        import traceback

        print("EXCEPTION DURING CLOUD READ:", repr(error))
        traceback.print_exc()

        print("========== CLOUD READ EXCEPTION ==========\n")
        raise

"""



def exists(filename):
    """
    Check whether a file exists.

    Returns:
        True / False
    """

    response = _signed_request(
        "GET",
        filename
    )

    exists = response.status_code == 200

    response.close()

    return exists


def delete(filename):
    """
    Delete a file.

    Returns:
        True  = deleted successfully
        False = failed
    """

    response = _signed_request(
        "DELETE",
        filename
    )

    success = response.status_code in (200, 204)

    response.close()

    return success


def write_json(filename, obj):
    """
    Write a Python dictionary/list as a JSON file.

    Example:
        cloud_storage.write_json(
            "esp4.json",
            {
                "tank1": 72,
                "tank2": 48
            }
        )
    """

    data = json.dumps(obj)

    response = _signed_request(
        "PUT",
        filename,
        data
    )

    success = response.status_code in (200, 201)

    response.close()

    return success

"""
def read_json(filename):

    print("\n========== JSON DEBUG ==========")

    data = read(filename)

    if data is None:
        print("No file content received.")
        print("========== JSON DEBUG END ==========\n")
        return None

    try:
        result = json.loads(data)

        print("JSON decoded successfully.")
        print("Decoded object type:", type(result))

        if isinstance(result, dict):
            print("JSON keys:", list(result.keys()))

        print("========== JSON DEBUG END ==========\n")
        return result

    except Exception as error:
        import traceback

        print("JSON decoding failed:", repr(error))
        traceback.print_exc()
        print("Raw data was:", repr(data))

        print("========== JSON DEBUG END ==========\n")
        return None
"""




def list_files():
    """
    Return a list of object/file names in the bucket.
    """

    # This uses the GCS JSON API and therefore requires
    # a different authentication method than our HMAC
    # XML API signing. We will add this separately if needed.

    return None
    
