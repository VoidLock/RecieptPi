import os
import time
import json
import requests
import textwrap
import usb.core
import usb.util
import argparse
import signal
import sys
import logging
import threading
import gc
import re
try:
    import psutil
except Exception:
    psutil = None
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance
from escpos.printer import Usb
import qrcode

# --- CONFIG (env / CLI overridable) ---
DEFAULT_NTFY_HOST = os.environ.get("NTFY_HOST")
DEFAULT_NTFY_TOPIC = os.environ.get("NTFY_TOPIC")
VENDOR_ID = int(os.environ.get("PRINTER_VENDOR", "0x0fe6"), 16)
PRODUCT_ID = int(os.environ.get("PRINTER_PRODUCT", "0x811e"), 16)
PRINTER_PROFILE = os.environ.get("PRINTER_PROFILE")
MEM_THRESHOLD_PERCENT = int(os.environ.get("MEM_THRESHOLD_PERCENT", "80"))
MEM_RESUME_PERCENT = int(os.environ.get("MEM_RESUME_PERCENT", "70"))
MAX_MESSAGE_LENGTH = int(os.environ.get("MAX_MESSAGE_LENGTH", "300"))
MAX_LINES = int(os.environ.get("MAX_LINES", "3"))
# Paper and printer geometry
PAPER_WIDTH_MM = float(os.environ.get("PAPER_WIDTH_MM", "80"))  # 80mm paper
PRINTER_DPI = int(os.environ.get("PRINTER_DPI", "203"))
X_OFFSET_MM = float(os.environ.get("X_OFFSET_MM", "0"))
Y_OFFSET_MM = float(os.environ.get("Y_OFFSET_MM", "0"))
# Max printable: 72mm on 80mm paper, 48mm on 58mm paper
SAFE_MARGIN_MM = 4.0  # (80mm - 72mm) / 2 = 4mm margin each side

# Calculate pixel dimensions (203 DPI)
# 80mm paper = 639px total, 72mm printable = 575px usable width
PAPER_WIDTH_PX = int(round(PAPER_WIDTH_MM / 25.4 * PRINTER_DPI))  # 639px for 80mm
SAFE_MARGIN_PX = int(round(SAFE_MARGIN_MM / 25.4 * PRINTER_DPI))  # 32px for 4mm
MAX_PRINTABLE_WIDTH_PX = PAPER_WIDTH_PX - (2 * SAFE_MARGIN_PX)    # 575px (72mm)

# Icon mappings (ASCII-friendly for thermal printer)
ICON_PRIORITY = {
    "critical": "[!!!]",
    "high": "[!!]",
    "medium": "[!]",
    "low": "[-]",
}

ICON_STATUS = {
    "done": "[OK]",
    "completed": "[OK]",
    "in_progress": "[WIP]",
    "wip": "[WIP]",
    "todo": "[TODO]",
    "blocked": "[BLOCKED]",
    "on_hold": "[HOLD]",
}

ICON_TYPE = {
    "task": "[T]",
    "bug": "[B]",
    "feature": "[F]",
    "alert": "[A]",
    "order": "[#]",
    "monday_task": "[M]",
}

# Common emoji to text mappings for thermal printer compatibility
EMOJI_MAP = {
    "🍕": "[pizza]",
    "🍔": "[burger]",
    "🍆": "[eggplant]",
    "☕": "[coffee]",
    "🎉": "[party]",
    "✅": "[check]",
    "❌": "[x]",
    "⚠️": "[warn]",
    "🔔": "[bell]",
    "📅": "[cal]",
    "⏰": "[clock]",
    "👍": "[+1]",
    "👎": "[-1]",
    "❤️": "[heart]",
    "🔥": "[fire]",
    "💡": "[idea]",
    "📧": "[mail]",
    "📱": "[phone]",
    "🚨": "[alert]",
    "✨": "[*]",
    "⚡": "[!]",
}

