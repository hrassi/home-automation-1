# ==============================================================
# HOME AUTOMATION DASHBOARD
# Pythonista on iPhone
# edited on mac
# Universal TECHNICIAN dashboard for ESP1, ESP2, ESP3 and ESP4.
# Reads status JSON and writes command JSON in Google Cloud Storage.
# Output controls write the command document, then send Telegram REFRESH.
# PING and other supported free-text Telegram commands remain available.
#
# ESP selector stays at the bottom.
# Dashboard refreshes automatically every 20 seconds.
#
# FILE MAP
# 1. Settings and field labels
# 2. Data helper functions
# 3. HomeDashboard class:
#    - Interface creation and layout
#    - User actions and cloud refresh logic
#    - Choosing which data to display
#    - Visual card creation and sizing
# 4. Start the dashboard
#
# IMPORTANT: cloud_storage.py is separate and is not changed here.
# Keep its time.sleep(0.05) stability delays as they are.
# ============================================================

import ui
import time
import threading
import datetime
import cloud_storage
import telegram_pythonista


# ============================================================
# SECTION 1 — SETTINGS AND DISPLAY LABELS
# These values are shared by the whole dashboard.
# Change colors, refresh interval, supported ESPs, or field names here.
# ============================================================

ESP_IDS = ['esp1', 'esp2', 'esp3', 'esp4']

REFRESH_SECONDS = 20

# Wait after sending a command before reading the ESP's reported status.
COMMAND_REFRESH_DELAY = 4

# Fallback polling settings written to every ESP command document.
FALLBACK_INTERVAL = 30

# Each ESP may use a different analog input GPIO.
ESP1_ANALOG_GPIO = 34
ESP2_ANALOG_GPIO = 34
ESP3_ANALOG_GPIO = 34
ESP4_ANALOG_GPIO = 33

ANALOG_GPIO_BY_ESP = {
    'esp1': ESP1_ANALOG_GPIO,
    'esp2': ESP2_ANALOG_GPIO,
    'esp3': ESP3_ANALOG_GPIO,
    'esp4': ESP4_ANALOG_GPIO,
}

# Prevent simultaneous read-modify-write operations on command JSON files.
command_file_lock = threading.Lock()

BACKGROUND_COLOR = '#151923'
HEADER_COLOR = '#202735'
CARD_COLOR = '#252D3B'
FOOTER_COLOR = '#202735'

TEXT_COLOR = '#FFFFFF'
SECONDARY_COLOR = '#AAB5C5'

GREEN_COLOR = '#42D392'
RED_COLOR = '#FF626D'
BLUE_COLOR = '#66A8FF'
ORANGE_COLOR = '#FFBD59'
GRAY_COLOR = '#AAB5C5'


# ============================================================
# FIELD LABELS
# ============================================================

FIELD_LABELS = {
    'gpio25': 'GPIO 25 OUTPUT',
    'gpio26': 'GPIO 26 OUTPUT',
    'gpio27': 'GPIO 27 OUTPUT',

    'input35': 'DIGITAL INPUT 35',
    'input13': 'DIGITAL INPUT 13',
    'input14': 'DIGITAL INPUT 14',

    'analog33': 'ANALOG SENSOR - GPIO 33',
    'analog34': 'ANALOG SENSOR - GPIO 34',

    'pot': 'POTENTIOMETER',
    'temperature': 'TEMPERATURE',
    'temp': 'TEMPERATURE',

    'tank1': 'TANK 1',
    'tank2': 'TANK 2',
    'tank3': 'TANK 3',
    'tank4': 'TANK 4',
    'tank5': 'TANK 5',

    'liters': 'WATER LEVEL',
    'level': 'WATER LEVEL',

    'online': 'DEVICE STATUS',
    'updated': 'LAST CLOUD UPDATE',
    'last_seen': 'LAST SEEN',
}


# ============================================================
# SECTION 2 — DATA HELPERS (FUNCTIONAL)
# These functions convert cloud field names and values into readable text.
# They do not create or position any interface elements.
# ============================================================

def readable_name(key):
    """Convert a JSON field name into a readable label."""

    if key in FIELD_LABELS:
        return FIELD_LABELS[key]

    return key.replace('_', ' ').upper()


def readable_value(value):
    """Convert values into readable text."""

    if value is None:
        return 'N/A'

    if isinstance(value, bool):
        return 'ON' if value else 'OFF'

    if isinstance(value, float):
        return '{:.2f}'.format(value)

    if isinstance(value, dict):
        return str(value)

    if isinstance(value, list):
        return ', '.join(str(item) for item in value)

    return str(value)


