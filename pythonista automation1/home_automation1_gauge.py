# =============================================================
# VINTAGE HOME AUTOMATION INTERFACE — VERSION 5
# Pythonista on iPhone
#
# PURPOSE
#   A vintage-style controller for four ESP32 devices.
#   It reads each device's JSON file from Google Cloud Storage and
#   sends GPIO25 ON/OFF commands through telegram_pythonista.py.
#
# IMPORTANT
#   - Keep cloud_storage.py and telegram_pythonista.py as separate modules.
#   - Keep the image files listed in the interface section in this folder.
#   - This version keeps the tested behavior of user_interface4.py.
#   - Only a selector change animates the gauge. Normal refreshes update it
#     immediately, so there are no repeated animations during polling.
# ============================================================

import ui
import threading
import datetime
from objc_util import UIApplication

import cloud_storage
import telegram_pythonista
from gaugeview import GaugeView


# ============================================================
# 1. SETTINGS — EDIT THESE VALUES WHEN NEEDED
# ============================================================

# The selector position chooses one item from this list:
#   1 = SONAR / esp1.json
#   2 = GARDEN / esp2.json
#   3 = ROOF / esp3.json
#   4 = HEATER / esp4.json
# Add or change devices here, keeping the matching JSON filenames correct.
DEVICES = [
    {'name': 'SONAR',  'esp_id': 'esp1', 'filename': 'esp1.json', 'command_filename': 'esp1_command.json'},
    {'name': 'GARDEN', 'esp_id': 'esp2', 'filename': 'esp2.json', 'command_filename': 'esp2_command.json'},
    {'name': 'ROOF',   'esp_id': 'esp3', 'filename': 'esp3.json', 'command_filename': 'esp3_command.json'},
    {'name': 'HEATER', 'esp_id': 'esp4', 'filename': 'esp4.json', 'command_filename': 'esp4_command.json'},
]

# Read the selected ESP automatically every 10 seconds.
AUTO_REFRESH_SECONDS = 10

# After a command is sent, wait 4 seconds before checking ESP status.
COMMAND_REFRESH_DELAY = 4

# Scheduled fallback polling interval sent to the selected ESP in its command JSON.
FALLBACK_INTERVAL = 30  # Seconds

# Possible JSON keys that may contain the sensor value shown on the gauge.
# The first matching non-empty key is used.
GAUGE_VALUE_KEYS = (
    'analog33', 'analog34', 'gpio33', 'input33',
    'pot', 'temperature', 'temp', 'value'
)

# The selector animation is deliberately short and runs only when changing ESP.
# The needle goes to zero, cloud data is read, then the needle goes to the value.
SELECTOR_DOWN_SECONDS = 0.2
SELECTOR_UP_SECONDS = 0.4
ANIMATION_STEPS = 30


# ============================================================
# 2. MAIN VIEW AND ORIGINAL VINTAGE ARTWORK
# ============================================================

root = ui.View()
root.name = 'Home Automation'

# Full-screen background image.
background = ui.ImageView()
background.image = ui.Image.named('IMG_3643.PNG')
background.frame = root.bounds
background.flex = 'WH'
root.add_subview(background)

# Rectangular black-leather panel.
panel = ui.View()
panel.frame = (15, 35, 400, 600)
panel.corner_radius = 12
panel.border_width = 2
panel.border_color = '#9b9ba4'
panel.clips_to_bounds = True

panel_image = ui.ImageView()
panel_image.frame = panel.bounds
panel_image.image = ui.Image.named('black_leather.jpg')
panel_image.content_mode = ui.CONTENT_SCALE_TO_FILL
panel.add_subview(panel_image)
root.add_subview(panel)

# Round metallic frame behind the gauge.
panel2 = ui.View()
panel2.frame = (35, 119, 362, 362)
panel2.corner_radius = 180
panel2.border_width = 2
panel2.border_color = '#9b9ba4'
panel2.clips_to_bounds = True

panel2_image = ui.ImageView()
panel2_image.frame = panel2.bounds
panel2_image.image = ui.Image.named('round_frame2.jpg')
panel2_image.content_mode = ui.CONTENT_SCALE_TO_FILL
panel2.add_subview(panel2_image)
root.add_subview(panel2)


# ============================================================
# 3. GAUGE
# ============================================================

