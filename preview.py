#!/usr/bin/env python3
"""
Receipt Preview Tool - Test receipt rendering without a physical printer.

Usage:
    python3 preview.py "Your message here"
    python3 preview.py '{"type":"monday_task","task":"Fix Bug","priority":"high",...}'
    python3 preview.py --file output.png "Test message"
    python3 preview.py --watch  # Listen to ntfy and preview messages in real-time
"""

import sys
import os
import argparse
import json
import time
import textwrap
import re
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance
import qrcode

# Load .env file if it exists
def load_env():
    """Load environment variables from .env file."""
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key, value)

load_env()

# Import configuration from environment
PAPER_WIDTH_MM = float(os.environ.get("PAPER_WIDTH_MM", "80"))
PRINTER_DPI = int(os.environ.get("PRINTER_DPI", "203"))
X_OFFSET_MM = float(os.environ.get("X_OFFSET_MM", "0"))
Y_OFFSET_MM = float(os.environ.get("Y_OFFSET_MM", "0"))
SAFE_MARGIN_MM = 4.0
MAX_MESSAGE_LENGTH = int(os.environ.get("MAX_MESSAGE_LENGTH", "300"))
MAX_LINES = int(os.environ.get("MAX_LINES", "3"))
IMAGE_SCALE = int(os.environ.get("IMAGE_SCALE", "2"))
IMAGE_CONTRAST = float(os.environ.get("IMAGE_CONTRAST", "2.0"))

# ntfy configuration
NTFY_HOST = os.environ.get("NTFY_HOST")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")

# Icon mappings (copied from app.py)
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

# Common emoji to text mappings
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
    
    # Remove any remaining emojis
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


