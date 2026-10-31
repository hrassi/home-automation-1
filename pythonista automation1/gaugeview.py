import ui
import math

class GaugeView(ui.View):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # --- Background image (must exist in Pythonista) ---
        self.bg_image = ui.Image.named('gauge_transparent.png')

        # --- Gauge values ---
        self.value = 50
        self.max_value = 100

        # --- Needle appearance ---
        self.needle_length = 70   # forward length in pixels
        self.needle_tail = 10     # length behind pivot
        self.needle_width = 1     # thickness in pixels
        self.pivot_radius = 3     # pivot circle radius

        # --- Digital display settings ---
        self.digital_font_name = 'DBLCDTempBlack'  # or 'Courier-Bold' if unavailable
        self.digital_font_size = 11
        self.digital_color = (0, 1, 0)  # green LED digits

        # Position of the existing black rectangle in the PNG
        # Adjust this if the text is not perfectly centered
        self.digital_center_x = self.width / 2
        self.digital_center_y = self.height * 0.745  # adjust for vertical placement

        # --- Gauge label (configurable from ex.py) ---
        self.label_text = ""                       # to be set from ex.py
        self.label_font_name = 'Helvetica-Bold'    # default font
        self.label_font_size = 16                  # default size
        self.label_color = (0, 0, 0)               # default black
        self.label_y_offset = 30                   # distance above the digital display

        # --- Calibration angles (degrees) ---
        self.min_angle = -150   # angle when value = 0
        self.max_angle = 90     # angle when value = max_value

    def draw(self):
        # --- Draw background image ---
        if self.bg_image:
            img_w, img_h = self.bg_image.size
            scale = min(self.width / img_w, self.height / img_h)
            new_w = img_w * scale
            new_h = img_h * scale
            x = (self.width - new_w) / 2
            y = (self.height - new_h) / 2
            self.bg_image.draw(x, y, new_w, new_h)
        else:
            ui.set_color('lightgrey')
            ui.Path.oval(0, 0, self.width, self.height).fill()

        # --- Needle calculation ---
        center_x = self.width / 2
        center_y = self.height / 2
        radius = self.needle_length - 30
        tail = self.needle_tail

        angle = math.radians(
            self.min_angle + (self.value / self.max_value) * (self.max_angle - self.min_angle)
        )

        end_x = center_x + radius * math.cos(angle)
        end_y = center_y + radius * math.sin(angle)
        start_x = center_x - tail * math.cos(angle)
        start_y = center_y - tail * math.sin(angle)

        # --- Draw needle ---
        ui.set_color('red')
        path = ui.Path()
        path.move_to(start_x, start_y)
        path.line_to(end_x, end_y)
        path.line_width = self.needle_width
        path.stroke()

        # --- Draw pivot circle ---
        ui.Path.oval(center_x - self.pivot_radius,
                     center_y - self.pivot_radius,
                     self.pivot_radius * 2,
                     self.pivot_radius * 2).fill()

        # --- Draw gauge label ---
        if self.label_text:
            label_font = (self.label_font_name, self.label_font_size)
            label_size = ui.measure_string(self.label_text, font=label_font)
            label_x = self.digital_center_x - label_size[0] / 2
            label_y = self.digital_center_y - self.label_y_offset - label_size[1] / 2
            ui.draw_string(
                self.label_text,
                (label_x, label_y, label_size[0], label_size[1]),
                font=label_font,
                color=self.label_color
            )

        # --- Draw digital value ---
        value_text = f"{int(self.value):03d}"  # 3 digits with leading zeros
        font = (self.digital_font_name, self.digital_font_size)
        text_size = ui.measure_string(value_text, font=font)
        text_x = self.digital_center_x - text_size[0] / 2
        text_y = self.digital_center_y - text_size[1] / 2
        ui.draw_string(
            value_text,
            (text_x, text_y, text_size[0], text_size[1]),
            font=font,
            color=self.digital_color
        )

    def set_value(self, val):
        self.value = max(0, min(self.max_value, val))
        self.set_needs_display()