# GaugeView is defined in the separate gaugeview.py module.
# Its set_value(number) method changes the displayed number and needle position.
g = GaugeView(frame=(30, 110, 380, 380), bg_color='None')
g.flex = ''
g.min_angle = -212
g.max_angle = 28
g.needle_length = 150
g.needle_tail = 30
g.pivot_radius = 4
g.set_value(0)
g.label_font_size = 14
g.label_color = (0, 0, 0)
g.label_font_name = 'Noteworthy-Light'
g.label_y_offset = 25
root.add_subview(g)


# ============================================================
# 4. GREEN DIGITAL SCREEN
# ============================================================

button_screen = ui.Button()
button_screen.frame = (50, 60, 330, 40)
button_screen.background_image = ui.Image.named('vintage_screen2.jpg')
button_screen.corner_radius = 15
button_screen.border_width = 0
button_screen.border_color = '#9b9ba4'
button_screen.enabled = False
root.add_subview(button_screen)

label_screen = ui.Label()
label_screen.text = 'Connecting to cloud...'
label_screen.frame = button_screen.frame
label_screen.border_width = 0
label_screen.border_color = 'white'
label_screen.corner_radius = 12
label_screen.font = ('DBLCDTempBlack', 12)
label_screen.text_color = '#00FF55'
label_screen.alignment = ui.ALIGN_CENTER
label_screen.background_color = 'clear'
label_screen.number_of_lines = 2
root.add_subview(label_screen)


# ============================================================
# 5. DEVICE SELECTOR
# ============================================================

# selector is a position in DEVICES: 1, 2, 3, or 4.
selector = 1

button_selector = ui.Button()
button_selector.frame = (45, 480, 115, 115)
button_selector.background_image = ui.Image.named('1.JPG')
button_selector.corner_radius = 55
button_selector.border_width = 2
button_selector.border_color = '#9b9ba4'
root.add_subview(button_selector)


def selected_device():
    """Return the configuration dictionary for the currently selected ESP."""
    return DEVICES[selector - 1]


def update_selected_device_display():
    """Update the gauge label and selector artwork for the selected ESP."""
    g.label_text = selected_device()['name']
    g.set_needs_display()
    button_selector.background_image = ui.Image.named(str(selector) + '.JPG')


def button_clear1_pressed(sender):
    """Cycle to the next ESP and run the special selector transition."""
    global selector, loading, request_id, selector_transition

    # Invalidate a cloud request for the old device, if one is still running.
    request_id += 1
    loading = False

    selector += 1
    if selector > len(DEVICES):
        selector = 1

    update_selected_device_display()

    # The transition has priority over automatic/manual refreshes:
    # 1) animate the needle down to zero;
    # 2) read the newly selected ESP's cloud JSON;
    # 3) animate up to its new value.
    selector_transition = True
    animate_needle_to(
        0,
        duration=SELECTOR_DOWN_SECONDS,
        on_complete=read_after_selector_change
    )


# Transparent button overlays the selector image so taps do not hide the image.
button_clear1 = ui.Button()
button_clear1.frame = button_selector.frame
button_clear1.background_color = 'clear'
button_clear1.action = button_clear1_pressed
root.add_subview(button_clear1)


# ============================================================
# 6. VINTAGE SWITCH — SENDS GPIO25 COMMANDS
# ============================================================

# button99 displays the switch artwork. The transparent vintage_switch button
# sits on top and receives taps.
button99 = ui.Button()
button99.frame = (330, 485, 60, 100)
button99.background_image = ui.Image.named('switch_off.jpg')
button99.corner_radius = 5
button99.border_width = 1
button99.border_color = '#9b9ba4'
button99.enabled = False
root.add_subview(button99)

vintage_switch = ui.Button()
vintage_switch.frame = button99.frame
vintage_switch.value = False
vintage_switch.background_color = 'clear'
vintage_switch.border_width = 0
vintage_switch.tint_color = 'clear'
vintage_switch.corner_radius = 15
root.add_subview(vintage_switch)


def set_switch_visual(is_on):
    """Show the ON or OFF switch image and keep its logical value in sync."""
    vintage_switch.value = bool(is_on)
    button99.background_image = ui.Image.named(
        'switch_on.jpg' if is_on else 'switch_off.jpg'
    )


