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

    def connect(self):
        """Establish USB connection to printer device."""
        if self.preview_mode:
            print("📸 Preview mode - no printer connection needed")
            return
        
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
        except Exception:
            logging.exception("Failed to connect to USB printer")
            self.p = None

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

        # Wrap main message
        wrapped = textwrap.wrap(message, width=10)
        lines = wrapped[:config.MAX_LINES]
        if len(wrapped) > config.MAX_LINES and lines:
            lines[-1] = (lines[-1][:max(0, len(lines[-1]) - 3)] + "...")

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
        bottom_pad = 20

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
                qr = qrcode.QRCode(version=1, box_size=3, border=1)
                qr.add_data(click_url)
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