class PreviewPrinter:
    """Mock printer that renders images without hardware."""
    
    def create_layout(self, message):
        """Render plain text message layout (copied from app.py)."""
        # Compute width from paper size and printer DPI, with safe margins
        full_width = int(round(PAPER_WIDTH_MM / 25.4 * PRINTER_DPI))
        safe_margin_px = int(round(SAFE_MARGIN_MM / 25.4 * PRINTER_DPI))
        width = full_width - (2 * safe_margin_px)
        x_offset_px = int(round(X_OFFSET_MM / 25.4 * PRINTER_DPI))
        y_offset_px = int(round(Y_OFFSET_MM / 25.4 * PRINTER_DPI))
        left_margin = safe_margin_px + x_offset_px

        # MASSIVE font sizes
        font_main_size = 70
        font_sub_size = 35

        try:
            font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_main_size)
            font_reg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_sub_size)
        except Exception:
            font_bold = font_reg = ImageFont.load_default()

        # enforce message caps
        if len(message) > MAX_MESSAGE_LENGTH:
            message = message[:MAX_MESSAGE_LENGTH-3] + "..."

        wrapped = textwrap.wrap(message, width=10)
        lines = wrapped[:MAX_LINES]
        if len(wrapped) > MAX_LINES and lines:
            lines[-1] = (lines[-1][:max(0, len(lines[-1]) - 3)] + "...")

        # Measure text sizes
        sample_main_bbox = font_bold.getbbox("Ag")
        main_line_height = sample_main_bbox[3] - sample_main_bbox[1]
        sample_sub_bbox = font_reg.getbbox("Ag")
        sub_line_height = sample_sub_bbox[3] - sample_sub_bbox[1]
        bolt_bbox = font_bold.getbbox("🍆")
        bolt_height = bolt_bbox[3] - bolt_bbox[1]

        top_pad = 20
        bolt_gap = 15
        line_gap = 10
        divider_gap = 15
        date_gap = 25
        bottom_pad = 20

        lines_height = (len(lines) * main_line_height) + (max(0, len(lines) - 1) * line_gap)
        total_height = (
            top_pad +
            bolt_height + bolt_gap +
            lines_height +
            divider_gap + 3 + date_gap +
            sub_line_height + 5 +
            sub_line_height +
            bottom_pad
        )

        canvas = Image.new('RGB', (full_width, total_height), color=(255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        y = top_pad + y_offset_px
        # Lightning Bolt Symbol
        bolt_x = (width - (bolt_bbox[2] - bolt_bbox[0])) // 2
        draw.text((bolt_x + left_margin, y), "🍆", font=font_bold, fill=(0, 0, 0))
        y += bolt_height + bolt_gap

        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font_bold)
            draw.text(((width - (bbox[2]-bbox[0]))//2 + left_margin, y), line, font=font_bold, fill=(0, 0, 0))
            y += main_line_height + line_gap

        # Divider line
        y += divider_gap
        draw.line([left_margin + 20, y, left_margin + width - 20, y], fill=(0, 0, 0), width=3)
        y += date_gap

        # Date and time
        date_str = time.strftime("%b %d, %Y")
        time_str = time.strftime("%H:%M:%S")
        bbox = draw.textbbox((0, 0), date_str, font=font_reg)
        draw.text(((width - (bbox[2]-bbox[0]))//2 + left_margin, y), date_str, font=font_reg, fill=(0, 0, 0))
        y += sub_line_height + 5
        bbox_time = draw.textbbox((0, 0), time_str, font=font_reg)
        draw.text(((width - (bbox_time[2]-bbox_time[0]))//2 + left_margin, y), time_str, font=font_reg, fill=(0, 0, 0))

        return canvas

    def _render_monday_task(self, payload):
        """Render kanban card layout (copied from app.py)."""
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
        
        # Priority indicator width
        priority_widths = {
            "critical": 8,
            "high": 6,
            "medium": 4,
            "low": 2,
        }
        priority_width = priority_widths.get(priority, 3)
        
        # Calculate dimensions
        qr_size = 80 if qr_data else 0
        card_height = 220 + qr_size
        card_width = full_width - (2 * safe_margin_px)
        padding = 15
        card_x = left_margin
        card_y = 10 + y_offset_px
        
        canvas = Image.new('RGB', (full_width, card_height), color=(255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        
        # Card border
        draw.rectangle(
            [card_x, card_y, card_x + card_width, card_y + card_height - 15],
            outline=(0, 0, 0),
            width=2
        )
        
        # Priority indicator bar
        draw.rectangle(
            [card_x, card_y, card_x + priority_width, card_y + card_height - 15],
            fill=(0, 0, 0),
            outline=(0, 0, 0)
        )
        
        # Content area
        y = card_y + padding
        content_x = card_x + padding + 5
        
        # Task title
        lines = textwrap.wrap(task_name, width=18)
        for line in lines[:2]:
            draw.text((content_x, y), line, font=font_title, fill=(0, 0, 0))
            y += 32
        
        y += 8
        
        # Status/priority icons
        status_icon = ICON_STATUS.get(status, "[?]")
        priority_icon = ICON_PRIORITY.get(priority, "[!]")
        draw.text((content_x, y), f"{status_icon} {priority_icon}", font=font_meta, fill=(0, 0, 0))
        y += 24
        
        # Metadata
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
        
        # QR code
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
                print(f"Warning: QR generation failed: {e}")
        
        return canvas

    def render_structured(self, payload):
        """Render structured JSON payloads."""
        msg_type = payload.get("type", "generic")
        
        if msg_type == "monday_task":
            return self._render_monday_task(payload)
        else:
            return self.create_layout(json.dumps(payload))
    
    def preview_message(self, message, output_file=None, show=True):
        """Generate preview image from message."""
        # Detect if message is JSON
        try:
            payload = json.loads(message)
            if isinstance(payload, dict) and "type" in payload:
                if "task" in payload:
                    payload["task"] = strip_emojis(payload["task"])
                img = self.render_structured(payload)
            else:
                img = self.create_layout(strip_emojis(message))
        except (json.JSONDecodeError, ValueError):
            img = self.create_layout(strip_emojis(message))
        
        # Apply same processing as real printer
        scale = max(1, IMAGE_SCALE)
        scaled_width = img.width * scale
        scaled_height = img.height * scale
        img_scaled = img.resize((scaled_width, scaled_height), Image.NEAREST)
        img_mono = img_scaled.convert("L")
        img_mono = ImageOps.autocontrast(img_mono)
        img_mono = ImageEnhance.Contrast(img_mono).enhance(IMAGE_CONTRAST)
        img_final = img_mono.convert("1")
        
        # Save to file if requested
        if output_file:
            img_final.save(output_file)
            print(f"✅ Preview saved to: {output_file}")
        
        # Show in window if requested
        if show:
            print("📸 Opening preview window...")
            print(f"   Resolution: {img_final.width}x{img_final.height}px")
            print(f"   Paper width: {PAPER_WIDTH_MM}mm ({int(round(PAPER_WIDTH_MM / 25.4 * PRINTER_DPI))}px @ {PRINTER_DPI} DPI)")
            print(f"   Printable width: {PAPER_WIDTH_MM - 2*SAFE_MARGIN_MM}mm")
            img_final.show()
        
        return img_final


def watch_ntfy(ntfy_host, ntfy_topic, auto_save=False):
    """Listen to ntfy and preview messages in real-time."""
    if not ntfy_host or not ntfy_topic:
        print("❌ Error: NTFY_HOST and NTFY_TOPIC must be set in .env file")
        print("   Or set them as environment variables")
        sys.exit(1)
    
    ntfy_url = f"{ntfy_host}/{ntfy_topic}/json"
    printer = PreviewPrinter()
    count = 0
    
    print(f"👀 Watching ntfy stream: {ntfy_url}")
    print(f"📸 Previews will open automatically for each message")
    print(f"   Press Ctrl+C to stop\n")
    
    while True:
        try:
            with requests.get(ntfy_url, stream=True, timeout=60) as r:
                r.raise_for_status()
                for line in r.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        if event.get("event") != "message":
                            continue
                        
                        message = event.get("message", "")
                        if not message:
                            continue
                        
                        count += 1
                        timestamp = time.strftime("%H:%M:%S")
                        print(f"\n[{timestamp}] Message #{count}: {message[:60]}{'...' if len(message) > 60 else ''}")
                        
                        # Generate preview
                        output_file = f"preview_{count}.png" if auto_save else None
                        printer.preview_message(message, output_file=output_file, show=True)
                        
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        print(f"⚠️  Error processing message: {e}")
                        continue
        
        except KeyboardInterrupt:
            print(f"\n\n✅ Stopped watching. Previewed {count} messages.")
            break
        except requests.RequestException as e:
            print(f"⚠️  Connection error: {e}")
            print("   Retrying in 5 seconds...")
            time.sleep(5)
        except Exception as e:
            print(f"⚠️  Unexpected error: {e}")
            print("   Retrying in 5 seconds...")
            time.sleep(5)


def main():
    parser = argparse.ArgumentParser(description="Preview receipt output without printer")
    parser.add_argument("message", nargs='?', help="Message text or JSON payload")
    parser.add_argument("--file", "-f", help="Save preview to file (e.g., output.png)")
    parser.add_argument("--no-show", action="store_true", help="Don't open preview window")
    parser.add_argument("--example", "-e", choices=["text", "kanban"], help="Show example message")
    parser.add_argument("--watch", "-w", action="store_true", help="Watch ntfy stream and preview messages")
    parser.add_argument("--save", "-s", action="store_true", help="Save each preview when watching (preview_N.png)")
    
    args = parser.parse_args()
    
    # Watch mode
    if args.watch:
        watch_ntfy(NTFY_HOST, NTFY_TOPIC, auto_save=args.save)
        return
    
    # Handle examples
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
    elif args.message:
        message = args.message
    else:
        parser.print_help()
        return
    
    # Generate preview
    printer = PreviewPrinter()
    printer.preview_message(message, output_file=args.file, show=not args.no_show)


if __name__ == "__main__":
    main()