def vintage_switch_pressed(sender):
    """Toggle GPIO25 on the selected ESP by sending a Telegram command."""
    requested_state = not bool(vintage_switch.value)
    set_switch_visual(requested_state)
    command = 'GPIO25 ON' if requested_state else 'GPIO25 OFF'
    send_command(command, requested_state)


vintage_switch.action = vintage_switch_pressed


# ============================================================
# 7. FOOTER, EXIT BUTTON, AND MANUAL REFRESH BUTTON
# ============================================================

label2 = ui.Label()
label2.text = 'By Sam'
label2.font = ('<MarkerFelt-Thin>', 20)
label2.text_color = '#cfcfcf'
label2.alignment = ui.ALIGN_CENTER
label2.frame = (20, 590, 385, 50)
label2.flex = 'W'
root.add_subview(label2)

# State variables used to stop pending work and reject stale cloud responses.
running = True
animation_id = 0
selector_transition = False
loading = False
request_id = 0

# Serialize Pythonista read-modify-write operations on command JSON files.
command_file_lock = threading.Lock()


def normalize_gpio_state(value, default='OFF'):
    """Normalize GPIO values from old and new JSON formats to ON/OFF."""
    if value is True or value == 1:
        return 'ON'
    if value is False or value == 0:
        return 'OFF'
    text = str(value).strip().upper()
    if text in ('ON', 'TRUE', '1'):
        return 'ON'
    if text in ('OFF', 'FALSE', '0'):
        return 'OFF'
    return default


def read_command_document(device):
    """Read command JSON; if it does not exist, seed from actual ESP state."""
    try:
        data = cloud_storage.read_json(device['command_filename'])
        if isinstance(data, dict):
            return data
    except Exception as error:
        print('Command JSON not available for {}: {}'.format(device['esp_id'], repr(error)))

    try:
        status = cloud_storage.read_json(device['filename'])
    except Exception:
        status = None

    if not isinstance(status, dict):
        status = {}

    return {
        'gpio25_request': normalize_gpio_state(status.get('gpio25')),
        'gpio26_request': normalize_gpio_state(status.get('gpio26')),
        'gpio27_request': normalize_gpio_state(status.get('gpio27')),
        'fallback_enabled': False,
        'fallback_interval': FALLBACK_INTERVAL,
    }


def write_command_document(device, changes):
    """Update only specified fields and write the selected ESP's command file."""
    with command_file_lock:
        document = read_command_document(device)
        if not isinstance(document, dict):
            document = {}

        # Preserve every requested GPIO state when changing another field.
        for gpio in ('gpio25', 'gpio26', 'gpio27'):
            key = gpio + '_request'
            document[key] = normalize_gpio_state(document.get(key))

        document['fallback_enabled'] = bool(document.get('fallback_enabled', False))
        try:
            interval = int(document.get('fallback_interval', FALLBACK_INTERVAL))
        except (TypeError, ValueError):
            interval = FALLBACK_INTERVAL
        document['fallback_interval'] = max(5, interval)
        document.update(changes)
        document['fallback_interval'] = max(5, int(document.get('fallback_interval', FALLBACK_INTERVAL)))

        # Pythonista cloud_storage API: write_json(filename, dictionary).
        result = cloud_storage.write_json(device['command_filename'], document)
        if result is False:
            raise RuntimeError('Cloud storage reported that the command JSON write failed')
        return document


def cloud_timing_switch_pressed(sender):
    """Save fallback polling setting, then trigger an immediate ESP check."""
    requested_state = not bool(cloud_timing_switch.value)
    device = selected_device()
    label_screen.text = '{}: SAVING POLLING SETTING'.format(device['name'])
    clear_operation_icons()

    thread = threading.Thread(
        target=update_polling_setting_worker,
        args=(device, requested_state)
    )
    thread.daemon = True
    thread.start()


def update_polling_setting_worker(device, requested_state):
    """Write fallback settings and use Telegram to tell the ESP to check now."""
    write_ok = False
    telegram_ok = False
    detail = None
    try:
        write_command_document(device, {
            'fallback_enabled': bool(requested_state),
            'fallback_interval': FALLBACK_INTERVAL,
        })
        write_ok = True
    except Exception as error:
        detail = str(error)

    # A trigger is needed even when disabling polling, otherwise an ESP that
    # stops polling could never learn that the setting was changed to OFF.
    if write_ok:
        try:
            telegram_ok, telegram_detail = telegram_pythonista.send_message(
                device['esp_id'], 'refresh'
            )
            if not telegram_ok:
                detail = telegram_detail
        except Exception as error:
            telegram_ok = False
            detail = str(error)

    ui.delay(
        lambda: polling_setting_result(
            device['esp_id'], requested_state, write_ok, telegram_ok, detail
        ),
        0
    )


