"""Receipt printer rendering and USB device management.

WhiteboardPrinter: Main class for rendering messages to PIL Image and printing via ESC/POS.
Supports multiple layout types: plain text, structured JSON (monday tasks), priority alerts.
"""

import logging
import time
import json
import textwrap
import gc
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance
from pilmoji import Pilmoji
from escpos.printer import Usb
import qrcode

from . import config
from .emoji_map import EMOJI_TAG_MAP
from .helpers import strip_emojis, detect_priority, get_priority_symbol, draw_priority_banner


class WhiteboardPrinter:
    """Thermal receipt printer driver for ESC/POS compatible devices.
    
    Renders messages to PIL Image objects and prints via USB connection.
    Supports preview mode for testing without hardware.
    """
    
    def __init__(self, preview_mode=False):
        """Initialize printer connection.
        
        Args:
            preview_mode (bool): If True, display images instead of printing
        """
        self.p = None
        self._paused = False
        self.preview_mode = preview_mode
        self.preview_count = 0
        if not preview_mode:
            self.connect()

    def set_paused(self, paused: bool):
        """Pause/resume printing (used by memory monitor)."""
        self._paused = bool(paused)

    @property
    def is_paused(self):
        """Check if printer is paused."""
        return self._paused

    def connect(self, retries=3, retry_delay=0.5):
        """Establish USB connection to printer device.
        
        Args:
            retries (int): Number of connection attempts (default: 3)
            retry_delay (float): Delay between retries in seconds (default: 0.5)
        """
        if self.preview_mode:
            print("📸 Preview mode - no printer connection needed")
            return
        
        last_error = None
        for attempt in range(retries):
            try:
                if config.PRINTER_PROFILE:
                    self.p = Usb(config.VENDOR_ID, config.PRODUCT_ID, 0, profile=config.PRINTER_PROFILE)
                else:
                    self.p = Usb(config.VENDOR_ID, config.PRODUCT_ID, 0)
                
                # detach kernel driver if active
                try:
                    if self.p.device.is_kernel_driver_active(0):
                        self.p.device.detach_kernel_driver(0)
                except Exception:
                    # device/kernel driver info may not be available on some platforms
                    logging.debug("Could not check/detach kernel driver")
                
                # Give USB device time to settle after connection
                time.sleep(0.5)
                print("🟢 Hardware Linked")
                return
            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    logging.debug(f"Connection attempt {attempt + 1}/{retries} failed, retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    continue
        
        logging.exception(f"Failed to connect to USB printer after {retries} attempts: {last_error}")
        self.p = None
    
    def is_ready(self):
        """Check if printer is connected and ready.
        
        Returns:
            bool: True if printer is connected and operational
        """
        if self.preview_mode or self.p is None:
            return False
        try:
            # Try to communicate with the device
            self.p.device.get_active_configuration()
            return True
        except Exception:
            logging.warning("Printer not ready - device may have been disconnected")
            return False

    def _transform_phone_url(self, click_url, message):
        """Transform phone numbers in click_url to tel: or sms: scheme based on message content.
        
        Args:
            click_url (str): Potential phone number or URL
            message (str): Message text to check for keywords
            
        Returns:
            str: Transformed URL or original click_url if no transformation applies
        """
        # Feature disabled or no click_url
        if not config.PHONE_QR_ENABLED or not click_url:
            return click_url
        
        # Check if click_url is only digits (phone number)
        if not click_url.replace("+", "").replace(" ", "").replace("-", "").isdigit():
            return click_url
        
        # Extract only digits from phone number
        phone_digits = ''.join(c for c in click_url if c.isdigit())
        if not phone_digits:
            return click_url
        
        # Check message for keywords (case-insensitive)
        message_upper = message.upper()
        
        # Check for CALL keywords
        for keyword in config.PHONE_CALL_KEYWORDS:
            if keyword in message_upper:
                # Format: tel:+{COUNTRY_CODE}{phone}
                return f"tel:+{config.COUNTRY_CODE}{phone_digits}"
        
        # Check for TEXT keywords
        for keyword in config.PHONE_TEXT_KEYWORDS:
            if keyword in message_upper:
                # Format: sms://{phone}
                return f"sms://{phone_digits}"
        
        return click_url

    def create_layout(self, message, subtext=None, priority="default", payload=None):
        """Create layout with ntfy fields: tags/priority (header), title, divider, message, QR if click present.
        
        Args:
            message (str): Main message text
            subtext (str): Optional secondary text
            priority (str): Priority level ("max", "high", "default", "low", "min")
            payload (dict): ntfy message payload with title, tags, click URL
            
        Returns:
            PIL.Image: Rendered receipt image (white background, black text/graphics)
        """
        # Compute width from paper size and printer DPI, with safe margins
        full_width = int(round(config.PAPER_WIDTH_MM / 25.4 * config.PRINTER_DPI))
        safe_margin_px = int(round(config.SAFE_MARGIN_MM / 25.4 * config.PRINTER_DPI))
        width = full_width - (2 * safe_margin_px)
        x_offset_px = int(round(config.X_OFFSET_MM / 25.4 * config.PRINTER_DPI))
        y_offset_px = int(round(config.Y_OFFSET_MM / 25.4 * config.PRINTER_DPI))
        left_margin = safe_margin_px + x_offset_px

        # Font sizes (title large, message medium)
        font_main_size = 40
        font_sub_size = 35
        font_title_size = 70
        font_subtext_size = 24

        try:
            font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_title_size)
            font_message = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_main_size)
            font_reg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_sub_size)
            font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_title_size)
            font_subtext = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_subtext_size)
        except Exception:
            logging.warning("Could not load TTF fonts; falling back to default font")
            font_bold = font_message = font_reg = font_title = font_subtext = ImageFont.load_default()

        # Extract fields from ntfy payload
        payload = payload or {}
        tags = payload.get("tags", "")
        title = payload.get("title", "")
        click_url = payload.get("click", "")

        # Parse tags and translate to emoji
        if isinstance(tags, str):
            tags_list = [t.strip() for t in tags.split(",") if t.strip()]
        else:
            tags_list = tags if isinstance(tags, list) else []

        translated_tags = []
        for tag in tags_list:
            if tag in EMOJI_TAG_MAP:
                translated_tags.append(EMOJI_TAG_MAP[tag])
            else:
                translated_tags.append(tag)

        # Header: tags OR priority icon
        if translated_tags:
            header_text = " | ".join(translated_tags)
        else:
            symbol, count = get_priority_symbol(priority)
            header_text = symbol * count

        # Enforce message caps
        if len(message) > config.MAX_MESSAGE_LENGTH:
            message = message[:config.MAX_MESSAGE_LENGTH-3] + "..."

        # Wrap main message - auto-scale to fit all text (no line limit)
        wrapped = textwrap.wrap(message, width=10)
        lines = wrapped  # Use all wrapped lines, no truncation

        # Measure text sizes
        sample_main_bbox = font_bold.getbbox("Ag")
        main_line_height = sample_main_bbox[3] - sample_main_bbox[1]
        sample_sub_bbox = font_reg.getbbox("Ag")
        sub_line_height = sample_sub_bbox[3] - sample_sub_bbox[1]
        sample_title_bbox = font_title.getbbox("Ag")
        title_line_height = sample_title_bbox[3] - sample_title_bbox[1]

        top_pad = 20
        header_gap = 80
        title_gap = 15
        line_gap = 10
        divider_gap = 15
        date_gap = 25
        subtext_gap = 10
        bottom_pad = 40  # 20px additional padding for QR code

        # Calculate header height
        header_bbox = font_bold.getbbox(header_text)
        header_height = header_bbox[3] - header_bbox[1]

        # Calculate title height
        title_height = 0
        if title:
            title_wrapped = textwrap.wrap(title, width=12)
            title_height = (len(title_wrapped) * title_line_height) + (max(0, len(title_wrapped) - 1) * line_gap)

        # Main message height
        lines_height = (len(lines) * main_line_height) + (max(0, len(lines) - 1) * line_gap)

        # QR code height (if click URL present)
        qr_height = 0
        qr_img = None
        if click_url:
            qr_size = 100
            qr_height = qr_size + subtext_gap
            try:
                # Transform phone numbers to tel: or sms: schemes if applicable
                qr_data = self._transform_phone_url(click_url, message)
                
                qr = qrcode.QRCode(version=1, box_size=3, border=1)
                qr.add_data(qr_data)
                qr.make()
                qr_img = qr.make_image(fill_color="black", back_color="white")
                qr_img = qr_img.resize((qr_size, qr_size), Image.NEAREST)
            except Exception as e:
                logging.warning("QR generation failed: %s", e)
                qr_height = 0

        # Calculate total height
        total_height = (
            top_pad +
            header_height + header_gap +
            (title_height + title_gap if title else 0) +
            lines_height +
            divider_gap + 3 + date_gap +
            sub_line_height + 5 +
            sub_line_height +
            qr_height +
            bottom_pad
        )
        
        # Apply max height limit if configured
        if config.MAX_HEIGHT_MM:
            max_height_px = int(round(config.MAX_HEIGHT_MM / 25.4 * config.PRINTER_DPI))
            if total_height > max_height_px:
                total_height = max_height_px

        canvas = Image.new('RGB', (full_width, total_height), color=(255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        y = top_pad + y_offset_px

        # 1. Header (tags or priority symbol) - centered with emoji width estimation
        char_width = font_title_size * 0.55
        estimated_width = len(header_text) * char_width
        header_x = int(left_margin + (width - estimated_width) / 2)
        with Pilmoji(canvas) as pilmoji:
            pilmoji.text((header_x, y), header_text, (0, 0, 0), font_bold)
        y += header_height + header_gap

        # 2. Title (if present)
        if title:
            title_wrapped = textwrap.wrap(title, width=12)
            for title_line in title_wrapped:
                title_bbox = draw.textbbox((0, 0), title_line, font=font_title)
                title_x = (width - (title_bbox[2] - title_bbox[0])) // 2 + left_margin
                draw.text((title_x, y), title_line, font=font_title, fill=(0, 0, 0))
                y += title_line_height + line_gap
            
            y += title_gap
            draw.line([left_margin + 20, y, left_margin + width - 20, y], fill=(0, 0, 0), width=3)
            y += divider_gap

        # 3. Main message text (centered, large)
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font_message)
            draw.text(((width - (bbox[2]-bbox[0]))//2 + left_margin, y), line, font=font_message, fill=(0, 0, 0))
            y += main_line_height + line_gap

        # 4. Divider line
        y += divider_gap
        draw.line([left_margin + 20, y, left_margin + width - 20, y], fill=(0, 0, 0), width=3)
        y += date_gap

        # 5. Date/Time (centered, smaller)
        date_str = time.strftime("%b %d, %Y")
        time_str = time.strftime("%H:%M:%S")
        bbox = draw.textbbox((0, 0), date_str, font=font_reg)
        draw.text(((width - (bbox[2]-bbox[0]))//2 + left_margin, y), date_str, font=font_reg, fill=(0, 0, 0))
        y += sub_line_height + 5
        bbox_time = draw.textbbox((0, 0), time_str, font=font_reg)
        draw.text(((width - (bbox_time[2]-bbox_time[0]))//2 + left_margin, y), time_str, font=font_reg, fill=(0, 0, 0))
        y += sub_line_height

        # 6. QR code (if click URL present, centered at bottom)
        if qr_img:
            y += subtext_gap
            qr_x = (width - qr_img.width) // 2 + left_margin
            canvas.paste(qr_img, (qr_x, y))
            y += qr_img.height

        y += bottom_pad
        return canvas

    def render_structured(self, payload):
        """Render structured JSON payloads (e.g., monday.com tasks)."""
        msg_type = payload.get("type", "generic")
        
        if msg_type == "monday_task":
            return self._render_monday_task(payload)
        elif msg_type == "text_with_subtext":
            message = payload.get("message", "Message")
            subtext = payload.get("subtext")
            return self.create_layout(strip_emojis(message), subtext=subtext)
        elif msg_type == "priority_alert":
            return self._render_priority_alert(payload)
        else:
            return self.create_layout(json.dumps(payload))
    
    def _render_monday_task(self, payload):
        """Kanban card style layout with borders and priority indicator."""
        full_width = int(round(config.PAPER_WIDTH_MM / 25.4 * config.PRINTER_DPI))
        safe_margin_px = int(round(config.SAFE_MARGIN_MM / 25.4 * config.PRINTER_DPI))
        x_offset_px = int(round(config.X_OFFSET_MM / 25.4 * config.PRINTER_DPI))
        y_offset_px = int(round(config.Y_OFFSET_MM / 25.4 * config.PRINTER_DPI))
        left_margin = safe_margin_px + x_offset_px
        
        try:
            font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
            font_meta = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
        except Exception:
            font_title = font_meta = font_small = ImageFont.load_default()
        
        task_name = payload.get("task", "Task").strip()[:50]
        priority = payload.get("priority", "medium").lower()
        status = payload.get("status", "todo").lower()
        assignee = payload.get("assignee", "").upper()[:3]
        due_date = payload.get("due_date", "")[:10]
        ref_id = payload.get("id", payload.get("ref_id", ""))
        qr_data = payload.get("qr_url") or payload.get("url")
        
        priority_widths = {
            "critical": 8,
            "high": 6,
            "medium": 4,
            "low": 2,
        }
        priority_width = priority_widths.get(priority, 3)
        
        qr_size = 80 if qr_data else 0
        card_height = 220 + qr_size
        card_width = full_width - (2 * safe_margin_px)
        padding = 15
        card_x = left_margin
        card_y = 10 + y_offset_px
        
        canvas = Image.new('RGB', (full_width, card_height), color=(255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        
        draw.rectangle(
            [card_x, card_y, card_x + card_width, card_y + card_height - 15],
            outline=(0, 0, 0),
            width=2
        )
        
        draw.rectangle(
            [card_x, card_y, card_x + priority_width, card_y + card_height - 15],
            fill=(0, 0, 0),
            outline=(0, 0, 0)
        )
        
        y = card_y + padding
        content_x = card_x + padding + 5 + 5
        
        lines = textwrap.wrap(task_name, width=18)
        for line in lines[:2]:
            draw.text((content_x, y), line, font=font_title, fill=(0, 0, 0))
            y += 32
        
        y += 8
        
        status_icon = config.ICON_STATUS.get(status, "[?]")
        priority_icon = config.ICON_PRIORITY.get(priority, "[!]")
        draw.text((content_x, y), f"{status_icon} {priority_icon}", font=font_meta, fill=(0, 0, 0))
        y += 24
        
        meta_parts = []
        if assignee:
            meta_parts.append(f"@{assignee}")
        if due_date:
            meta_parts.append(f"{due_date}")
        
        if meta_parts:
            meta_text = "  |  ".join(meta_parts)
            draw.text((content_x, y), meta_text, font=font_small, fill=(0, 0, 0))
            y += 20
        
        if ref_id:
            draw.text((content_x, y), f"#{ref_id}", font=font_small, fill=(0, 0, 0))
            y += 18
        
        if qr_data:
            try:
                qr = qrcode.QRCode(version=1, box_size=3, border=1)
                qr.add_data(qr_data)
                qr.make()
                qr_img = qr.make_image(fill_color="black", back_color="white")
                qr_resized = qr_img.resize((70, 70), Image.NEAREST)
                qr_x = card_x + card_width - 75
                qr_y = card_y + card_height - 85
                canvas.paste(qr_resized, (qr_x, qr_y))
            except Exception as e:
                logging.warning("QR generation failed: %s", e)
        
        return canvas

    def _render_priority_alert(self, payload):
        """Render a priority-based alert with visual banner and optional subtext."""
        full_width = int(round(config.PAPER_WIDTH_MM / 25.4 * config.PRINTER_DPI))
        safe_margin_px = int(round(config.SAFE_MARGIN_MM / 25.4 * config.PRINTER_DPI))
        x_offset_px = int(round(config.X_OFFSET_MM / 25.4 * config.PRINTER_DPI))
        y_offset_px = int(round(config.Y_OFFSET_MM / 25.4 * config.PRINTER_DPI))
        left_margin = safe_margin_px + x_offset_px
        
        try:
            font_banner = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
            font_subtext = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        except Exception:
            font_banner = font_subtext = ImageFont.load_default()
        
        priority = payload.get("priority", "medium").lower()
        message = payload.get("message", "Alert")
        subtext = payload.get("subtext", "")
        
        width = full_width - (2 * safe_margin_px)
        banner_height = 80
        padding = 15
        
        total_height = banner_height + padding + padding
        if subtext:
            subtext_bbox = ImageFont.load_default().getbbox("Ag")
            subtext_height = (subtext_bbox[3] - subtext_bbox[1]) + padding
            total_height += subtext_height
        
        canvas = Image.new('RGB', (full_width, total_height), color=(255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        
        banner_x = left_margin
        banner_y = padding + y_offset_px
        draw_priority_banner(draw, banner_x, banner_y, width, banner_height, priority, font_banner)
        
        if subtext:
            subtext_y = banner_y + banner_height + padding
            subtext_bbox = draw.textbbox((0, 0), subtext, font=font_subtext)
            subtext_x = left_margin + (width - (subtext_bbox[2] - subtext_bbox[0])) // 2
            draw.text((subtext_x, subtext_y), strip_emojis(subtext), font=font_subtext, fill=(80, 80, 80))
        
        return canvas

    def create_calibration_grid(self):
        """Create calibration grid with coordinates to determine printable area.
        
        Returns PIL.Image with grid showing:
        - Horizontal lines every 10mm with offset labels
        - Vertical lines every 5mm with coordinate markers
        - Center line indicator
        - Right edge markers to determine max printable width
        """
        full_width = int(round(config.PAPER_WIDTH_MM / 25.4 * config.PRINTER_DPI))
        height = int(round(150 / 25.4 * config.PRINTER_DPI))  # 150mm tall grid
        mm_to_px = config.PRINTER_DPI / 25.4
        
        canvas = Image.new('RGB', (full_width, height), color=(255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        
        try:
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
            font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 34)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
            font_tiny = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        except Exception:
            font_large = font_medium = font_small = font_tiny = ImageFont.load_default()
        
        # Draw title
        title = "CALIBRATION GRID"
        title_bbox = draw.textbbox((0, 0), title, font=font_large)
        title_x = (full_width - (title_bbox[2] - title_bbox[0])) // 2
        draw.text((title_x, 16), title, font=font_large, fill=(0, 0, 0))
        
        # Instructions - larger and more readable
        inst1 = "NOTE: Last visible LETTER on RIGHT edge"
        inst2 = "(Letters only at 10mm marks)"
        inst1_bbox = draw.textbbox((0, 0), inst1, font=font_tiny)
        inst2_bbox = draw.textbbox((0, 0), inst2, font=font_tiny)
        draw.text(((full_width - (inst1_bbox[2] - inst1_bbox[0])) // 2, 80), inst1, font=font_tiny, fill=(0, 0, 0))
        draw.text(((full_width - (inst2_bbox[2] - inst2_bbox[0])) // 2, 105), inst2, font=font_tiny, fill=(0, 0, 0))
        
        grid_start_y = 260
        grid_end_y = height - 160
        
        # Draw horizontal lines every 10mm with row numbers
        for row_mm in range(0, 65, 10):
            y = grid_start_y + int(row_mm * mm_to_px)
            draw.line([0, y, full_width, y], fill=(150, 150, 150), width=2)
            # Row label on left - larger
            row_label = f"{row_mm}mm"
            draw.text((10, y - 20), row_label, font=font_small, fill=(0, 0, 0))
        
        # Draw vertical lines every 5mm; label letters at 10mm marks
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLMNOPQRSTUVWXYZ"  # Extended for wider paper
        for col_idx, col_mm in enumerate(range(0, int(config.PAPER_WIDTH_MM) + 1, 5)):
            x = int(col_mm * mm_to_px)
            if x >= full_width:
                break
            
            # Thicker line every 10mm
            line_width = 3 if col_mm % 10 == 0 else 1
            draw.line([x, grid_start_y, x, grid_end_y], fill=(100, 100, 100), width=line_width)
            
            # Column letter at top - much larger
            if col_mm % 10 == 0 and col_idx < len(letters):
                letter = letters[col_idx]
                letter_bbox = draw.textbbox((0, 0), letter, font=font_medium)
                letter_width = letter_bbox[2] - letter_bbox[0]
                draw.text((x - letter_width // 2, grid_start_y - 62), letter, font=font_medium, fill=(0, 0, 0))
                # mm value below letter - still readable
                mm_text = f"{col_mm}mm"
                mm_bbox = draw.textbbox((0, 0), mm_text, font=font_tiny)
                mm_width = mm_bbox[2] - mm_bbox[0]
                draw.text((x - mm_width // 2, grid_start_y - 34), mm_text, font=font_tiny, fill=(100, 100, 100))
        
        # Draw center line (current paper center)
        center_x = full_width // 2
        draw.line([center_x, grid_start_y, center_x, grid_end_y], fill=(255, 0, 0), width=4)
        center_label = "CENTER"
        center_bbox = draw.textbbox((0, 0), center_label, font=font_small)
        center_width = center_bbox[2] - center_bbox[0]
        draw.text((center_x - center_width // 2, grid_start_y + 24), center_label, font=font_small, fill=(255, 0, 0))
        
        # Draw current safe margins if configured
        safe_margin_px = int(round(config.SAFE_MARGIN_MM * mm_to_px))
        left_margin = safe_margin_px
        right_margin = full_width - safe_margin_px
        
        # Left margin line
        draw.line([left_margin, grid_start_y, left_margin, grid_end_y], fill=(0, 150, 0), width=2)
        draw.text((left_margin + 6, grid_start_y + 32), "LEFT", font=font_small, fill=(0, 150, 0))
        
        # Right margin line
        draw.line([right_margin, grid_start_y, right_margin, grid_end_y], fill=(0, 150, 0), width=2)
        draw.text((right_margin - 70, grid_start_y + 32), "RIGHT", font=font_small, fill=(0, 150, 0))
        
        # Config info at bottom
        info_y = height - 90
        draw.text((10, info_y), f"Current Config:", font=font_small, fill=(0, 0, 0))
        draw.text((10, info_y + 22), f"PAPER_WIDTH_MM={config.PAPER_WIDTH_MM}", font=font_tiny, fill=(0, 0, 0))
        draw.text((10, info_y + 42), f"X_OFFSET_MM={config.X_OFFSET_MM}", font=font_tiny, fill=(0, 0, 0))
        draw.text((10, info_y + 62), f"SAFE_MARGIN_MM={config.SAFE_MARGIN_MM}", font=font_tiny, fill=(0, 0, 0))
        
        return canvas
    
    def create_alignment_test(self):
        """Create alignment test pattern with center line and tick marks."""
        width = int(round(config.PAPER_WIDTH_MM / 25.4 * config.PRINTER_DPI))
        height = int(round(width * 1.2))
        x_offset_px = int(round(config.X_OFFSET_MM / 25.4 * config.PRINTER_DPI))

        canvas = Image.new('RGB', (width, height), color=(255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        draw.rectangle([0, 0, width - 1, height - 1], outline=(0, 0, 0), width=2)

        cx = width // 2 + x_offset_px
        draw.line([cx, 0, cx, height], fill=(0, 0, 0), width=3)

        mm_to_px = config.PRINTER_DPI / 25.4
        for mm in range(0, int(config.PAPER_WIDTH_MM) + 1, 10):
            x = int(round(mm * mm_to_px)) + x_offset_px
            draw.line([x, 0, x, 15], fill=(0, 0, 0), width=1)
            draw.line([x, height - 15, x, height], fill=(0, 0, 0), width=1)

        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        except Exception:
            font = ImageFont.load_default()
        
        label1 = f"X_OFFSET_MM={config.X_OFFSET_MM}"
        label2 = f"Center at {config.PAPER_WIDTH_MM/2}mm"
        bbox1 = draw.textbbox((0, 0), label1, font=font)
        bbox2 = draw.textbbox((0, 0), label2, font=font)
        draw.text(((width - (bbox1[2]-bbox1[0]))//2, height//2 - 30), label1, font=font, fill=(0, 0, 0))
        draw.text(((width - (bbox2[2]-bbox2[0]))//2, height//2 + 10), label2, font=font, fill=(0, 0, 0))

        return canvas

    def print_msg(self, message, subtext=None, payload=None):
        """Print a message (structured or plain text).
        
        Args:
            message (str): Message text or JSON payload
            subtext (str): Optional secondary text
            payload (dict): ntfy payload data (priority, tags, title, click)
        """
        if self.is_paused:
            logging.warning("Printer paused due to high memory — dropping message")
            return
        if not self.p:
            self.connect()
        
        # Detect if message is JSON (structured payload)
        try:
            msg_payload = json.loads(message)
            if isinstance(msg_payload, dict) and "type" in msg_payload:
                if "task" in msg_payload:
                    msg_payload["task"] = strip_emojis(msg_payload["task"])
                img = self.render_structured(msg_payload)
            else:
                priority = detect_priority(message, payload or msg_payload)
                img = self.create_layout(strip_emojis(message), subtext=subtext, priority=priority, payload=payload or msg_payload)
        except (json.JSONDecodeError, ValueError):
            priority = detect_priority(message, payload)
            img = self.create_layout(strip_emojis(message), subtext=subtext, priority=priority, payload=payload)
        
        # Preview mode - show image instead of printing
        if self.preview_mode:
            scale = max(1, config.IMAGE_SCALE)
            
            # Ensure scaled image doesn't exceed paper width
            max_scaled_width = config.PAPER_WIDTH_PX
            if img.width * scale > max_scaled_width:
                scale = max(1, max_scaled_width // img.width)
                logging.debug(f"Capping scale to {scale} to fit paper width {config.PAPER_WIDTH_PX}px")
            
            scaled_width = img.width * scale
            scaled_height = img.height * scale
            img_scaled = img.resize((scaled_width, scaled_height), Image.NEAREST)
            img_mono = img_scaled.convert("L")
            img_mono = ImageOps.autocontrast(img_mono)
            img_mono = ImageEnhance.Contrast(img_mono).enhance(config.IMAGE_CONTRAST)
            img_final = img_mono.convert("1")
            
            self.preview_count += 1
            timestamp = time.strftime("%H:%M:%S")
            print(f"\n[{timestamp}] Preview #{self.preview_count}: {message[:60]}{'...' if len(message) > 60 else ''}")
            print(f"   Resolution: {img_final.width}x{img_final.height}px")
            print(f"   Paper: {config.PAPER_WIDTH_MM}mm ({config.PAPER_WIDTH_PX}px @ {config.PRINTER_DPI} DPI)")
            print(f"   Printable: {config.PAPER_WIDTH_MM - 2*config.SAFE_MARGIN_MM}mm ({config.MAX_PRINTABLE_WIDTH_PX}px)")
            img_final.show()
            return
        
        # Retry logic for USB operations
        max_retries = 3
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                if not self.p:
                    logging.warning("No printer connected — skipping print: %s", message)
                    return
                self.p.hw("INIT")
                scale = max(1, config.IMAGE_SCALE)
                
                # Ensure scaled image doesn't exceed paper width
                max_scaled_width = config.PAPER_WIDTH_PX
                if img.width * scale > max_scaled_width:
                    scale = max(1, max_scaled_width // img.width)
                    logging.debug(f"Capping scale to {scale} to fit paper width {config.PAPER_WIDTH_PX}px")
                
                scaled_width = img.width * scale
                scaled_height = img.height * scale
                img_scaled = img.resize((scaled_width, scaled_height), Image.NEAREST)
                img_mono = img_scaled.convert("L")
                img_mono = ImageOps.autocontrast(img_mono)
                img_mono = ImageEnhance.Contrast(img_mono).enhance(config.IMAGE_CONTRAST)
                img_mono = img_mono.convert("1")
                
                if config.IMAGE_IMPLS:
                    impls = [i.strip() for i in config.IMAGE_IMPLS.split(',') if i.strip()]
                else:
                    impls = [config.IMAGE_IMPL]

                printed = False
                for impl in impls:
                    try:
                        self.p.image(img_mono, impl=impl)
                        printed = True
                        break
                    except TypeError:
                        self.p.image(img_mono)
                        printed = True
                        break
                    except Exception:
                        logging.exception("Image print failed with impl=%s", impl)

                if not printed:
                    logging.error("All image implementations failed. Try IMAGE_IMPLS=bitImageColumn,bitImageRaster,graphics,raster")
                
                self.p.text("\n\n\n\n")
                self.p.cut()
                print(f"✅ Printed: {message[:50]}")
                break
            except Exception as e:
                is_usb_error = "USBError" in str(type(e).__name__) or "Entity not found" in str(e) or "No such device" in str(e)
                
                if is_usb_error and attempt < max_retries - 1:
                    logging.warning("USB error on attempt %d/%d: %s - retrying after %.1fs", attempt + 1, max_retries, e, retry_delay)
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    self.connect()
                    continue
                else:
                    logging.exception("Printing error (attempt %d/%d)", attempt + 1, max_retries)
                    self.connect()
                    break
        
        # Cleanup
        if 'img' in locals():
            try:
                del img
            except Exception:
                pass
        if 'img_scaled' in locals():
            try:
                del img_scaled
            except Exception:
                pass
        if 'img_mono' in locals():
            try:
                del img_mono
            except Exception:
                pass
        gc.collect()