def strip_emojis(text):
    """Remove or replace emojis with ASCII alternatives for thermal printer."""
    # First try specific mappings
    for emoji, replacement in EMOJI_MAP.items():
        text = text.replace(emoji, replacement)
    
    # Remove any remaining emojis (Unicode ranges for common emoji blocks)
    # This regex covers most emoji ranges
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002702-\U000027B0"  # dingbats
        "\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U0001FA00-\U0001FA6F"  # extended symbols
        "]+", flags=re.UNICODE
    )
    text = emoji_pattern.sub('', text)
    return text

def detect_priority(message, payload=None):
    """Detect priority level from ntfy message payload.
    
    Supports:
    - ntfy numeric priority (1-5 scale)
    - Explicit priority field in JSON payload
    - Priority header values (min, low, default, high, max, urgent)
    
    Returns: ("max", "high", "default", "low", "min")
    """
    if not payload or not isinstance(payload, dict):
        return "default"
    
    # Check for numeric priority (ntfy uses 1-5 scale: 5=max, 4=high, 3=default, 2=low, 1=min)
    priority_value = payload.get("priority")
    if priority_value is not None:
        try:
            p = int(priority_value)
            if p >= 5:
                return "max"
            elif p >= 4:
                return "high"
            elif p >= 3:
                return "default"
            elif p >= 2:
                return "low"
            else:
                return "min"
        except (ValueError, TypeError):
            pass
    
    # Check for string priority values (e.g., from headers or explicit field)
    priority_str = payload.get("priority_str", payload.get("priority_level", "")).lower()
    if priority_str:
        if priority_str in ["5", "urgent", "critical", "max", "emergency"]:
            return "max"
        elif priority_str in ["4", "high"]:
            return "high"
        elif priority_str in ["3", "normal", "default", "medium"]:
            return "default"
        elif priority_str in ["2", "low"]:
            return "low"
        elif priority_str in ["1", "min", "minimal"]:
            return "min"
    
    return "default"


def get_priority_symbol(priority_level):
    """Get the alert symbol(s) and count for priority level.
    
    Returns: (symbol, count)
    """
    symbols = {
        "max": ("⚡", 3),      # ***
        "high": ("⚡", 2),     # **
        "default": ("⚡", 1),  # *
        "low": ("↓", 1),       # Single downward arrow
        "min": ("•", 1),       # Single bullet point
    }
    return symbols.get(priority_level, ("⚡", 1))