def polling_setting_result(esp_id, requested_state, write_ok, telegram_ok, detail):
    """Update the polling switch and icons after the cloud/Telegram operations."""
    if esp_id != selected_device()['esp_id']:
        return
    if write_ok:
        set_cloud_switch_visual(requested_state)
        set_status_icon(btn_cloud_icon, True)
        set_status_icon(btn_telegram_icon, telegram_ok)
        label_screen.text = '{}: POLLING {}'.format(
            selected_device()['name'], 'ON' if requested_state else 'OFF'
        )
        ui.delay(refresh_data, COMMAND_REFRESH_DELAY)
    else:
        label_screen.text = '{}: POLLING SAVE FAILED'.format(selected_device()['name'])
        print('Polling setting write failed:', repr(detail))
        # Restore the previous switch appearance; the cloud write did not succeed.
        set_cloud_switch_visual(not requested_state)



def buttonx_action(sender):
    """Stop scheduled work and close the Pythonista interface."""
    global running, animation_id, selector_transition
    running = False
    animation_id += 1  # Invalidates any scheduled needle-animation step.
    selector_transition = False
    UIApplication.sharedApplication().performSelector_('terminateWithSuccess')


btn2 = ui.Button(title='')
btn2.frame = (350, 425, 40, 40)
btn2.font = ('<MarkerFelt-Thin>', 40)
btn2.title_color = '#cfcfcf'
btn2.tint_color = '#cfcfcf'
btn2.background_color = 'clear'
btn2.background_image = ui.Image.named('push_button_exit.JPG')
btn2.border_width = 0
btn2.corner_radius = 20
btn2.action = buttonx_action
root.add_subview(btn2)


def button_refresh_action(sender):
    """Read the latest cloud data for the currently selected ESP."""
    refresh_data()


button_refresh = ui.Button()
button_refresh.frame = (40, 425, 40, 40)
button_refresh.background_image = ui.Image.named('push_button_start.JPG')
button_refresh.corner_radius = 20
button_refresh.border_width = 2
button_refresh.border_color = '#9b9ba4'
button_refresh.action = button_refresh_action
root.add_subview(button_refresh)


# ============================================================
# LOWER LEATHER STATUS PANEL
# ============================================================

status_panel = ui.View()
status_panel.frame = (15, 650, 400, 60)
status_panel.corner_radius = 12
status_panel.border_width = 2
status_panel.border_color = '#9b9ba4'
status_panel.clips_to_bounds = True

status_panel_image = ui.ImageView()
status_panel_image.frame = status_panel.bounds
status_panel_image.image = ui.Image.named('black_leather.jpg')
status_panel_image.content_mode = ui.CONTENT_SCALE_ASPECT_FILL
status_panel.add_subview(status_panel_image)
root.add_subview(status_panel)


def make_status_icon(frame, active_image):
    """Create a status icon that is black until its operation succeeds."""
    button = ui.Button(title='')
    button.frame = frame
    button.background_color = 'clear'
    button.background_image = ui.Image.named('push_button_black.jpg')
    button.border_width = 0
    button.corner_radius = 20
    button.enabled = False
    button._active_image_name = active_image
    root.add_subview(button)
    return button


btn_telegram_icon = make_status_icon((150, 660, 40, 40), 'telegram_icon.JPEG')
btn_cloud_icon = make_status_icon((200, 660, 40, 40), 'cloud_icon.JPEG')
btn_cloud2_icon = make_status_icon((250, 660, 40, 40), 'cloud_icon.JPEG')


def set_status_icon(button, active):
    """Show the service icon on success, otherwise show the black button."""
    image_name = button._active_image_name if active else 'push_button_black.jpg'
    button.background_image = ui.Image.named(image_name)


def clear_operation_icons():
    set_status_icon(btn_telegram_icon, False)
    set_status_icon(btn_cloud_icon, False)
    set_status_icon(btn_cloud2_icon, False)


