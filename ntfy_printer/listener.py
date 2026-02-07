"""ntfy stream listener and memory monitoring for receipt printer service."""

import logging
import time
import json
import threading
import requests

try:
    import psutil
except ImportError:
    psutil = None

from . import config
from .printer import WhiteboardPrinter
from .updater import UpdateChecker


# Global monitor and update checker instances
MONITOR = None
UPDATE_CHECKER = None


def _send_error_notification(ntfy_url, title, message):
    """Send error notification to ntfy topic using native format."""
    if not ntfy_url:
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
        requests.post(ntfy_url, data=message, headers=headers, timeout=5)
    except Exception as e:
        logging.error("Failed to send error notification: %s", e)


def listen(ntfy_url, preview_mode=False, error_notifier=None, server_mode=False):
    """Connect to ntfy stream and print incoming messages.
    
    Args:
        ntfy_url (str): Full ntfy SSE URL (e.g., https://ntfy.sh/mytopic/json)
        preview_mode (bool): If True, display images instead of printing
        error_notifier (str): ntfy URL for error notifications (optional)
        server_mode (bool): If True, running as systemd service
    """
    global MONITOR, UPDATE_CHECKER
    wp = WhiteboardPrinter(preview_mode=preview_mode)
    
    mode_str = "preview mode" if preview_mode else "printer mode"
    if not server_mode:
        print(f"👀 Listening to {ntfy_url} ({mode_str})")
        if preview_mode:
            print(f"📸 Previews will open automatically for each message")
        print(f"   Press 'Q' then Enter to stop, or Ctrl+C\n")
    
    logging.info("Listening to %s (%s)", ntfy_url, mode_str)
    if error_notifier:
        logging.info("Error notifications enabled to: %s", error_notifier)
    
    # Start memory monitor (skip in preview mode)
    if not preview_mode:
        MONITOR = MemoryMonitor(wp)
        MONITOR.start()
    
    # Start update checker
    if config.AUTO_UPDATE:
        UPDATE_CHECKER = UpdateChecker(
            server_mode=server_mode,
            error_notifier=error_notifier
        )
        UPDATE_CHECKER.start()
    
    while not config.STOP_EVENT.is_set():
        try:
            with requests.get(ntfy_url, stream=True, timeout=None) as r:
                r.raise_for_status()
                for line in r.iter_lines(decode_unicode=True):
                    if config.STOP_EVENT.is_set():
                        break
                    if line:
                        try:
                            payload = json.loads(line)
                        except Exception:
                            logging.warning("Received non-json line: %s", line)
                            continue
                        msg = payload.get("message", "")
                        if msg:
                            if len(msg) > config.MAX_MESSAGE_LENGTH:
                                msg = msg[:config.MAX_MESSAGE_LENGTH-3] + "..."
                            try:
                                wp.print_msg(msg, payload=payload)
                            except Exception as e:
                                logging.error("Error printing message: %s", e, exc_info=True)
                                if error_notifier:
                                    _send_error_notification(error_notifier, "Printer Error", f"Failed to print message: {str(e)}")
        except Exception as e:
            if config.STOP_EVENT.is_set():
                break
            logging.exception("Connection to ntfy failed — retrying in 5s")
            if error_notifier:
                _send_error_notification(error_notifier, "Connection Error", f"Failed to connect to ntfy: {str(e)}")
            time.sleep(5)
    
    # Stop monitor and update checker on exit
    try:
        if MONITOR:
            MONITOR.stop()
            MONITOR.join(timeout=2.0)
        if UPDATE_CHECKER:
            UPDATE_CHECKER.stop()
            UPDATE_CHECKER.join(timeout=2.0)
    except Exception:
        logging.debug("Error stopping background threads")


class MemoryMonitor(threading.Thread):
    """Background thread checking memory usage and pausing printing when high.

    If memory usage rises above MEM_THRESHOLD_PERCENT, printing is paused until
    usage drops below MEM_RESUME_PERCENT.
    
    Args:
        printer (WhiteboardPrinter): Printer instance to pause/resume
        interval (float): Check interval in seconds (default 5.0)
    """
    
    def __init__(self, printer: WhiteboardPrinter, interval: float = 5.0):
        super().__init__(daemon=True)
        self.printer = printer
        self.interval = interval
        self._stop_event = threading.Event()

    def run(self):
        """Monitor loop - runs until stop() is called."""
        while not self._stop_event.is_set():
            try:
                used_percent = self._get_mem_percent()
                if used_percent is None:
                    time.sleep(self.interval)
                    continue
                
                if used_percent >= config.MEM_THRESHOLD_PERCENT and not self.printer.is_paused:
                    logging.warning("Memory usage high (%.1f%%) — pausing printer", used_percent)
                    self.printer.set_paused(True)
                elif used_percent <= config.MEM_RESUME_PERCENT and self.printer.is_paused:
                    logging.info("Memory usage normal (%.1f%%) — resuming printer", used_percent)
                    self.printer.set_paused(False)
            except Exception:
                logging.exception("Memory monitor error")
            
            time.sleep(self.interval)

    def stop(self):
        """Stop the monitor thread."""
        self._stop_event.set()

    def _get_mem_percent(self):
        """Get system memory usage percentage.
        
        Returns:
            float: Memory usage percentage (0-100), or None if unavailable
        """
        try:
            if psutil:
                return psutil.virtual_memory().percent
            
            # Fallback: read /proc/meminfo
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
