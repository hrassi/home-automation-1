# clock.py give real local time and date and auto synchronyse
#
# USE:
#       import clock
#       print(clock.get_time())
#       print(clock.get_date())
#       print(clock.get_date_time())
#       print(clock.get_day())
#

import ntptime
import utime

TIMEZONE_OFFSET = 2  # lebanon utc + 2 hours
DST_START = (3, 29)  # day light saving time 29 mars
DST_END = (10, 25)   # day light ending time 25 october
DST_OFFSET = 1       # the extra hour added during DST (during summer)

_last_sync = 0
SYNC_INTERVAL = 6 * 60 * 60  # 6 hours


def is_dst(year, month, day):
    start = (year, DST_START[0], DST_START[1])
    end = (year, DST_END[0], DST_END[1])
    today = (year, month, day)
    return start <= today < end


def _sync_time():
    global _last_sync
    try:
        ntptime.settime()
        _last_sync = utime.time()
    except:
        pass


def _ensure_synced():
    global _last_sync
    if _last_sync == 0 or (utime.time() - _last_sync) > SYNC_INTERVAL:
        _sync_time()


def get_time():
    """
    Returns local time string (auto-sync included)
    """
    _ensure_synced()

    t = utime.localtime()

    year, month, day = t[0], t[1], t[2]
    hour, minute, second = t[3], t[4], t[5]

    offset = TIMEZONE_OFFSET
    if is_dst(year, month, day):
        offset += DST_OFFSET

    # apply timezone shift
    t_sec = utime.mktime(t)
    t_sec += offset * 3600

    local = utime.localtime(t_sec)

    return "{:02d}:{:02d}:{:02d}".format(
    local[3], local[4], local[5]
    )


def get_date():
    """
    Returns local time string (auto-sync included)
    """
    _ensure_synced()

    t = utime.localtime()

    year, month, day = t[0], t[1], t[2]
    hour, minute, second = t[3], t[4], t[5]

    offset = TIMEZONE_OFFSET
    if is_dst(year, month, day):
        offset += DST_OFFSET

    # apply timezone shift
    t_sec = utime.mktime(t)
    t_sec += offset * 3600

    local = utime.localtime(t_sec)
    
    return "{:02d}-{:02d}-{:04d}".format(
    local[2], local[1], local[0]
    )


def get_day():
    """
    Returns local time string (auto-sync included)
    """
    _ensure_synced()

    t = utime.localtime()

    year, month, day = t[0], t[1], t[2]
    hour, minute, second = t[3], t[4], t[5]

    offset = TIMEZONE_OFFSET
    if is_dst(year, month, day):
        offset += DST_OFFSET

    # apply timezone shift
    t_sec = utime.mktime(t)
    t_sec += offset * 3600

    local = utime.localtime(t_sec)
    
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_name = days[local[6]]

    return day_name

def get_date_time():
    """
    Returns local time string (auto-sync included)
    """
    _ensure_synced()

    t = utime.localtime()

    year, month, day = t[0], t[1], t[2]
    hour, minute, second = t[3], t[4], t[5]

    offset = TIMEZONE_OFFSET
    if is_dst(year, month, day):
        offset += DST_OFFSET

    # apply timezone shift
    t_sec = utime.mktime(t)
    t_sec += offset * 3600

    local = utime.localtime(t_sec)

    return "{:02d}-{:02d}-{:04d} {:02d}:{:02d}:{:02d}".format(
        local[2], local[1], local[0],
        local[3], local[4], local[5]
    )