# Fallback-polling switch artwork and transparent tap target.
button9 = ui.Button()
button9.frame = (340, 660, 40, 40)
button9.background_image = ui.Image.named('push_button_black.jpg')
button9.corner_radius = 20
button9.border_width = 1
button9.border_color = '#9b9ba4'
button9.enabled = False
root.add_subview(button9)

cloud_timing_switch = ui.Button()
cloud_timing_switch.frame = button9.frame
cloud_timing_switch.value = False
cloud_timing_switch.background_color = 'clear'
cloud_timing_switch.border_width = 0
cloud_timing_switch.tint_color = 'clear'
cloud_timing_switch.corner_radius = 20
root.add_subview(cloud_timing_switch)


def set_cloud_switch_visual(is_on):
    """Show the ON/OFF switch image and synchronize its logical value."""
    cloud_timing_switch.value = bool(is_on)
    button9.background_image = ui.Image.named(
        'black_button_on.JPEG' if is_on else 'push_button_black.jpg'
    )


# Attach the action only after the switch button has been created.
cloud_timing_switch.action = cloud_timing_switch_pressed


# ============================================================
# 8. GAUGE ANIMATION HELPERS
# ============================================================


def animate_needle_to(target_value, duration, on_complete=None):
    """Animate from the current gauge value to a target without blocking the UI.

    ui.delay schedules each small step. animation_id lets a newer animation
    cancel the remaining steps from an older animation.
    """
    global animation_id
    animation_id += 1
    this_animation = animation_id

    try:
        start_value = float(g.value)
        target_value = max(0.0, min(100.0, float(target_value)))
    except (TypeError, ValueError):
        start_value = 0.0
        target_value = 0.0

    steps = max(1, int(ANIMATION_STEPS))
    interval = max(0.001, float(duration) / steps)
    step_number = 0

    def animate_step():
        nonlocal step_number

        # Stop if another animation replaced this one or the interface is closing.
        if this_animation != animation_id or not running:
            return

        step_number += 1
        fraction = min(1.0, step_number / steps)
        value = start_value + (target_value - start_value) * fraction
        g.set_value(value)

        if step_number < steps:
            ui.delay(animate_step, interval)
        elif on_complete is not None:
            on_complete()

    # If already at the target, complete without running unnecessary steps.
    if abs(start_value - target_value) < 0.0001:
        g.set_value(target_value)
        if on_complete is not None:
            ui.delay(on_complete, 0)
    else:
        ui.delay(animate_step, interval)


def set_gauge_immediately(new_value):
    """Cancel pending animation steps and show a new cloud value immediately."""
    global animation_id
    animation_id += 1
    g.set_value(new_value)


def read_after_selector_change():
    """Read cloud data only after the selector's downward animation finishes."""
    if running:
        refresh_data(selector_change_read=True)


def finish_selector_transition():
    """Mark the selector transition as finished so normal refreshes can resume."""
    global selector_transition
    selector_transition = False


# ============================================================
# 9. CLOUD DATA HELPERS
# ============================================================


def numeric_gauge_value(data):
    """Find a sensor field and convert raw ESP32 ADC readings to 0–100."""
    value = None
    for key in GAUGE_VALUE_KEYS:
        if key in data and data.get(key) is not None:
            value = data.get(key)
            break

    if isinstance(value, bool):
        return 100 if value else 0

    try:
        value = float(value)
    except (TypeError, ValueError):
        return None

    # ADC readings above 100 are treated as raw 12-bit values (0–4095).
    if 100 < value <= 4095:
        value = value * 100.0 / 4095.0

    return max(0, min(100, value))


# Mark the device OFFLINE when its last cloud timestamp is older than 6 minutes.
OFFLINE_AFTER_SECONDS = 6 * 60


def parse_device_timestamp(value):
    """Parse common ISO and date/time formats used by the ESP status JSON."""
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    try:
        # Support ISO timestamps ending in Z as well as explicit UTC offsets.
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        return datetime.datetime.fromisoformat(text)
    except (ValueError, TypeError):
        pass

    for fmt in (
        '%Y-%m-%d %H:%M:%S',
        '%Y/%m/%d %H:%M:%S',
        '%d/%m/%Y %H:%M:%S',
        '%d-%m-%Y %H:%M:%S',
    ):
        try:
            return datetime.datetime.strptime(text, fmt)
        except ValueError:
            continue

    return None