def draw_priority_banner(draw, x, y, width, height, priority, font, text_color=(0, 0, 0), bg_color=(200, 200, 200)):
    """Draw a priority banner with visual styling based on priority level.
    
    Args:
        draw: PIL ImageDraw object
        x, y: Top-left coordinates
        width, height: Banner dimensions
        priority: One of "critical", "high", "medium", "low"
        font: PIL Font for text
        text_color: RGB tuple for text
        bg_color: RGB tuple for background
    
    Returns: Text to display in banner
    """
    # Define visual styles per priority
    styles = {
        "critical": {
            "text": "⚠ CRITICAL ⚠",
            "fill": (255, 100, 100),  # Red
            "pattern": "heavy",  # Dense shading
        },
        "high": {
            "text": "● HIGH ●",
            "fill": (255, 180, 100),  # Orange
            "pattern": "medium",
        },
        "medium": {
            "text": "○ MEDIUM ○",
            "fill": (255, 255, 100),  # Yellow
            "pattern": "light",
        },
        "low": {
            "text": "- LOW -",
            "fill": (200, 255, 200),  # Light green
            "pattern": "minimal",
        },
    }
    
    style = styles.get(priority.lower(), styles["medium"])
    fill = style["fill"]
    banner_text = style["text"]
    pattern = style["pattern"]
    
    # Draw background rectangle with border
    border_width = 2
    draw.rectangle([x, y, x + width - 1, y + height - 1], fill=fill, outline=(0, 0, 0), width=border_width)
    
    # Add pattern/shading based on priority (thicker line = higher priority)
    if pattern == "heavy":
        # Dense lines for critical
        for line_y in range(y + 5, y + height - 5, 2):
            draw.line([x + 5, line_y, x + width - 5, line_y], fill=(100, 0, 0), width=1)
    elif pattern == "medium":
        # Medium spacing for high
        for line_y in range(y + 5, y + height - 5, 3):
            draw.line([x + 5, line_y, x + width - 5, line_y], fill=(150, 80, 0), width=1)
    elif pattern == "light":
        # Light spacing for medium
        for line_y in range(y + 5, y + height - 5, 5):
            draw.line([x + 5, line_y, x + width - 5, line_y], fill=(150, 150, 0), width=1)
    
    # Draw text centered in banner
    text_bbox = draw.textbbox((0, 0), banner_text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    text_x = x + (width - text_width) // 2
    text_y = y + (height - text_height) // 2
    draw.text((text_x, text_y), banner_text, font=font, fill=(0, 0, 0))
    
    return banner_text

# Image processing controls for printer compatibility
IMAGE_IMPL = os.environ.get("IMAGE_IMPL", "bitImageColumn")
IMAGE_IMPLS = os.environ.get("IMAGE_IMPLS")
IMAGE_SCALE = int(os.environ.get("IMAGE_SCALE", "2"))
IMAGE_CONTRAST = float(os.environ.get("IMAGE_CONTRAST", "2.0"))
# global stop event used to exit loops cleanly
STOP_EVENT = threading.Event()
MONITOR = None

class WhiteboardPrinter:
    def __init__(self, preview_mode=False):
        self.p = None
        self._paused = False
        self.preview_mode = preview_mode
        self.preview_count = 0
        if not preview_mode:
            self.connect()

    def set_paused(self, paused: bool):
        self._paused = bool(paused)

    @property
    def is_paused(self):
        return self._paused

    def connect(self):
        if self.preview_mode:
            print("📸 Preview mode - no printer connection needed")
            return
        
        try:
            if PRINTER_PROFILE:
                self.p = Usb(VENDOR_ID, PRODUCT_ID, 0, profile=PRINTER_PROFILE)
            else:
                self.p = Usb(VENDOR_ID, PRODUCT_ID, 0)
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

    def create_layout(self, message, subtext=None, priority="default"):
        # Compute width from paper size and printer DPI, with safe margins
        full_width = int(round(PAPER_WIDTH_MM / 25.4 * PRINTER_DPI))
        safe_margin_px = int(round(SAFE_MARGIN_MM / 25.4 * PRINTER_DPI))
        width = full_width - (2 * safe_margin_px)  # Subtract margins from usable width
        x_offset_px = int(round(X_OFFSET_MM / 25.4 * PRINTER_DPI))
        y_offset_px = int(round(Y_OFFSET_MM / 25.4 * PRINTER_DPI))
        left_margin = safe_margin_px + x_offset_px  # Left edge accounting for offset

        # MASSIVE font sizes
        font_main_size = 70
        font_sub_size = 35
        font_subtext_size = 24

        try:
            font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_main_size)
            font_reg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_sub_size)
            font_subtext = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_subtext_size)
        except Exception:
            logging.warning("Could not load TTF fonts; falling back to default font")
            font_bold = font_reg = font_subtext = ImageFont.load_default()

        # 2. Main Message (Heavy Wrap for Size)
        # enforce message caps to avoid unbounded image sizes
        if len(message) > MAX_MESSAGE_LENGTH:
            message = message[:MAX_MESSAGE_LENGTH-3] + "..."

        wrapped = textwrap.wrap(message, width=10)
        lines = wrapped[:MAX_LINES]  # 10 chars max keeps it huge
        if len(wrapped) > MAX_LINES and lines:
            lines[-1] = (lines[-1][:max(0, len(lines[-1]) - 3)] + "...")

        # Measure text sizes to build a tight canvas
        sample_main_bbox = font_bold.getbbox("Ag")
        main_line_height = sample_main_bbox[3] - sample_main_bbox[1]
        sample_sub_bbox = font_reg.getbbox("Ag")
        sub_line_height = sample_sub_bbox[3] - sample_sub_bbox[1]
        sample_subtext_bbox = font_subtext.getbbox("Ag")
        subtext_line_height = sample_subtext_bbox[3] - sample_subtext_bbox[1]

        top_pad = 20
        bolt_gap = 15
        line_gap = 10
        divider_gap = 15
        date_gap = 25
        subtext_gap = 10
        bottom_pad = 20
        
        # Get priority-based alert symbol and count
        symbol, count = get_priority_symbol(priority)
        alert_symbol = symbol * count  # Repeat symbol based on priority
        alert_symbol = strip_emojis(alert_symbol)

        lines_height = (len(lines) * main_line_height) + (max(0, len(lines) - 1) * line_gap)
        bolt_bbox = font_bold.getbbox(alert_symbol)
        bolt_height = bolt_bbox[3] - bolt_bbox[1]
        
        # Calculate subtext height if provided
        subtext_height = 0
        if subtext:
            subtext_height = subtext_line_height + subtext_gap
        
        total_height = (
            top_pad +
            bolt_height + bolt_gap +
            lines_height +
            subtext_height +
            divider_gap + 3 + date_gap +
            sub_line_height + 5 +  # date
            sub_line_height +  # time
            bottom_pad
        )

        canvas = Image.new('RGB', (full_width, total_height), color=(255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        y = top_pad + y_offset_px
        # 1. Lightning Bolt Symbol (Centered)
        bolt_x = (width - (bolt_bbox[2] - bolt_bbox[0])) // 2
        draw.text((bolt_x + left_margin, y), alert_symbol, font=font_bold, fill=(0, 0, 0))
        y += bolt_height + bolt_gap

        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font_bold)
            draw.text(((width - (bbox[2]-bbox[0]))//2 + left_margin, y), line, font=font_bold, fill=(0, 0, 0))
            y += main_line_height + line_gap

        # 3. Optional subtext (smaller, gray)
        if subtext:
            subtext_bbox = draw.textbbox((0, 0), subtext, font=font_subtext)
            draw.text(((width - (subtext_bbox[2]-subtext_bbox[0]))//2 + left_margin, y), subtext, font=font_subtext, fill=(80, 80, 80))
            y += subtext_line_height + subtext_gap

        # 4. Divider line
        y += divider_gap
        draw.line([left_margin + 20, y, left_margin + width - 20, y], fill=(0, 0, 0), width=3)
        y += date_gap

        # 5. Date Sub-header
        date_str = time.strftime("%b %d, %Y")
        time_str = time.strftime("%H:%M:%S")
        bbox = draw.textbbox((0, 0), date_str, font=font_reg)
        draw.text(((width - (bbox[2]-bbox[0]))//2 + left_margin, y), date_str, font=font_reg, fill=(0, 0, 0))
        y += sub_line_height + 5
        bbox_time = draw.textbbox((0, 0), time_str, font=font_reg)
        draw.text(((width - (bbox_time[2]-bbox_time[0]))//2 + left_margin, y), time_str, font=font_reg, fill=(0, 0, 0))
        y += sub_line_height + bottom_pad

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
            # Generic fallback
            return self.create_layout(json.dumps(payload))
    
    def _render_monday_task(self, payload):
        """Kanban card style layout (monochrome) with borders and priority indicator."""
        full_width = int(round(PAPER_WIDTH_MM / 25.4 * PRINTER_DPI))
        safe_margin_px = int(round(SAFE_MARGIN_MM / 25.4 * PRINTER_DPI))
        x_offset_px = int(round(X_OFFSET_MM / 25.4 * PRINTER_DPI))
        y_offset_px = int(round(Y_OFFSET_MM / 25.4 * PRINTER_DPI))
        left_margin = safe_margin_px + x_offset_px
        
        try:
            font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
            font_meta = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
        except Exception:
            font_title = font_meta = font_small = ImageFont.load_default()
        
        # Extract fields
        task_name = payload.get("task", "Task").strip()[:50]
        priority = payload.get("priority", "medium").lower()
        status = payload.get("status", "todo").lower()
        assignee = payload.get("assignee", "").upper()[:3]
        due_date = payload.get("due_date", "")[:10]
        ref_id = payload.get("id", payload.get("ref_id", ""))
        qr_data = payload.get("qr_url") or payload.get("url")
        
        # Priority indicator width (monochrome: thicker = higher priority)
        priority_widths = {
            "critical": 8,
            "high": 6,
            "medium": 4,
            "low": 2,
        }
        priority_width = priority_widths.get(priority, 3)
        
        # Calculate dimensions with safe margins
        qr_size = 80 if qr_data else 0
        card_height = 220 + qr_size
        card_width = full_width - (2 * safe_margin_px)
        padding = 15
        card_x = left_margin
        card_y = 10 + y_offset_px
        
        canvas = Image.new('RGB', (full_width, card_height), color=(255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        
        # Card border/frame (black)
        draw.rectangle(
            [card_x, card_y, card_x + card_width, card_y + card_height - 15],
            outline=(0, 0, 0),
            width=2
        )
        
        # Priority indicator bar (left side, varying thickness based on priority)
        draw.rectangle(
            [card_x, card_y, card_x + priority_width, card_y + card_height - 15],
            fill=(0, 0, 0),
            outline=(0, 0, 0)
        )
        
        # Content area
        y = card_y + padding
        content_x = card_x + padding + 5 + 5
        
        # Task title (wrapped, bold)
        lines = textwrap.wrap(task_name, width=18)
        for line in lines[:2]:
            draw.text((content_x, y), line, font=font_title, fill=(0, 0, 0))
            y += 32
        
        y += 8
        
        # Status badge / icon
        status_icon = ICON_STATUS.get(status, "[?]")
        priority_icon = ICON_PRIORITY.get(priority, "[!]")
        draw.text((content_x, y), f"{status_icon} {priority_icon}", font=font_meta, fill=(0, 0, 0))
        y += 24
        
        # Metadata row: assignee and due date
        meta_parts = []
        if assignee:
            meta_parts.append(f"@{assignee}")
        if due_date:
            meta_parts.append(f"{due_date}")
        
        if meta_parts:
            meta_text = "  |  ".join(meta_parts)
            draw.text((content_x, y), meta_text, font=font_small, fill=(0, 0, 0))
            y += 20
        
        # Reference ID
        if ref_id:
            draw.text((content_x, y), f"#{ref_id}", font=font_small, fill=(0, 0, 0))
            y += 18
        
        # QR code (bottom right corner of card)
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
        full_width = int(round(PAPER_WIDTH_MM / 25.4 * PRINTER_DPI))
        safe_margin_px = int(round(SAFE_MARGIN_MM / 25.4 * PRINTER_DPI))
        x_offset_px = int(round(X_OFFSET_MM / 25.4 * PRINTER_DPI))
        y_offset_px = int(round(Y_OFFSET_MM / 25.4 * PRINTER_DPI))
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
        
        # Calculate total height
        total_height = banner_height + padding + padding
        if subtext:
            subtext_bbox = ImageFont.load_default().getbbox("Ag")
            subtext_height = (subtext_bbox[3] - subtext_bbox[1]) + padding
            total_height += subtext_height
        
        canvas = Image.new('RGB', (full_width, total_height), color=(255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        
        # Draw priority banner
        banner_x = left_margin
        banner_y = padding + y_offset_px
        draw_priority_banner(draw, banner_x, banner_y, width, banner_height, priority, font_banner)
        
        # Draw subtext if provided
        if subtext:
            subtext_y = banner_y + banner_height + padding
            subtext_bbox = draw.textbbox((0, 0), subtext, font=font_subtext)
            subtext_x = left_margin + (width - (subtext_bbox[2] - subtext_bbox[0])) // 2
            draw.text((subtext_x, subtext_y), strip_emojis(subtext), font=font_subtext, fill=(80, 80, 80))
        
        return canvas

    def create_alignment_test(self):
        # Build a simple alignment test using the same layout as regular messages
        width = int(round(PAPER_WIDTH_MM / 25.4 * PRINTER_DPI))
        height = int(round(width * 1.2))
        x_offset_px = int(round(X_OFFSET_MM / 25.4 * PRINTER_DPI))

        canvas = Image.new('RGB', (width, height), color=(255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        # Border
        draw.rectangle([0, 0, width - 1, height - 1], outline=(0, 0, 0), width=2)

        # Center line (vertical) - apply offset
        cx = width // 2 + x_offset_px
        draw.line([cx, 0, cx, height], fill=(0, 0, 0), width=3)

        # Tick marks every 10 mm
        mm_to_px = PRINTER_DPI / 25.4
        for mm in range(0, int(PAPER_WIDTH_MM) + 1, 10):
            x = int(round(mm * mm_to_px)) + x_offset_px
            draw.line([x, 0, x, 15], fill=(0, 0, 0), width=1)
            draw.line([x, height - 15, x, height], fill=(0, 0, 0), width=1)

        # Simple text label
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        except Exception:
            font = ImageFont.load_default()
        
        label1 = f"X_OFFSET_MM={X_OFFSET_MM}"
        label2 = f"Center at {PAPER_WIDTH_MM/2}mm"
        bbox1 = draw.textbbox((0, 0), label1, font=font)
        bbox2 = draw.textbbox((0, 0), label2, font=font)
        draw.text(((width - (bbox1[2]-bbox1[0]))//2, height//2 - 30), label1, font=font, fill=(0, 0, 0))
        draw.text(((width - (bbox2[2]-bbox2[0]))//2, height//2 + 10), label2, font=font, fill=(0, 0, 0))

        return canvas

    def print_msg(self, message, subtext=None, payload=None):
        if self.is_paused:
            logging.warning("Printer paused due to high memory — dropping message")
            return
        if not self.p:
            self.connect()
        
        # Detect if message is JSON (structured payload)
        try:
            msg_payload = json.loads(message)
            if isinstance(msg_payload, dict) and "type" in msg_payload:
                # Structured payload — use template (filter emojis from task names)
                if "task" in msg_payload:
                    msg_payload["task"] = strip_emojis(msg_payload["task"])
                img = self.render_structured(msg_payload)
            else:
                # Fallback to plain text layout with optional subtext
                # Detect priority from payload (ntfy priority data)
                priority = detect_priority(message, payload or msg_payload)
                img = self.create_layout(strip_emojis(message), subtext=subtext, priority=priority)
        except (json.JSONDecodeError, ValueError):
            # Plain text message - strip emojis, with optional subtext
            # Detect priority from ntfy payload (if provided)
            priority = detect_priority(message, payload)
            img = self.create_layout(strip_emojis(message), subtext=subtext, priority=priority)
        
        # Preview mode - show image instead of printing
        if self.preview_mode:
            scale = max(1, IMAGE_SCALE)
            scaled_width = img.width * scale
            scaled_height = img.height * scale
            img_scaled = img.resize((scaled_width, scaled_height), Image.NEAREST)
            img_mono = img_scaled.convert("L")
            img_mono = ImageOps.autocontrast(img_mono)
            img_mono = ImageEnhance.Contrast(img_mono).enhance(IMAGE_CONTRAST)
            img_final = img_mono.convert("1")
            
            self.preview_count += 1
            timestamp = time.strftime("%H:%M:%S")
            print(f"\n[{timestamp}] Preview #{self.preview_count}: {message[:60]}{'...' if len(message) > 60 else ''}")
            print(f"   Resolution: {img_final.width}x{img_final.height}px")
            print(f"   Paper: {PAPER_WIDTH_MM}mm ({PAPER_WIDTH_PX}px @ {PRINTER_DPI} DPI)")
            print(f"   Printable: {PAPER_WIDTH_MM - 2*SAFE_MARGIN_MM}mm ({MAX_PRINTABLE_WIDTH_PX}px)")
            img_final.show()
            return
        
        # Retry logic for USB operations (handles transient device errors)
        max_retries = 3
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                if not self.p:
                    # No printer available; log and skip printing instead of crashing
                    logging.warning("No printer connected — skipping print: %s", message)
                    return
                self.p.hw("INIT")
                # Scale and convert to printer-friendly monochrome image
                scale = max(1, IMAGE_SCALE)
                scaled_width = img.width * scale
                scaled_height = img.height * scale
                img_scaled = img.resize((scaled_width, scaled_height), Image.NEAREST)
                img_mono = img_scaled.convert("L")
                img_mono = ImageOps.autocontrast(img_mono)
                img_mono = ImageEnhance.Contrast(img_mono).enhance(IMAGE_CONTRAST)
                img_mono = img_mono.convert("1")
                # Select implementation list
                if IMAGE_IMPLS:
                    impls = [i.strip() for i in IMAGE_IMPLS.split(',') if i.strip()]
                else:
                    impls = [IMAGE_IMPL]

                printed = False
                for impl in impls:
                    try:
                        self.p.image(img_mono, impl=impl)
                        printed = True
                        break
                    except TypeError:
                        # Fallback for older escpos versions
                        self.p.image(img_mono)
                        printed = True
                        break
                    except Exception:
                        logging.exception("Image print failed with impl=%s", impl)

                if not printed:
                    logging.error("All image implementations failed. Try IMAGE_IMPLS=bitImageColumn,bitImageRaster,graphics,raster or set PRINTER_PROFILE.")
                self.p.text("\n\n\n\n")
                self.p.cut()
                print(f"✅ Printed: {message[:50]}")
                break  # Success - exit retry loop
            except Exception as e:
                # Check if it's a USB error that might be transient
                is_usb_error = "USBError" in str(type(e).__name__) or "Entity not found" in str(e) or "No such device" in str(e)
                
                if is_usb_error and attempt < max_retries - 1:
                    logging.warning("USB error on attempt %d/%d: %s - retrying after %.1fs", attempt + 1, max_retries, e, retry_delay)
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    # Try reconnecting
                    self.connect()
                    continue
                else:
                    logging.exception("Printing error (attempt %d/%d)", attempt + 1, max_retries)
                    # Final attempt failed - reconnect for next message
                    self.connect()
                    break
        
        # Cleanup images after all retry attempts
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

def listen(ntfy_url, preview_mode=False):
    global MONITOR
    wp = WhiteboardPrinter(preview_mode=preview_mode)
    
    mode_str = "preview mode" if preview_mode else "printer mode"
    print(f"👀 Listening to {ntfy_url} ({mode_str})")
    if preview_mode:
        print(f"📸 Previews will open automatically for each message")
    print(f"   Press Ctrl+C to stop\n")
    
    logging.info("Listening to %s", ntfy_url)
    # Start memory monitor (skip in preview mode)
    if not preview_mode:
        MONITOR = MemoryMonitor(wp)
        MONITOR.start()
    while not STOP_EVENT.is_set():
        try:
            # use context manager to ensure response is closed
            with requests.get(ntfy_url, stream=True, timeout=None) as r:
                r.raise_for_status()
                for line in r.iter_lines(decode_unicode=True):
                    if STOP_EVENT.is_set():
                        break
                    if line:
                        try:
                            payload = json.loads(line)
                        except Exception:
                            logging.warning("Received non-json line: %s", line)
                            continue
                        msg = payload.get("message", "")
                        if msg:
                            # enforce a local truncation/caps before printing
                            if len(msg) > MAX_MESSAGE_LENGTH:
                                msg = msg[:MAX_MESSAGE_LENGTH-3] + "..."
                            # Extract priority from ntfy payload (numeric 1-5 scale)
                            wp.print_msg(msg, payload=payload)
        except Exception:
            if STOP_EVENT.is_set():
                break
            logging.exception("Connection to ntfy failed — retrying in 5s")
            time.sleep(5)
    # stop monitor on exit
    try:
        if MONITOR:
            MONITOR.stop()
            MONITOR.join(timeout=2.0)
    except Exception:
        logging.debug("Error stopping monitor")


class MemoryMonitor(threading.Thread):
    """Background thread checking memory usage and pausing printing when high.

    If memory usage rises above MEM_THRESHOLD_PERCENT, printing is paused until
    usage drops below MEM_RESUME_PERCENT.
    """
    def __init__(self, printer: WhiteboardPrinter, interval: float = 5.0):
        super().__init__(daemon=True)
        self.printer = printer
        self.interval = interval
        self._stop_event = threading.Event()

    def run(self):
        while not self._stop_event.is_set():
            try:
                used_percent = self._get_mem_percent()
                if used_percent is None:
                    # Unable to determine memory usage; skip
                    time.sleep(self.interval)
                    continue
                if used_percent >= MEM_THRESHOLD_PERCENT and not self.printer.is_paused:
                    logging.warning("Memory usage high (%.1f%%) — pausing printer", used_percent)
                    self.printer.set_paused(True)
                elif used_percent <= MEM_RESUME_PERCENT and self.printer.is_paused:
                    logging.info("Memory usage normal (%.1f%%) — resuming printer", used_percent)
                    self.printer.set_paused(False)
            except Exception:
                logging.exception("Memory monitor error")
            time.sleep(self.interval)

    def stop(self):
        self._stop_event.set()

    def _get_mem_percent(self):
        try:
            if psutil:
                return psutil.virtual_memory().percent
            # fallback: read /proc/meminfo
            with open('/proc/meminfo', 'r') as f:
                info = f.read()
            mem_total = None
            mem_available = None
            for line in info.splitlines():
                if line.startswith('MemTotal:'):
                    mem_total = int(line.split()[1])
                elif line.startswith('MemAvailable:'):
                    mem_available = int(line.split()[1])
            if mem_total and mem_available:
                used = mem_total - mem_available
                return used / mem_total * 100.0
        except Exception:
            logging.exception("Failed to read memory usage")
        return None


def shutdown(signum, frame):
    logging.info("Shutting down (signal %s)", signum)
    # signal listen loop and monitor to stop
    try:
        STOP_EVENT.set()
        if MONITOR:
            MONITOR.stop()
            MONITOR.join(timeout=2.0)
    except Exception:
        logging.debug("Error during shutdown cleanup")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Receipt printer listening to an ntfy topic")
    parser.add_argument("--host", default=DEFAULT_NTFY_HOST, help="ntfy host (including scheme)")
    parser.add_argument("--topic", default=DEFAULT_NTFY_TOPIC, help="ntfy topic name")
    parser.add_argument("--test-align", action="store_true", help="print alignment test and exit")
    parser.add_argument("--preview", "-p", action="store_true", help="preview mode - show images instead of printing")
    parser.add_argument("--example", "-e", choices=["text", "kanban"], help="show example message")
    args = parser.parse_args()
    
    # Example mode
    if args.example:
        if args.example == "text":
            message = "Lunch Time! 🍕🍔"
            print(f"Example plain text: {message}")
        elif args.example == "kanban":
            message = json.dumps({
                "type": "monday_task",
                "task": "Design Homepage",
                "priority": "high",
                "status": "in_progress",
                "assignee": "JD",
                "due_date": "2026-02-15",
                "id": "M123",
                "qr_url": "https://monday.com/boards/123"
            })
            print(f"Example kanban card:\n{message}")
        
        wp = WhiteboardPrinter(preview_mode=True)
        wp.print_msg(message)
        sys.exit(0)

    if args.test_align:
        wp = WhiteboardPrinter()
        img = wp.create_alignment_test()
        # use the same print pipeline for calibration
        wp.print_msg("ALIGNMENT TEST")
        try:
            # print test image directly
            img_mono = img.convert("L")
            img_mono = ImageOps.autocontrast(img_mono)
            img_mono = ImageEnhance.Contrast(img_mono).enhance(IMAGE_CONTRAST)
            img_mono = img_mono.convert("1")
            if IMAGE_IMPLS:
                impls = [i.strip() for i in IMAGE_IMPLS.split(',') if i.strip()]
            else:
                impls = [IMAGE_IMPL]
            for impl in impls:
                try:
                    wp.p.image(img_mono, impl=impl)
                    break
                except TypeError:
                    wp.p.image(img_mono)
                    break
        finally:
            wp.p.text("\n\n\n\n")
            wp.p.cut()
        sys.exit(0)

    if not args.host or not args.topic:
        logging.error("NTFY host/topic not provided. Set NTFY_HOST and NTFY_TOPIC in environment or pass --host/--topic.")
        logging.error("Copy .env.template to .env and fill in NTFY_HOST/NTFY_TOPIC before running.")
        sys.exit(2)

    ntfy_url = f"{args.host.rstrip('/')}/{args.topic}/json"

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    listen(ntfy_url, preview_mode=args.preview)


if __name__ == "__main__":
    main()