# ============================================================
# DEVICE ONLINE/OFFLINE STATUS
# A device is ONLINE only if its last reported update is no older
# than six minutes. This does not rely solely on the JSON online flag.
# ============================================================

OFFLINE_AFTER_SECONDS = 6 * 60


def parse_device_timestamp(value):
    """Parse ISO and common local timestamp formats from ESP status JSON."""
    if not isinstance(value, str) or not value.strip():
        return None

    text = value.strip()
    try:
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


def device_connection_status(data):
    """Return ONLINE, OFFLINE, or UNKNOWN based on last update age."""
    if not isinstance(data, dict):
        return 'UNKNOWN'

    timestamp_text = data.get('updated')
    if timestamp_text is None:
        timestamp_text = data.get('last_seen')

    timestamp = parse_device_timestamp(timestamp_text)
    if timestamp is None:
        return 'UNKNOWN'

    try:
        if timestamp.tzinfo is None:
            now = datetime.datetime.now()
        else:
            now = datetime.datetime.now(timestamp.tzinfo)
        age_seconds = (now - timestamp).total_seconds()
    except Exception as error:
        print('[Status] Timestamp calculation failed:', repr(error))
        return 'UNKNOWN'

    # Treat a timestamp more than one minute in the future as invalid.
    if age_seconds < -60:
        return 'UNKNOWN'

    if age_seconds > OFFLINE_AFTER_SECONDS:
        return 'OFFLINE'

    return 'ONLINE'


def is_output_field(key):
    """Return True for GPIO output fields."""

    return key.startswith('gpio')


def is_input_field(key):
    """Return True for digital input fields."""

    return key.startswith('input')


def is_analog_field(key):
    """Return True for analog sensor fields."""

    return key.startswith('analog')


# ============================================================
# CLOUD COMMAND HELPERS — COMMON PROTOCOL FOR ALL FOUR ESPs
# ============================================================

def normalize_gpio_state(value, default='OFF'):
    """Normalize old numeric and new text GPIO states to ON/OFF."""
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


def command_filename_for(esp_id):
    """Return the selected ESP's cloud command object filename."""
    return '{}_command.json'.format(esp_id)


def read_command_document(esp_id):
    """Read the command JSON, seeding it from status if it does not exist."""
    filename = command_filename_for(esp_id)

    try:
        document = cloud_storage.read_json(filename)
        if isinstance(document, dict):
            return document
    except Exception as error:
        print('Command JSON read error for {}: {}'.format(esp_id, repr(error)))

    # If no command file exists yet, initialize requested states from status.
    try:
        status = cloud_storage.read_json('{}.json'.format(esp_id))
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


def write_command_document(esp_id, changes):
    """Preserve the other requested states and write the selected command JSON."""
    with command_file_lock:
        document = read_command_document(esp_id)
        if not isinstance(document, dict):
            document = {}

        # Keep all three output requests in every command document.
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

        try:
            document['fallback_interval'] = max(
                5, int(document.get('fallback_interval', FALLBACK_INTERVAL))
            )
        except (TypeError, ValueError):
            document['fallback_interval'] = FALLBACK_INTERVAL

        result = cloud_storage.write_json(
            command_filename_for(esp_id), document
        )
        if result is False:
            raise RuntimeError('Cloud storage reported that the command JSON write failed')

        return document


# ============================================================
# SECTION 3 — DASHBOARD
#
# The class below contains both behavior and interface methods, kept in
# this single file as requested. Its methods are grouped into clear areas:
#
# A. INTERFACE CREATION AND LAYOUT — creates/positions visual elements.
# B. USER ACTIONS AND CLOUD LOGIC — responds to taps and reads cloud data.
# C. CARD CONTENT — decides which data to show, then creates its cards.
#
# The existing behavior and layout are intentionally preserved.
# ============================================================