def timestamp_from_data(data):
    """Return the device timestamp formatted as DD-MM-YYYY HH:MM:SS."""
    for key in ('updated', 'last_seen', 'timestamp', 'last_update'):
        value = data.get(key)
        if value not in (None, ''):
            parsed = parse_device_timestamp(value)
            if parsed is not None:
                return parsed.strftime('%d-%m-%Y %H:%M:%S')
            return str(value).replace('T', ' ', 1)
    return 'NO TIMESTAMP'


def device_online_status(data):
    """Return ONLINE/OFFLINE/UNKNOWN using the age of the latest timestamp."""
    timestamp_text = None
    for key in ('updated', 'last_seen', 'timestamp', 'last_update'):
        if data.get(key) not in (None, ''):
            timestamp_text = data.get(key)
            break

    timestamp = parse_device_timestamp(timestamp_text)
    if timestamp is None:
        return 'UNKNOWN'

    try:
        # ESP timestamps without an offset are local time, matching the ESP clock.
        if timestamp.tzinfo is None:
            now = datetime.datetime.now()
        else:
            now = datetime.datetime.now(timestamp.tzinfo)
        age_seconds = (now - timestamp).total_seconds()
    except Exception as error:
        print('Device timestamp calculation failed:', repr(error))
        return 'UNKNOWN'

    # Avoid showing ONLINE for a timestamp significantly in the future.
    if age_seconds < -60:
        return 'UNKNOWN'
    if age_seconds > OFFLINE_AFTER_SECONDS:
        return 'OFFLINE'
    return 'ONLINE'


# ============================================================
# 10. CLOUD READ — ONLY THE SELECTED ESP
# ============================================================


def refresh_data(selector_change_read=False):
    """Start a background cloud read for the selected ESP, unless one is active."""
    global loading, request_id

    if not running or loading:
        return

    # Normal refreshes must not interrupt the selector's down/read/up sequence.
    if selector_transition and not selector_change_read:
        return

    loading = True
    request_id += 1
    current_request = request_id
    device = selected_device()
    label_screen.text = '{}: READING CLOUD'.format(device['name'])

    # Network access runs in a worker thread so the UI remains responsive.
    thread = threading.Thread(
        target=cloud_reader,
        args=(device, current_request)
    )
    thread.daemon = True
    thread.start()


def cloud_reader(device, current_request):
    """Read status and command JSON in the background, then update the UI."""
    data = None
    command_data = None
    error_text = None

    try:
        data = cloud_storage.read_json(device['filename'])
        if not isinstance(data, dict):
            raise RuntimeError('Status JSON did not contain an object')
    except Exception as error:
        error_text = str(error)
        print('Cloud read error for {}: {}'.format(device['esp_id'], repr(error)))

    try:
        command_data = cloud_storage.read_json(device['command_filename'])
        if not isinstance(command_data, dict):
            command_data = None
    except Exception as error:
        print('Command JSON read error for {}: {}'.format(device['esp_id'], repr(error)))
        command_data = None

    try:
        ui.delay(
            lambda: display_cloud_result(
                device['esp_id'], current_request, data, command_data, error_text
            ),
            0
        )
    except Exception as error:
        print('Could not schedule cloud result:', repr(error))


def display_cloud_result(esp_id, current_request, data, command_data, error_text):
    """Handle the cloud result, rejecting responses for an old selection."""
    global loading

    # A slow response from a previously selected ESP must not change the display.
    if current_request != request_id or esp_id != selected_device()['esp_id']:
        if current_request == request_id:
            loading = False
        return

    loading = False

    if error_text is not None:
        label_screen.text = '{}: CLOUD ERROR'.format(selected_device()['name'])
        if selector_transition:
            finish_selector_transition()
        return

    if not isinstance(data, dict):
        label_screen.text = '{}: NO CLOUD DATA'.format(selected_device()['name'])
        if selector_transition:
            finish_selector_transition()
        return

    device = selected_device()
    status_text = device_online_status(data)
    label_screen.text = '{} {} : {}'.format(
        device['esp_id'], status_text.lower(), timestamp_from_data(data)
    )

    value = numeric_gauge_value(data)

    if selector_transition:
        # This is the read requested after the needle reached zero.
        # Animate up once, then release the selector-transition lock.
        if value is None:
                value = 0
        animate_needle_to(
            value,
            duration=SELECTOR_UP_SECONDS,
            on_complete=finish_selector_transition
        )
    elif value is not None:
        # Normal/manual/command refresh: update directly, with no animation.
        set_gauge_immediately(value)
    else:
        set_gauge_immediately(0)

    # Show the polling switch according to the selected ESP's command file.
    if isinstance(command_data, dict):
        set_cloud_switch_visual(bool(command_data.get('fallback_enabled', False)))

        # Cloud 2 is active only when each requested output matches the ESP report.
        matches = True
        for gpio in ('gpio25', 'gpio26', 'gpio27'):
            requested = normalize_gpio_state(command_data.get(gpio + '_request'))
            actual = normalize_gpio_state(data.get(gpio), default='UNKNOWN')
            if actual != requested:
                matches = False
                break
        set_status_icon(btn_cloud2_icon, matches)
    else:
        set_status_icon(btn_cloud2_icon, False)

    # Synchronize the switch picture with GPIO25 when that field is present.
    output_value = data.get('gpio25')
    if output_value is True or output_value == 1 or str(output_value).upper() == 'ON':
        set_switch_visual(True)
    elif output_value is False or output_value == 0 or str(output_value).upper() == 'OFF':
        set_switch_visual(False)


