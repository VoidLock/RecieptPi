#!/usr/bin/env python3
"""ntfy Receipt Printer - Service that prints ntfy.sh messages to a thermal receipt printer.

Subscribes to ntfy topics via HTTP SSE and renders messages to an ESC/POS USB printer.
Supports multiple message types: plain text, structured JSON (kanban tasks), priority alerts.

Usage:
    # Normal interactive mode (press 'Q' to exit)
    python app.py --host https://ntfy.example.com --topic my-topic
    
    # Server mode (for systemd service, file logging, auto-updates)
    python app.py --host https://ntfy.example.com --topic my-topic --server --log-level INFO
    
    # Testing modes
    python app.py --preview                    # test without printer
    python app.py --example text|kanban        # show example message
    python app.py --test-align                 # print alignment test
    python app.py --calibrate                  # print calibration grid

Environment Variables:
    NTFY_HOST, NTFY_TOPIC          - ntfy connection settings
    LOG_LEVEL                      - logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    LOG_FILE                       - log file path for server mode
    ERROR_NTFY_TOPIC               - optional ntfy URL to send error notifications
    AUTO_UPDATE                    - enable automatic git-based updates (true/false)
    UPDATE_CHECK_INTERVAL          - update check interval in seconds (default: 3600)
    GITHUB_REPO                    - GitHub repository (default: VoidLock/RecieptPi)
"""

import logging
import signal
import sys
import argparse
import json
import os
import threading
import time
import requests

from PIL import ImageOps, ImageEnhance
from ntfy_printer import config
from ntfy_printer.printer import WhiteboardPrinter
from ntfy_printer.listener import listen


# Global error handler for sending ntfy notifications
ERROR_NTFY_TOPIC = None


class ErrorNotifier:
    """Send error messages to an ntfy topic."""
    
    def __init__(self, ntfy_url):
        """Initialize with ntfy URL (e.g., https://ntfy.sh/my-errors)"""
        self.ntfy_url = ntfy_url
        self.enabled = ntfy_url is not None
    
    def send_error(self, title, message):
        """Send error notification to ntfy topic using native format."""
        if not self.enabled:
            return
        try:
            import socket
            hostname = socket.gethostname()
            # Use ntfy native format: POST with title and tags as headers
            headers = {
                "Title": f"Application Error on {hostname}",
                "Tags": "rotating_light,error",
                "Priority": "high"
            }
            requests.post(self.ntfy_url, data=message, headers=headers, timeout=5)
        except Exception as e:
            logging.error("Failed to send error notification: %s", e)


