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
PAPER_WIDTH_MM = float(os.environ.get("PAPER_WIDTH_MM", "79.375"))
PRINTER_DPI = int(os.environ.get("PRINTER_DPI", "203"))
X_OFFSET_MM = float(os.environ.get("X_OFFSET_MM", "0"))
Y_OFFSET_MM = float(os.environ.get("Y_OFFSET_MM", "0"))

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
# Image processing controls for printer compatibility
IMAGE_IMPL = os.environ.get("IMAGE_IMPL", "bitImageColumn")
IMAGE_IMPLS = os.environ.get("IMAGE_IMPLS")
IMAGE_SCALE = int(os.environ.get("IMAGE_SCALE", "2"))
IMAGE_CONTRAST = float(os.environ.get("IMAGE_CONTRAST", "2.0"))
# global stop event used to exit loops cleanly
STOP_EVENT = threading.Event()
MONITOR = None

class WhiteboardPrinter:
    def __init__(self):
        self.p = None
        self._paused = False
        self.connect()

    def set_paused(self, paused: bool):
        self._paused = bool(paused)

    @property
    def is_paused(self):
        return self._paused

    def connect(self):
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
            print("🟢 Hardware Linked")
        except Exception:
            logging.exception("Failed to connect to USB printer")
            self.p = None

    def create_layout(self, message):
        # Compute width from paper size and printer DPI
        width = int(round(PAPER_WIDTH_MM / 25.4 * PRINTER_DPI))
        x_offset_px = int(round(X_OFFSET_MM / 25.4 * PRINTER_DPI))
        y_offset_px = int(round(Y_OFFSET_MM / 25.4 * PRINTER_DPI))

        # MASSIVE font sizes
        font_main_size = 70
        font_sub_size = 35

        try:
            font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_main_size)
            font_reg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_sub_size)
        except Exception:
            logging.warning("Could not load TTF fonts; falling back to default font")
            font_bold = font_reg = ImageFont.load_default()

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
        bolt_bbox = font_bold.getbbox("⚡")
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
            sub_line_height + 5 +  # date
            sub_line_height +  # time
            bottom_pad
        )

        canvas = Image.new('RGB', (width, total_height), color=(255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        y = top_pad + y_offset_px
        # 1. Lightning Bolt Symbol (Centered)
        bolt_x = (width - (bolt_bbox[2] - bolt_bbox[0])) // 2
        draw.text((bolt_x + x_offset_px, y), "⚡", font=font_bold, fill=(0, 0, 0))
        y += bolt_height + bolt_gap

        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font_bold)
            draw.text(((width - (bbox[2]-bbox[0]))//2 + x_offset_px, y), line, font=font_bold, fill=(0, 0, 0))
            y += main_line_height + line_gap

        # 3. Divider line
        y += divider_gap
        draw.line([20 + x_offset_px, y, width-20 + x_offset_px, y], fill=(0, 0, 0), width=3)
        y += date_gap

        # 4. Date Sub-header
        date_str = time.strftime("%b %d, %Y")
        time_str = time.strftime("%H:%M:%S")
        bbox = draw.textbbox((0, 0), date_str, font=font_reg)
        draw.text(((width - (bbox[2]-bbox[0]))//2 + x_offset_px, y), date_str, font=font_reg, fill=(0, 0, 0))
        y += sub_line_height + 5
        bbox_time = draw.textbbox((0, 0), time_str, font=font_reg)
        draw.text(((width - (bbox_time[2]-bbox_time[0]))//2 + x_offset_px, y), time_str, font=font_reg, fill=(0, 0, 0))
        y += sub_line_height + bottom_pad

        return canvas

    def render_structured(self, payload):
        """Render structured JSON payloads (e.g., monday.com tasks)."""
        msg_type = payload.get("type", "generic")
        
        if msg_type == "monday_task":
            return self._render_monday_task(payload)
        else:
            # Generic fallback
            return self.create_layout(json.dumps(payload))
    
    def _render_monday_task(self, payload):
        """Kanban card style layout (monochrome) with borders and priority indicator."""
        width = int(round(PAPER_WIDTH_MM / 25.4 * PRINTER_DPI))
        x_offset_px = int(round(X_OFFSET_MM / 25.4 * PRINTER_DPI))
        y_offset_px = int(round(Y_OFFSET_MM / 25.4 * PRINTER_DPI))
        
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
        
        # Calculate dimensions
        qr_size = 80 if qr_data else 0
        card_height = 220 + qr_size
        card_width = width - 40
        padding = 15
        card_x = 20 + x_offset_px
        card_y = 10 + y_offset_px
        
        canvas = Image.new('RGB', (width, card_height), color=(255, 255, 255))
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
        content_x = card_x + padding + 5
        
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

    def print_msg(self, message):
        if self.is_paused:
            logging.warning("Printer paused due to high memory — dropping message")
            return
        if not self.p:
            self.connect()
        
        # Detect if message is JSON (structured payload)
        try:
            payload = json.loads(message)
            if isinstance(payload, dict) and "type" in payload:
                # Structured payload — use template
                img = self.render_structured(payload)
            else:
                # Fallback to plain text layout
                img = self.create_layout(message)
        except (json.JSONDecodeError, ValueError):
            # Plain text message
            img = self.create_layout(message)
        
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
        except Exception as e:
            logging.exception("Printing error")
            # attempt reconnect on any error
            self.connect()
        finally:
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

def listen(ntfy_url):
    global MONITOR
    wp = WhiteboardPrinter()
    logging.info("Listening to %s", ntfy_url)
    # Start memory monitor
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
                            wp.print_msg(msg)
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
    args = parser.parse_args()

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

    listen(ntfy_url)


if __name__ == "__main__":
    main()