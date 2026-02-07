"""Configuration module for ntfy receipt printer.

Loads environment variables and sets up printer geometry, memory limits, and UI settings.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- NTFY Configuration ---
DEFAULT_NTFY_HOST = os.environ.get("NTFY_HOST")
DEFAULT_NTFY_TOPIC = os.environ.get("NTFY_TOPIC")
ERROR_NTFY_TOPIC = os.environ.get("ERROR_NTFY_TOPIC")

# --- Phone Number QR Code Configuration ---
COUNTRY_CODE = os.environ.get("COUNTRY_CODE", "1")  # Default: US +1
PHONE_QR_ENABLED = os.environ.get("PHONE_QR_ENABLED", "true").lower() == "true"
PHONE_CALL_KEYWORDS = [k.strip().upper() for k in os.environ.get("PHONE_CALL_KEYWORDS", "call").split(",") if k.strip()]
PHONE_TEXT_KEYWORDS = [k.strip().upper() for k in os.environ.get("PHONE_TEXT_KEYWORDS", "text,message").split(",") if k.strip()]

# --- Logging Configuration ---
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.environ.get("LOG_FILE", "/var/log/receipt-printer.log")

# --- Auto-Update Configuration ---
AUTO_UPDATE = os.environ.get("AUTO_UPDATE", "false").lower() == "true"
UPDATE_CHECK_INTERVAL = int(os.environ.get("UPDATE_CHECK_INTERVAL", "3600"))  # seconds
GITHUB_REPO = os.environ.get("GITHUB_REPO", "VoidLock/RecieptPi")

# --- USB Printer Configuration ---
VENDOR_ID = int(os.environ.get("PRINTER_VENDOR", "0x0fe6"), 16)
PRODUCT_ID = int(os.environ.get("PRINTER_PRODUCT", "0x811e"), 16)
PRINTER_PROFILE = os.environ.get("PRINTER_PROFILE")

# --- Memory Monitoring ---
MEM_THRESHOLD_PERCENT = int(os.environ.get("MEM_THRESHOLD_PERCENT", "80"))
MEM_RESUME_PERCENT = int(os.environ.get("MEM_RESUME_PERCENT", "70"))

# --- Message Display ---
MAX_MESSAGE_LENGTH = int(os.environ.get("MAX_MESSAGE_LENGTH", "300"))
MAX_LINES = int(os.environ.get("MAX_LINES", "3"))

# --- Printer Geometry & DPI ---
PAPER_WIDTH_MM = float(os.environ.get("PAPER_WIDTH_MM", "80"))  # 80mm paper
PRINTER_DPI = int(os.environ.get("PRINTER_DPI", "203"))
X_OFFSET_MM = float(os.environ.get("X_OFFSET_MM", "0"))
Y_OFFSET_MM = float(os.environ.get("Y_OFFSET_MM", "0"))

# Maximum receipt height (optional - leave empty for unlimited)
MAX_HEIGHT_MM = float(os.environ.get("MAX_HEIGHT_MM", "0")) if os.environ.get("MAX_HEIGHT_MM") else None

# Safe print margins: 4mm on each side of 80mm paper = 72mm printable
SAFE_MARGIN_MM = 4.0

# Calculate pixel dimensions (203 DPI)
# 80mm paper = 639px total, 72mm printable = 575px usable width
PAPER_WIDTH_PX = int(round(PAPER_WIDTH_MM / 25.4 * PRINTER_DPI))      # 639px for 80mm
SAFE_MARGIN_PX = int(round(SAFE_MARGIN_MM / 25.4 * PRINTER_DPI))      # 32px for 4mm
MAX_PRINTABLE_WIDTH_PX = PAPER_WIDTH_PX - (2 * SAFE_MARGIN_PX)        # 575px (72mm)

# --- Image Processing ---
IMAGE_IMPL = os.environ.get("IMAGE_IMPL", "bitImageRaster")
IMAGE_IMPLS = os.environ.get("IMAGE_IMPLS", "")
IMAGE_SCALE = int(os.environ.get("IMAGE_SCALE", "2"))
IMAGE_CONTRAST = float(os.environ.get("IMAGE_CONTRAST", "2.0"))

# --- Icon Mappings (ASCII-friendly for thermal printer) ---
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
# (used for plain text messages that don't use pilmoji rendering)
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
}

# --- Text Processing ---
STOP_EVENT = None  # Set at runtime

def setup():
    """Initialize configuration. Call after imports."""
    global STOP_EVENT
    import threading
    STOP_EVENT = threading.Event()