def setup_logging(log_level, server_mode=False, log_file=None):
    """Setup logging with configurable level and optional file output.
    
    Args:
        log_level (str): Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        server_mode (bool): If True, log to file for systemd service
        log_file (str): Path to log file (default: /var/log/receipt-printer.log)
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    logger = logging.getLogger()
    logger.setLevel(level)
    
    # Console handler (always enabled)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler for server mode
    if server_mode and log_file:
        try:
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            logging.info(f"Logging to file: {log_file}")
        except PermissionError:
            logging.error(f"Cannot write to log file {log_file} (permission denied)")
        except Exception as e:
            logging.error(f"Failed to setup file logging: {e}")


def input_listener():
    """Listen for 'Q' key press to gracefully shutdown."""
    try:
        while not config.STOP_EVENT.is_set():
            user_input = input().strip().upper()
            if user_input == "Q":
                logging.info("Quit command received (Q pressed)")
                config.STOP_EVENT.set()
                break
    except EOFError:
        # Input stream closed (normal when running in background)
        pass
    except KeyboardInterrupt:
        # Ctrl+C pressed
        pass
    except Exception as e:
        logging.debug(f"Input listener error: {e}")


def shutdown(signum, frame):
    """Handle SIGINT/SIGTERM gracefully."""
    logging.info("Shutdown signal received")
    config.STOP_EVENT.set()
    sys.exit(0)


def main():
    """Main entry point."""
    global ERROR_NTFY_TOPIC
    
    parser = argparse.ArgumentParser(description="Receipt printer listening to an ntfy topic")
    parser.add_argument("--host", default=config.DEFAULT_NTFY_HOST, help="ntfy host (including scheme)")
    parser.add_argument("--topic", default=config.DEFAULT_NTFY_TOPIC, help="ntfy topic name")
    parser.add_argument("--calibrate", action="store_true", help="print calibration grid to determine printable area")
    parser.add_argument("--test-align", action="store_true", help="print alignment test and exit")
    parser.add_argument("--preview", "-p", action="store_true", help="preview mode - show images instead of printing")
    parser.add_argument("--example", "-e", choices=["text", "kanban"], help="show example message")
    parser.add_argument("--server", action="store_true", help="server mode - run as systemd service with file logging")
    args = parser.parse_args()
    
    # Initialize configuration
    config.setup()
    
    # Setup logging
    setup_logging(config.LOG_LEVEL, server_mode=args.server, log_file=config.LOG_FILE)
    
    # Setup error ntfy topic if provided
    if config.ERROR_NTFY_TOPIC:
        ERROR_NTFY_TOPIC = config.ERROR_NTFY_TOPIC
        logging.info(f"Error notifications enabled: {ERROR_NTFY_TOPIC}")
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    # Example mode
    if args.example:
        message = None
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
        
        if message:
            wp = WhiteboardPrinter(preview_mode=True)
            wp.print_msg(message)
        sys.exit(0)
    
    if args.calibrate:
        print("\n" + "="*60)
        print("CALIBRATION MODE")
        print("="*60)
        print("\nThis will print a calibration grid.")
        print("\nInstructions:")
        print("1. Note the rightmost column letter you can see clearly")
        print("2. Check if text is centered or shifted")
        print("3. Update your .env file with these values:")
        print("\n   X_OFFSET_MM=<adjust left/right centering>")
        print("   SAFE_MARGIN_MM=<margin from paper edge>")
        print("   MAX_HEIGHT_MM=<optional max receipt height>")
        print("\nCurrent settings:")
        print(f"   PAPER_WIDTH_MM={config.PAPER_WIDTH_MM}")
        print(f"   X_OFFSET_MM={config.X_OFFSET_MM}")
        print(f"   SAFE_MARGIN_MM={config.SAFE_MARGIN_MM}")
        print(f"   MAX_HEIGHT_MM={config.MAX_HEIGHT_MM or 'unlimited'}")
        print("="*60 + "\n")
        
        wp = WhiteboardPrinter()
        
        # Retry calibration if device not ready
        max_retries = 3
        for attempt in range(max_retries):
            if not wp.is_ready():
                if attempt < max_retries - 1:
                    print(f"Printer not ready, retrying ({attempt + 2}/{max_retries})...")
                    time.sleep(1)
                    wp.connect()
                    continue
                else:
                    print("ERROR: Could not connect to printer. Please check USB connection and try again.")
                    sys.exit(1)
            
            # Device is ready, proceed with calibration
            img = wp.create_calibration_grid()
            
            try:
                img_mono = img.convert("L")
                img_mono = ImageOps.autocontrast(img_mono)
                img_mono = ImageEnhance.Contrast(img_mono).enhance(config.IMAGE_CONTRAST)
                img_mono = img_mono.convert("1")
                
                if wp.p:
                    if config.IMAGE_IMPLS:
                        impls = [i.strip() for i in config.IMAGE_IMPLS.split(',') if i.strip()]
                    else:
                        impls = [config.IMAGE_IMPL]
                    
                    for impl in impls:
                        try:
                            wp.p.image(img_mono, impl=impl)
                            break
                        except TypeError:
                            wp.p.image(img_mono)
                            break
            except Exception as e:
                if attempt < max_retries - 1:
                    logging.warning(f"Calibration attempt {attempt + 1} failed: {e}, retrying...")
                    wp.p = None
                    continue
                else:
                    logging.error(f"Calibration failed after {max_retries} attempts: {e}")
                    raise
            finally:
                if wp.p and wp.is_ready():
                    try:
                        wp.p.text("\n\n\n\n")
                        wp.p.cut()
                    except Exception as e:
                        logging.warning(f"Could not send final cut command: {e}")
            
            break  # Success, exit retry loop
        
        print("\nCalibration grid printed!")
        print("\nBased on what you see:")
        print("- If center line is off, adjust X_OFFSET_MM (negative=left, positive=right)")
        print("- If right edge is cut off, increase SAFE_MARGIN_MM")
        print("- To limit receipt length, set MAX_HEIGHT_MM in .env")
        print("\n")
        sys.exit(0)

    if args.test_align:
        wp = WhiteboardPrinter()
        img = wp.create_alignment_test()
        wp.print_msg("ALIGNMENT TEST")
        try:
            img_mono = img.convert("L")
            img_mono = ImageOps.autocontrast(img_mono)
            img_mono = ImageEnhance.Contrast(img_mono).enhance(config.IMAGE_CONTRAST)
            img_mono = img_mono.convert("1")
            if wp.p:
                if config.IMAGE_IMPLS:
                    impls = [i.strip() for i in config.IMAGE_IMPLS.split(',') if i.strip()]
                else:
                    impls = [config.IMAGE_IMPL]
                for impl in impls:
                    try:
                        wp.p.image(img_mono, impl=impl)
                        break
                    except TypeError:
                        wp.p.image(img_mono)
                        break
        finally:
            if wp.p:
                wp.p.text("\n\n\n\n")
                wp.p.cut()
        sys.exit(0)

    if not args.host or not args.topic:
        logging.error("NTFY host/topic not provided. Set NTFY_HOST and NTFY_TOPIC in environment or pass --host/--topic.")
        logging.error("Copy .env.template to .env and fill in NTFY_HOST/NTFY_TOPIC before running.")
        sys.exit(2)

    ntfy_url = f"{args.host.rstrip('/')}/{args.topic}/json"
    
    # Start input listener thread if not in server mode (allows 'Q' to quit)
    if not args.server:
        print(f"👀 Listening to {ntfy_url}")
        print(f"   Press 'Q' then Enter to stop, or Ctrl+C\n")
        input_thread = threading.Thread(target=input_listener, daemon=True)
        input_thread.start()
    
    try:
        listen(ntfy_url, preview_mode=args.preview, error_notifier=ERROR_NTFY_TOPIC, server_mode=args.server)
    except Exception as e:
        error_msg = f"Fatal error in listener: {str(e)}"
        logging.error(error_msg, exc_info=True)
        if ERROR_NTFY_TOPIC:
            notifier = ErrorNotifier(ERROR_NTFY_TOPIC)
            notifier.send_error("Receipt Printer Error", error_msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
