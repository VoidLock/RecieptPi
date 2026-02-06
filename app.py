#!/usr/bin/env python3
"""ntfy Receipt Printer - Service that prints ntfy.sh messages to a thermal receipt printer.

Subscribes to ntfy topics via HTTP SSE and renders messages to an ESC/POS USB printer.
Supports multiple message types: plain text, structured JSON (kanban tasks), priority alerts.

Usage:
    python app.py --host https://ntfy.example.com --topic my-topic
    python app.py --preview  (test without printer)
    python app.py --example text|kanban
    python app.py --test-align
"""

import logging
import signal
import sys
import argparse
import json

from ntfy_printer import config
from ntfy_printer.printer import WhiteboardPrinter
from ntfy_printer.listener import listen


def shutdown(signum, frame):
    """Handle SIGINT/SIGTERM gracefully."""
    logging.info("Shutdown signal received")
    config.STOP_EVENT.set()
    sys.exit(0)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Receipt printer listening to an ntfy topic")
    parser.add_argument("--host", default=config.DEFAULT_NTFY_HOST, help="ntfy host (including scheme)")
    parser.add_argument("--topic", default=config.DEFAULT_NTFY_TOPIC, help="ntfy topic name")
    parser.add_argument("--test-align", action="store_true", help="print alignment test and exit")
    parser.add_argument("--preview", "-p", action="store_true", help="preview mode - show images instead of printing")
    parser.add_argument("--example", "-e", choices=["text", "kanban"], help="show example message")
    args = parser.parse_args()
    
    # Initialize configuration
    config.setup()
    
    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
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
        wp.print_msg("ALIGNMENT TEST")
        try:
            img_mono = img.convert("L")
            from PIL import ImageOps, ImageEnhance
            img_mono = ImageOps.autocontrast(img_mono)
            img_mono = ImageEnhance.Contrast(img_mono).enhance(config.IMAGE_CONTRAST)
            img_mono = img_mono.convert("1")
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
            wp.p.text("\n\n\n\n")
            wp.p.cut()
        sys.exit(0)

    if not args.host or not args.topic:
        logging.error("NTFY host/topic not provided. Set NTFY_HOST and NTFY_TOPIC in environment or pass --host/--topic.")
        logging.error("Copy .env.template to .env and fill in NTFY_HOST/NTFY_TOPIC before running.")
        sys.exit(2)

    ntfy_url = f"{args.host.rstrip('/')}/{args.topic}/json"
    listen(ntfy_url, preview_mode=args.preview)


if __name__ == "__main__":
    main()