class HomeDashboard(ui.View):

    # --------------------------------------------------------
    # A1 — CREATE THE INTERFACE
    # Build the header, scrolling content area, and bottom ESP selector.
    # The buttons are connected to their functional callback methods below.
    # --------------------------------------------------------
    def __init__(self):

        ui.View.__init__(self)

        self.name = 'Home Automation'
        self.background_color = BACKGROUND_COLOR

        self.esp_id = 'esp1'
        self.device_data = None

        self.loading = False
        self.running = True

        self.request_id = 0

        self.cards = []
        self._special_command_text = ''

        # ----------------------------------------------------
        # HEADER
        # ----------------------------------------------------

        self.header = ui.View()
        self.header.background_color = HEADER_COLOR
        self.add_subview(self.header)

        self.title_label = ui.Label()
        self.title_label.text = 'TECHNICIAN DASHBOARD'
        self.title_label.text_color = TEXT_COLOR
        self.title_label.font = ('<System-Bold>', 19)
        self.title_label.alignment = ui.ALIGN_CENTER
        self.header.add_subview(self.title_label)

        self.device_label = ui.Label()
        self.device_label.text = 'ESP1'
        self.device_label.text_color = BLUE_COLOR
        self.device_label.font = ('<System-Bold>', 17)
        self.device_label.alignment = ui.ALIGN_CENTER
        self.header.add_subview(self.device_label)

        self.status_label = ui.Label()
        self.status_label.text = 'Loading cloud data...'
        self.status_label.text_color = SECONDARY_COLOR
        self.status_label.font = ('<System>', 12)
        self.status_label.alignment = ui.ALIGN_CENTER
        self.header.add_subview(self.status_label)

        self.refresh_button = ui.Button()
        self.refresh_button.title = '↻'
        self.refresh_button.font = ('<System-Bold>', 27)
        self.refresh_button.tint_color = BLUE_COLOR
        self.refresh_button.action = self.refresh_button_pressed
        self.header.add_subview(self.refresh_button)

        # ----------------------------------------------------
        # SCROLL AREA
        # ----------------------------------------------------

        self.scroll = ui.ScrollView()
        self.scroll.background_color = BACKGROUND_COLOR
        self.scroll.always_bounce_vertical = True
        self.scroll.shows_vertical_scroll_indicator = True
        self.add_subview(self.scroll)

        self.content = ui.View()
        self.content.background_color = BACKGROUND_COLOR

        # Initial frame; corrected to full width in layout().
        self.content.frame = (0, 0, self.width, 1)

        self.scroll.add_subview(self.content)

        # ----------------------------------------------------
        # BOTTOM SELECTOR
        # ----------------------------------------------------

        self.footer = ui.View()
        self.footer.background_color = FOOTER_COLOR
        self.add_subview(self.footer)

        self.selector_label = ui.Label()
        self.selector_label.text = 'SELECT DEVICE'
        self.selector_label.text_color = SECONDARY_COLOR
        self.selector_label.font = ('<System-Bold>', 11)
        self.selector_label.alignment = ui.ALIGN_CENTER
        self.footer.add_subview(self.selector_label)

        self.esp_buttons = []

        for esp in ESP_IDS:

            button = ui.Button()
            button.title = esp.upper()
            button.name = esp
            button.font = ('<System-Bold>', 14)
            button.corner_radius = 9
            button.action = self.esp_button_pressed

            self.footer.add_subview(button)
            self.esp_buttons.append(button)

        self.update_selector()

        self.build_cards()

        self.refresh_data()

        ui.delay(self.auto_refresh, REFRESH_SECONDS)

    # ========================================================
    # A2 — INTERFACE LAYOUT
    # Pythonista calls layout() when the view's size changes.
    # This method positions the header, footer, scrolling area, and cards.
    # ========================================================

    def layout(self):

        width = self.width
        height = self.height

        if width <= 0 or height <= 0:
            return

        header_height = 112
        footer_height = 88

        self.header.frame = (
            0,
            0,
            width,
            header_height
        )

        self.title_label.frame = (
            45,
            5,
            width - 90,
            26
        )

        self.device_label.frame = (
            45,
            31,
            width - 90,
            24
        )

        self.status_label.frame = (
            12,
            58,
            width - 24,
            22
        )

        self.refresh_button.frame = (
            width - 48,
            7,
            42,
            42
        )

        # ----------------------------------------------------
        # FOOTER
        # ----------------------------------------------------

        self.footer.frame = (
            0,
            height - footer_height,
            width,
            footer_height
        )

        self.selector_label.frame = (
            8,
            5,
            width - 16,
            19
        )

        button_count = len(self.esp_buttons)
        side_margin = 8
        gap = 6

        available_width = (
            width
            - (2 * side_margin)
            - (gap * (button_count - 1))
        )

        button_width = available_width / button_count

        for index, button in enumerate(self.esp_buttons):

            button.frame = (
                side_margin + index * (button_width + gap),
                31,
                button_width,
                43
            )

        # ----------------------------------------------------
        # SCROLL AREA
        # ----------------------------------------------------

        scroll_y = header_height

        scroll_height = (
            height
            - header_height
            - footer_height
        )

        self.scroll.frame = (
            0,
            scroll_y,
            width,
            max(1, scroll_height)
        )

        # IMPORTANT:
        # The content view must have the full screen width.
        self.content.frame = (
            0,
            0,
            width,
            max(1, self.content.height)
        )

        self.scroll.content_size = (
            width,
            self.content.height
        )

        self.layout_cards()

    # ========================================================
    # B1 — DEVICE SELECTOR BEHAVIOR
    # update_selector() only changes button appearance.
    # esp_button_pressed() handles the user's selection and starts a new read.
    # ========================================================

    def update_selector(self):

        for button in self.esp_buttons:

            if button.name == self.esp_id:

                button.background_color = BLUE_COLOR
                button.tint_color = '#10151E'

            else:

                button.background_color = CARD_COLOR
                button.tint_color = TEXT_COLOR

    def esp_button_pressed(self, sender):
        # A bottom selector button was tapped. Ignore unknown button names.
        selected_esp = sender.name

        if selected_esp not in ESP_IDS:
            return

        self.esp_id = selected_esp

        self.device_data = None

        self.device_label.text = selected_esp.upper()
        self.status_label.text = 'Loading cloud data...'

        self.update_selector()

        self.build_cards()

        self.refresh_data()

    # ========================================================
    # B2 — MANUAL REFRESH BUTTON
    # The button does not read the cloud itself; it starts the shared
    # refresh process so manual and automatic refreshes behave consistently.
    # ========================================================

    def refresh_button_pressed(self, sender):

        self.refresh_data()

    # ========================================================
    # B3 — CLOUD DATA REQUEST (FUNCTIONAL)
    # refresh_data() prevents overlapping requests, remembers which ESP
    # and request are current, then starts a background thread.
    # The thread keeps network waiting from freezing the user interface.
    # ========================================================

    def refresh_data(self):

        if self.loading:
            return

        self.loading = True

        self.request_id += 1

        current_request = self.request_id
        selected_esp = self.esp_id

        filename = selected_esp + '.json'

        self.status_label.text = 'Reading cloud data...'

        thread = threading.Thread(
            target=self.cloud_reader,
            args=(
                selected_esp,
                filename,
                current_request
            )
        )

        thread.daemon = True
        thread.start()

    def cloud_reader(self, esp_id, filename, request_id):
        # Runs in a background thread: fetch and decode the selected JSON file.
        # It does not directly change labels or other UI elements.
        data = None
        error_text = None

        try:
            data = cloud_storage.read_json(filename)

        except Exception as error:
            error_text = str(error)
            print("Cloud read error:", repr(error))

        # Safely schedule the UI update.
        try:
            ui.delay(
                lambda: self.display_cloud_result(
                    esp_id,
                    request_id,
                    data,
                    error_text
                ),
                0
            )

        except Exception as error:
            print("Cloud UI scheduling error:", repr(error))

            # Release the refresh lock so a later refresh can run.
            try:
                ui.delay(
                    lambda: setattr(self, 'loading', False),
                    0
                )
            except Exception:
                pass




    # Apply the completed request on Pythonista's UI scheduling mechanism.
    # Old results are ignored if the user has selected another ESP or a newer
    # request has replaced this one.
    def display_cloud_result(
        self,
        esp_id,
        request_id,
        data,
        error_text
    ):

        if request_id != self.request_id:
            return

        if esp_id != self.esp_id:
            return

        self.loading = False

        # ----------------------------------------------------
        # CLOUD REQUEST ERROR
        # Keep the last successful dashboard values.
        # ----------------------------------------------------

        if error_text is not None:

            print(
                "Cloud read error for",
                esp_id,
                ":",
                error_text
            )

            if self.device_data is not None:
                self.status_label.text = (
                    'Cloud error - showing last data'
                )
            else:
                self.status_label.text = (
                    'Cloud read failed - retrying'
                )

            # Do not clear device_data.
            # Do not rebuild the cards.
            # The next automatic refresh will try again.
            return

        # ----------------------------------------------------
        # NO VALID DATA
        # ----------------------------------------------------

        if not isinstance(data, dict):

            if self.device_data is not None:
                self.status_label.text = (
                    'No cloud response - showing last data'
                )
            else:
                self.status_label.text = 'No cloud data found'

            return

        # ----------------------------------------------------
        # SUCCESSFUL CLOUD READ
        # ----------------------------------------------------

        self.device_data = data

        if data.get('online') is True:
            self.status_label.text = 'Cloud data loaded'

        elif data.get('online') is False:
            self.status_label.text = 'Device reports OFFLINE'

        else:
            self.status_label.text = 'Cloud data loaded'

        self.build_cards()




    # ========================================================
    # B4 — AUTOMATIC REFRESH (FUNCTIONAL)
    # Schedule another refresh every REFRESH_SECONDS.
    # If a request is still running, skip this cycle rather than overlap it.
    # ========================================================

    def auto_refresh(self):

        if not self.running:
            return

        if not self.loading:
            self.refresh_data()

        ui.delay(
            self.auto_refresh,
            REFRESH_SECONDS
        )

    # ========================================================
    # C1 — CHOOSE AND BUILD DISPLAYED DATA CARDS
    # This method is a bridge between logic and design:
    # it examines device_data, chooses the fields/order/status to show,
    # then calls the visual card-building methods below.
    # ========================================================

    def build_cards(self, error_message=None):

        # Preserve text if a cloud refresh rebuilds the controls.
        old_command_field = getattr(self, 'command_field', None)
        if old_command_field is not None:
            self._special_command_text = old_command_field.text

        # Remove existing cards and section labels.
        for subview in list(self.content.subviews):
            self.content.remove_subview(subview)

        self.cards = []

        y = 8

        # ----------------------------------------------------
        # ERROR MESSAGE
        # ----------------------------------------------------

        if error_message is not None:

            self.add_value_card(
                'CLOUD CONNECTION',
                error_message,
                y,
                kind='error'
            )

            y += 58

            y = self.add_special_command(y)
            y = self.add_output_controls(y)

            self.content.height = y + 8

            self.layout_cards()

            return

        # ----------------------------------------------------
        # NO DATA YET
        # ----------------------------------------------------

        if not isinstance(self.device_data, dict):

            self.add_value_card(
                'DEVICE',
                self.esp_id.upper(),
                y,
                kind='normal'
            )

            y += 58

            self.add_value_card(
                'CLOUD DATA',
                'Waiting for data...',
                y,
                kind='normal'
            )

            y += 58

            y = self.add_special_command(y)
            y = self.add_output_controls(y)

            self.content.height = y + 8

            self.layout_cards()

            return

        # A successful cloud read is stored in self.device_data.
        data = self.device_data

        # ----------------------------------------------------
        # 1. SPECIAL COMMANDS — keep this at the top so it is
        #    visible before opening the iPhone keyboard.
        # ----------------------------------------------------

        y = self.add_special_command(y)

        # ----------------------------------------------------
        # 2. DIGITAL INPUTS in the requested order: 14, 35, 13.
        # Always show these three GPIOs, even when a field is missing.
        # ----------------------------------------------------

        input_order = ('input14', 'input35', 'input13')
        shown_inputs = set()

        # Technician mode always shows all three standard input GPIOs.
        # A reported 0 is valid; a missing field is displayed as N/A.
        for key in input_order:
            value = data.get(key)
            self.add_value_card(
                readable_name(key),
                readable_value(value),
                y,
                kind='input',
                original_value=value
            )
            y += 58
            shown_inputs.add(key)

        # Preserve any other digital input fields, after the three
        # specifically requested above.
        for key in data:
            if is_input_field(key) and key not in shown_inputs:
                self.add_value_card(
                    readable_name(key),
                    readable_value(data.get(key)),
                    y,
                    kind='input',
                    original_value=data.get(key)
                )
                y += 58

        # ----------------------------------------------------
        # 3. ANALOG INPUT / OTHER SENSOR VALUES.
        # Keep all input/sensor cards together before the outputs.
        # Display only the analog GPIO configured for the selected ESP.
        # ----------------------------------------------------

        sensor_keys = []
        selected_analog_key = 'analog{}'.format(
            ANALOG_GPIO_BY_ESP.get(self.esp_id, 34)
        )

        # Include the configured analog input only. Always reserve its card,
        # even if the selected ESP has not uploaded that field yet.
        ordered_sensors = [selected_analog_key]

        for key in data:
            if is_analog_field(key):
                # Do not display the other analog GPIO on this ESP.
                continue
            if key in (
                'pot', 'temperature', 'temp',
                'tank1', 'tank2', 'tank3', 'tank4', 'tank5',
                'liters', 'level'
            ):
                sensor_keys.append(key)

        ordered_sensors.extend(
            key for key in sensor_keys if key not in ordered_sensors
        )

        for key in ordered_sensors:
            value = data.get(key)
            self.add_value_card(
                readable_name(key),
                readable_value(value),
                y,
                kind='sensor',
                original_value=value
            )
            y += 58

        # ----------------------------------------------------
        # 4. GPIO OUTPUTS 25, 26, 27.
        # ----------------------------------------------------

        y = self.add_output_controls(y)

        # ----------------------------------------------------
        # DEVICE STATUS
        # ----------------------------------------------------

        status_text = device_connection_status(data)

        if status_text == 'ONLINE':
            status_kind = 'online'
        elif status_text == 'OFFLINE':
            status_kind = 'offline'
        else:
            status_kind = 'normal'

        self.add_value_card(
            'DEVICE STATUS',
            status_text,
            y,
            kind=status_kind
        )

        y += 58

        # ----------------------------------------------------
        # LAST CLOUD UPDATE
        # ----------------------------------------------------

        updated_value = data.get(
            'updated',
            data.get('last_seen', 'Not available')
        )

        self.add_value_card(
            'LAST CLOUD UPDATE',
            readable_value(updated_value),
            y,
            kind='timestamp',
            original_value=updated_value
        )

        y += 58

        # ----------------------------------------------------
        # FINISH
        # ----------------------------------------------------

        self.content.height = y + 8

        self.layout_cards()

    # ========================================================
    # B5 — SEND COMMANDS TO THE SELECTED ESP
    # Commands are sent in a background thread so the interface remains
    # responsive. A successful Telegram API response is not treated as proof
    # that the ESP executed the command; cloud data remains authoritative.
    # ========================================================

    def gpio_button_pressed(self, sender):
        # Button names are e.g. "GPIO25 ON". These are cloud requests, not
        # direct GPIO commands: write command JSON, then trigger REFRESH.
        self.send_command(sender.name)

    def special_command_pressed(self, sender):

        command = self.command_field.text.strip()

        if not command:
            self.status_label.text = 'Enter a command first'
            return

        self._special_command_text = command
        self.send_command(command, clear_special_field=True)

    def send_command(self, command, clear_special_field=False):

        esp_id = self.esp_id
        self.status_label.text = 'Sending command to {}...'.format(esp_id.upper())

        thread = threading.Thread(
            target=self._send_command_worker,
            args=(esp_id, command, clear_special_field)
        )
        thread.daemon = True
        thread.start()

    def _send_command_worker(self, esp_id, command, clear_special_field):
        """Use cloud command JSON for GPIO requests; Telegram for REFRESH/PING."""
        success = False
        detail = None
        normalized_command = command.strip().upper()
        parts = normalized_command.split()

        try:
            # GPIO25 ON/OFF (including requests typed into the command field)
            # follows the same cloud-command workflow for every ESP.
            if (
                len(parts) == 2
                and parts[0] in ('GPIO25', 'GPIO26', 'GPIO27')
                and parts[1] in ('ON', 'OFF')
            ):
                gpio_key = parts[0].lower() + '_request'
                write_command_document(esp_id, {gpio_key: parts[1]})

                success, detail = telegram_pythonista.send_message(
                    esp_id, 'REFRESH'
                )
                if success:
                    detail = 'Cloud request saved; REFRESH sent'

            else:
                # PING, REFRESH, and other supported ESP commands remain
                # available through the free-text technician command field.
                success, detail = telegram_pythonista.send_message(
                    esp_id, normalized_command
                )

        except Exception as error:
            success = False
            detail = str(error)

        ui.delay(
            lambda: self._command_result(
                esp_id, command, success, detail, clear_special_field
            ),
            0
        )

    def _command_result(self, esp_id, command, success, detail,
                        clear_special_field):

        # Ignore a result for a device that is no longer selected.
        if esp_id != self.esp_id:
            return

        if success:
            self.status_label.text = 'Command sent; waiting for cloud update'
            if clear_special_field:
                # Keep the typed command visible for repeat testing.
                self.command_field.text = self._special_command_text
            # Let the ESP process REFRESH and upload actual state before reread.
            ui.delay(self.refresh_data, COMMAND_REFRESH_DELAY)
        else:
            self.status_label.text = 'Command failed: {}'.format(detail)
            print('Command failed:', repr(detail))

    # ========================================================
    # A3 — VISUAL DESIGN: GPIO CONTROLS AND SPECIAL COMMAND
    # The controls are recreated with the cards after each cloud refresh.
    # ========================================================

    def add_output_controls(self, y):

        # No section heading: GPIO cards follow the input cards directly.
        # The 4-point gap matches the spacing between value cards.
        for gpio_number in (25, 26, 27):
            key = 'gpio{}'.format(gpio_number)
            value = None
            if isinstance(self.device_data, dict):
                value = self.device_data.get(key)

            card = ui.View()
            card.background_color = CARD_COLOR
            card.corner_radius = 12
            card.frame = (5, y, max(1, self.content.width - 10), 62)
            self.content.add_subview(card)

            title = ui.Label()
            title.text = 'GPIO {}'.format(gpio_number)
            title.text_color = SECONDARY_COLOR
            title.font = ('<System-Bold>', 13)
            title.alignment = ui.ALIGN_LEFT
            card.add_subview(title)

            state = ui.Label()
            state.text = readable_value(value) if value is not None else 'Unknown'
            state.text_color = (
                GREEN_COLOR if value is True or value == 1 else
                RED_COLOR if value is False or value == 0 else
                SECONDARY_COLOR
            )
            state.font = ('<System-Bold>', 14)
            state.alignment = ui.ALIGN_LEFT
            card.add_subview(state)

            on_button = ui.Button()
            on_button.title = 'ON'
            on_button.name = 'GPIO{} ON'.format(gpio_number)
            on_button.background_color = GREEN_COLOR
            on_button.tint_color = '#10151E'
            on_button.corner_radius = 8
            on_button.font = ('<System-Bold>', 14)
            on_button.action = self.gpio_button_pressed
            card.add_subview(on_button)

            off_button = ui.Button()
            off_button.title = 'OFF'
            off_button.name = 'GPIO{} OFF'.format(gpio_number)
            off_button.background_color = RED_COLOR
            off_button.tint_color = '#10151E'
            off_button.corner_radius = 8
            off_button.font = ('<System-Bold>', 14)
            off_button.action = self.gpio_button_pressed
            card.add_subview(off_button)

            self.cards.append({
                'kind': 'gpio_control',
                'card': card,
                'title': title,
                'value': state,
                'on_button': on_button,
                'off_button': off_button,
            })

            y += 66

        return y

    def add_special_command(self, y):

        # Special free-text command card appears before sensor and GPIO cards.
        command_card = ui.View()
        command_card.background_color = CARD_COLOR
        command_card.corner_radius = 12
        command_card.frame = (5, y, max(1, self.content.width - 10), 78)
        self.content.add_subview(command_card)

        command_title = ui.Label()
        command_title.text = 'SPECIAL COMMAND'
        command_title.text_color = SECONDARY_COLOR
        command_title.font = ('<System-Bold>', 10)
        command_title.alignment = ui.ALIGN_LEFT
        command_card.add_subview(command_title)

        self.command_field = ui.TextField()
        self.command_field.placeholder = 'Enter command...'
        self.command_field.text = getattr(self, '_special_command_text', '')
        self.command_field.background_color = '#FFFFFF'
        self.command_field.text_color = '#151923'
        self.command_field.tint_color = '#151923'
        self.command_field.corner_radius = 7
        self.command_field.font = ('<System>', 14)
        self.command_field.autocapitalization_type = ui.AUTOCAPITALIZE_ALL
        command_card.add_subview(self.command_field)

        send_button = ui.Button()
        send_button.title = 'SEND'
        send_button.background_color = BLUE_COLOR
        send_button.tint_color = '#10151E'
        send_button.corner_radius = 8
        send_button.font = ('<System-Bold>', 13)
        send_button.action = self.special_command_pressed
        command_card.add_subview(send_button)

        self.cards.append({
            'kind': 'command',
            'card': command_card,
            'title': command_title,
            'field': self.command_field,
            'send_button': send_button,
        })

        y += 82
        return y


    # ========================================================
    # A3 — VISUAL DESIGN: SECTION TITLE
    # Create the heading used to separate the GPIO output cards.
    # ========================================================

    def add_section_title(self, title, y):

        label = ui.Label()

        label.text = title
        label.text_color = BLUE_COLOR
        label.font = ('<System-Bold>', 15)
        label.alignment = ui.ALIGN_LEFT

        label.frame = (
            8,
            y,
            max(1, self.content.width - 16),
            28
        )

        self.content.add_subview(label)

    # ========================================================
    # A4 — VISUAL DESIGN: VALUE CARD
    # Create one card and its title/value labels.
    # The 'kind' argument controls the value's color and font.
    # ========================================================

    def add_value_card(
        self,
        title,
        value,
        y,
        kind='normal',
        original_value=None
    ):

        card_height = 54

        # Card width is corrected again by layout_cards().
        card_width = max(1, self.content.width - 10)

        card = ui.View()

        card.background_color = CARD_COLOR
        card.corner_radius = 12

        card.frame = (
            5,
            y,
            card_width,
            card_height
        )

        self.content.add_subview(card)

        # ----------------------------------------------------
        # CARD TITLE
        # ----------------------------------------------------

        title_label = ui.Label()

        title_label.text = title
        title_label.text_color = SECONDARY_COLOR
        title_label.font = ('<System-Bold>', 8)
        title_label.alignment = ui.ALIGN_LEFT
        title_label.number_of_lines = 1
        title_label.line_break_mode = ui.LB_CLIP

        title_label.frame = (
            5,
            7,
            max(1, card_width - 10),
            18
        )

        card.add_subview(title_label)

        # ----------------------------------------------------
        # CARD VALUE
        # ----------------------------------------------------

        value_label = ui.Label()

        value_text = readable_value(value)

        # Put ISO timestamps on two lines.
        if kind == 'timestamp':
            value_text = value_text.replace('T', '\n', 1)

        value_label.text = value_text
        value_label.text_color = TEXT_COLOR

        if kind == 'output':

            if original_value is True or original_value == 1:
                value_label.text_color = GREEN_COLOR

            elif original_value is False or original_value == 0:
                value_label.text_color = RED_COLOR

        elif kind == 'online':

            value_label.text_color = GREEN_COLOR

        elif kind == 'offline':

            value_label.text_color = RED_COLOR

        elif kind == 'input':

            if original_value is True or original_value == 1:
                value_label.text_color = GREEN_COLOR

            elif original_value is False or original_value == 0:
                value_label.text_color = ORANGE_COLOR

        elif kind == 'sensor':

            value_label.text_color = BLUE_COLOR

        elif kind == 'timestamp':

            value_label.text_color = TEXT_COLOR
            value_label.font = ('<System>', 14)

        elif kind == 'error':

            value_label.text_color = RED_COLOR
            value_label.font = ('<System>', 15)

        else:

            value_label.font = ('<System-Bold>', 24)

        if kind not in ('timestamp', 'error'):
            value_label.font = ('<System-Bold>', 24)

        value_label.alignment = ui.ALIGN_LEFT
        value_label.number_of_lines = 2
        value_label.line_break_mode = ui.LB_WORD_WRAP

        value_label.frame = (
            5,
            32,
            max(1, card_width - 10),
            58
        )

        card.add_subview(value_label)

        self.cards.append({
            'card': card,
            'title': title_label,
            'value': value_label,
        })

    # ========================================================
    # A5 — VISUAL DESIGN: RESPONSIVE CARD SIZING
    # Recalculate widths when the screen or scroll area changes.
    # This preserves the existing full-width card layout.
    # ========================================================

    def layout_cards(self):

        # ----------------------------------------------------
        # CRITICAL FIX:
        # Make the CONTENT VIEW as wide as the SCROLL VIEW.
        # ----------------------------------------------------

        content_width = self.scroll.width

        if content_width <= 0:
            content_width = self.width

        if content_width <= 0:
            return

        self.content.frame = (
            0,
            0,
            content_width,
            max(1, self.content.height)
        )

        # Leave only 5 points of margin on each side.
        card_width = max(1, content_width - 10)

        for card_info in self.cards:

            card = card_info['card']
            title_label = card_info['title']
            kind = card_info.get('kind', 'value')

            # Card background spans nearly the full screen.
            card.frame = (
                5,
                card.y,
                card_width,
                card.height
            )

            if kind == 'gpio_control':
                # Keep GPIO name/state at left and ON/OFF buttons at right.
                button_width = min(68, max(52, (card_width - 150) / 2))
                right_margin = 8
                gap = 6
                off_x = card_width - right_margin - button_width
                on_x = off_x - gap - button_width
                left_width = max(90, on_x - 14)

                title_label.frame = (8, 7, left_width, 20)
                card_info['value'].frame = (8, 30, left_width, 22)
                card_info['on_button'].frame = (on_x, 12, button_width, 38)
                card_info['off_button'].frame = (off_x, 12, button_width, 38)

            elif kind == 'command':
                title_label.frame = (8, 5, max(1, card_width - 16), 18)
                send_width = 68
                card_info['field'].frame = (
                    8, 29, max(1, card_width - send_width - 28), 36
                )
                card_info['send_button'].frame = (
                    card_width - send_width - 8, 29, send_width, 36
                )

            else:
                value_label = card_info['value']

                # Title uses nearly the entire card width.
                title_label.frame = (
                    5,
                    7,
                    max(1, card_width - 10),
                    18
                )

                # Reading uses nearly the entire card width.
                value_label.frame = (
                    5,
                    23,
                    max(1, card_width - 10),
                    27
                )

        # Update the scrollable area.
        self.scroll.content_size = (
            content_width,
            self.content.height
        )

    # ========================================================
    # B5 — STOP AUTOMATIC REFRESH
    # Mark the dashboard as stopped so scheduled refreshes do not continue
    # after the view closes.
    # ========================================================

    def will_close(self):

        self.running = False


# ============================================================
# START DASHBOARD
# ============================================================

dashboard = HomeDashboard()

dashboard.present(
    'fullscreen',
    orientations=[
        'portrait'
    ]
)