# ============================================================
# 11. TELEGRAM COMMANDS
# ============================================================


def send_command(command, requested_state=None):
    """Save the requested GPIO state, then send the Telegram trigger."""
    device = selected_device()
    label_screen.text = '{}: SAVING COMMAND'.format(device['name'])
    clear_operation_icons()

    thread = threading.Thread(
        target=send_command_worker,
        args=(device, command, requested_state)
    )
    thread.daemon = True
    thread.start()


def send_command_worker(device, command, requested_state):
    """Write the command JSON first; send Telegram only if that write succeeds."""
    cloud_ok = False
    telegram_ok = False
    detail = None

    try:
        if command.strip().upper() in ('GPIO25 ON', 'GPIO25 OFF'):
            state = command.strip().upper().split()[-1]
            write_command_document(device, {'gpio25_request': state})
        else:
            raise ValueError('Unsupported controller command: {}'.format(command))
        cloud_ok = True
    except Exception as error:
        detail = str(error)

    if cloud_ok:
        try:
            telegram_ok, telegram_detail = telegram_pythonista.send_message(
                device['esp_id'], 'refresh'
            )
            if not telegram_ok:
                detail = telegram_detail
        except Exception as error:
            telegram_ok = False
            detail = str(error)

    ui.delay(
        lambda: command_result(
            device['esp_id'], command, cloud_ok, telegram_ok, detail, requested_state
        ),
        0
    )


def command_result(esp_id, command, cloud_ok, telegram_ok, detail, requested_state):
    """Display the cloud-save and Telegram-send results for the current command."""
    # Ignore a result if the user has since selected another ESP.
    if esp_id != selected_device()['esp_id']:
        return

    set_status_icon(btn_cloud_icon, cloud_ok)
    set_status_icon(btn_telegram_icon, telegram_ok)

    if cloud_ok and telegram_ok:
        label_screen.text = '{}: COMMAND SENT'.format(selected_device()['name'])
    elif cloud_ok:
        label_screen.text = '{}: SAVED; WAITING FOR POLL'.format(selected_device()['name'])
        print('Telegram trigger failed; fallback polling can recover:', repr(detail))
    else:
        label_screen.text = '{}: COMMAND SAVE FAILED'.format(selected_device()['name'])
        print('Command JSON write failed:', repr(detail))
        if requested_state is not None:
            set_switch_visual(not requested_state)

    # Refresh status whether Telegram worked or not; fallback may still apply it.
    if cloud_ok:
        ui.delay(refresh_data, COMMAND_REFRESH_DELAY)


# ============================================================
# 12. AUTOMATIC REFRESH
# ============================================================


def auto_refresh():
    """Refresh periodically; the selector-transition lock prevents interference."""
    if not running:
        return
    refresh_data()
    ui.delay(auto_refresh, AUTO_REFRESH_SECONDS)


# ============================================================
# 13. START THE INTERFACE
# ============================================================

update_selected_device_display()
set_switch_visual(False)
set_cloud_switch_visual(False)
clear_operation_icons()
root.present('sheet')

# Animate the needle from zero to the first cloud reading.
selector_transition = True
refresh_data(selector_change_read=True)
ui.delay(auto_refresh, AUTO_REFRESH_SECONDS)
