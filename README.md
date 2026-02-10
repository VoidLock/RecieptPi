<h1>
  <img src="assets/logo.png" alt="ReceiptPi logo" width="96" style="vertical-align:middle; margin-right:12px;">
  ReceiptPi
</h1>

This project is a Python service that subscribes to the [ntfy.sh](https://ntfy.sh) *or selfhosted ntfy server* topic and prints received messages to a connected USB thermal receipt printer.

## Purpose

This service was designed for:
*   Creating a physical notification system.
*   Printing messages received from an ntfy topic.
*   Serving as a simple order ticket system.

## Features

* **Prints ntfy messages** to ESC/POS USB thermal printers
* **Auto-scaling messages** - content grows to fit the receipt, no truncation
* **Preview mode** (no printer required) with image output
* **Structured message support** (plain text, kanban cards, priority alerts)
* **Calibration tools** with readable grid for precise print placement
* **Phone Number QR Codes** - Auto-converts phone numbers to tel: or sms: schemes based on message keywords
* **Memory protection** with automatic pause/resume under high usage
* **Error notifications** to a separate ntfy topic with human-readable format
* **Auto-updates** via git with configurable polling interval
* **Configurable logging** with file output for server mode
* **Graceful shutdown** via `Q` (interactive) or system signals
* **USB connection retry logic** - automatically recovers from transient USB errors

### Resource Usage

*Note: The auto-update checker runs as a daemon thread and is idle most of the time.*

* **Memory:** <0.5 MB
* **CPU:** ~0.1% (1s active per hour)
* **Network:** <0.1 MB/day

## Development Hardware

The service was developed and tested on the following hardware:

*   **Board:** Orange Pi Zero 2W (4GB RAM)
*   **OS:** DietPi (minimal image)
*   **Printer:** Rongta RP850  [Amazon](https://a.co/d/0hIGPI9M)

## Prerequisites

Ensure the following are installed on your system:

```bash
# For Debian/Ubuntu-based systems (e.g., DietPi):
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git rsync
```

## Manual Execution (Temporary Run)

These steps describe how to run the service directly for testing or temporary use.

### 1. Clone the Repository

```bash
git clone https://github.com/VoidLock/ReceiptPi.git
cd ReceiptPi
```

### 2. Set Up Python Environment

Create and activate a Python virtual environment, then install required packages.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configuration

Configure the service parameters using an `.env` file.

*   **Create `.env`:**
    ```bash
    cp .env.template .env
    ```
*   **Edit `.env`:** Open the `.env` file and set the following variables:

**Required Settings:**
*   `NTFY_HOST`: The URL of your ntfy server (e.g., `https://ntfy.sh`).
*   `NTFY_TOPIC`: The ntfy topic to subscribe to **for messages to print**.
*   `PRINTER_VENDOR`: The USB Vendor ID of your thermal printer (hex format, e.g., `0x0fe6`).
*   `PRINTER_PRODUCT`: The USB Product ID of your thermal printer (hex format, e.g., `0x811e`).

    To find your printer's Vendor and Product IDs, use the `lsusb` command.

**Optional Settings:**
*   `PAPER_WIDTH_MM`: Paper width in millimeters (default: `80`)
*   `X_OFFSET_MM`: Horizontal offset in mm - negative shifts left, positive shifts right (default: `0`)
*   `Y_OFFSET_MM`: Vertical offset in mm (default: `0`)
*   `SAFE_MARGIN_MM`: Margin from paper edge in mm (default: `4.0`)
*   `MAX_HEIGHT_MM`: Maximum receipt height in mm, empty for unlimited
*   `COUNTRY_CODE`: Country code for phone QR codes (default: `1` for US)
*   `PHONE_QR_ENABLED`: Enable phone/SMS QR conversion (default: `true`)
*   `PHONE_CALL_KEYWORDS`: Keywords that trigger tel: scheme (default: `call`)
*   `PHONE_TEXT_KEYWORDS`: Keywords that trigger sms: scheme (default: `text,message`)
*   `LOG_LEVEL`: Logging verbosity - `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (default: `INFO`)
*   `LOG_FILE`: Log file path for server mode (default: `/var/log/receipt-printer.log`)
*   `ERROR_NTFY_TOPIC`: Separate ntfy topic for error notifications (e.g., `https://ntfy.sh/my-printer-errors`)
*   `AUTO_UPDATE`: Enable automatic git-based updates - `true` or `false` (default: `false`)
*   `UPDATE_CHECK_INTERVAL`: Seconds between update checks (default: `3600` = 1 hour)
*   `GITHUB_REPO`: GitHub repository for updates (default: `VoidLock/ReceiptPi`)
*   `PRINTER_PROFILE`: Optional printer profile for python-escpos (e.g., `TM-T20`, `RP80`). Leave empty for generic ESC/POS.
*   `MEM_THRESHOLD_PERCENT`: Memory usage threshold % to pause printing (default: `80`)
*   `MEM_RESUME_PERCENT`: Memory usage % to resume printing (default: `70`)
*   `MAX_MESSAGE_LENGTH`: Character limit for messages (default: `300`)
*   `IMAGE_IMPL`: Image implementation (default: `bitImageColumn`)
*   `IMAGE_IMPLS`: Comma-separated list of image implementations to try
*   `IMAGE_SCALE`: Image scaling factor (default: `2`)
*   `IMAGE_CONTRAST`: Image contrast enhancement (default: `2.0`)

**Example `.env` file:**
```bash
# Required - Messages TO print
NTFY_HOST=https://ntfy.sh
NTFY_TOPIC=my-receipt-printer

# Phone Number QR Codes (optional - converts phone numbers to tel: or sms: schemes)
COUNTRY_CODE=1                          # US: +1, UK: +44, etc.
PHONE_QR_ENABLED=true
PHONE_CALL_KEYWORDS=call                # Comma-separated keywords for tel: scheme
PHONE_TEXT_KEYWORDS=text,message        # Comma-separated keywords for sms: scheme

# Logging & Errors - Errors FROM the printer (separate topic!)
LOG_LEVEL=INFO
LOG_FILE=/var/log/receipt-printer.log
ERROR_NTFY_TOPIC=https://ntfy.sh/my-printer-errors

# Auto-Updates
AUTO_UPDATE=true
UPDATE_CHECK_INTERVAL=3600
GITHUB_REPO=VoidLock/ReceiptPi

# Printer
PRINTER_VENDOR=0x0fe6
PRINTER_PRODUCT=0x811e
```

### 4. Run the Service

Ensure your virtual environment is active.

```bash
# Interactive mode (press 'Q' then Enter to quit, or Ctrl+C)
python app.py

# Server mode (uses LOG_LEVEL and LOG_FILE from .env)
python app.py --server
```

Messages sent to the configured ntfy topic will now be printed. 

**Stopping the service:**
- **Interactive mode:** Press `Q` then `Enter`, or use `Ctrl+C`
- **Server mode:** Use `systemctl stop receipt-printer`

#### Command-Line Flags

The `app.py` script supports the following flags:

```bash
usage: app.py [-h] [--host HOST] [--topic TOPIC] [--calibrate] [--test-align]
              [--preview] [--example {text,kanban}] [--server]

Receipt printer listening to an ntfy topic

options:
  -h, --help            show this help message and exit
  --host HOST           ntfy host (including scheme)
  --topic TOPIC         ntfy topic name
  --calibrate           print calibration grid to determine printable area
  --test-align          print alignment test and exit
  --preview, -p         preview mode - show images instead of printing
  --example, -e {text,kanban}
                        show example message
  --server              server mode - run as systemd service with file logging
```

**Flag Details:**

**Connection:**
*   `--host <URL>`: Override NTFY_HOST from .env (e.g., `https://ntfy.example.com`)
*   `--topic <NAME>`: Override NTFY_TOPIC from .env

**Testing & Calibration:**
*   `--calibrate`: Print calibration grid with column letters (A-Z) and row numbers to verify print area
*   `--test-align`: Print alignment test and exit
*   `--preview`: Preview images in image viewer without printing (useful for testing)
*   `--example <TYPE>`: Print example message (`text` or `kanban`) and exit

**Service:**
*   `--server`: Run in server mode for systemd service (uses LOG_FILE and LOG_LEVEL from .env)

### Calibrating the Print Bounding Box

To optimize printing for your specific thermal printer and paper, use the built-in calibration feature:

1.  **Run Calibration:** With your printer connected and the virtual environment active, execute:
    ```bash
    python app.py --calibrate
    ```
2.  **Inspect Printout:** The printer outputs a calibration grid showing:
    *   Column letters (A-Z) at 10mm intervals to check the rightmost visible letter
    *   Row numbers (0mm-60mm) to verify vertical spacing
    *   CENTER line (red) indicating the paper center
    *   Current configuration settings at the bottom
3.  **Adjust `.env` Variables:** Based on your observations, modify:
    *   `X_OFFSET_MM`: Shifts content left (negative) or right (positive) for horizontal centering
    *   `SAFE_MARGIN_MM`: Margin from paper edge - increase if right edge content is cut off
    *   `MAX_HEIGHT_MM`: (Optional) Maximum receipt height in mm. Leave empty for unlimited.

    **Example adjustments:**
    ```bash
    X_OFFSET_MM=2
    SAFE_MARGIN_MM=5
    # MAX_HEIGHT_MM=150
    ```
    Repeat calibration until satisfied with alignment.

## Systemd Service Installation (Permanent Run)

To install the service to run automatically on system boot, use the provided installer script.

**Note:** This script requires `sudo` privileges.

```bash
chmod +x ./scripts/install_service
chmod +x ./scripts/uninstall_service

sudo ./scripts/install_service $(whoami)
```

This script performs the following actions:
1.  Copies the application to `/opt/ReceiptPi`.
2.  Moves or creates the `.env` file in `/opt/ReceiptPi/.env`.
3.  Creates a virtual environment in `/opt/ReceiptPi/venv` and installs dependencies.
4.  Copies a systemd service file to `/etc/systemd/system/`.
5.  Enables and starts the `receipt-printer` service.

Check the service status with:

```bash
systemctl status receipt-printer
```

View service logs:

```bash
# Real-time logs
journalctl -u receipt-printer -f

# Last 100 lines
journalctl -u receipt-printer -n 100
```

### Uninstall

To remove the service and application:

```bash
chmod +x ./scripts/uninstall_service
sudo ./scripts/uninstall_service
```

## Advanced Features

### Phone Number QR Codes

Automatically convert phone numbers in click URLs to callable or text-able QR codes based on message keywords.

**How it works:**
1. Include a numeric `click` field in your ntfy message (phone number)
2. Include a keyword in your message (CALL, TEXT, MESSAGE, etc.)
3. QR code automatically encodes the proper scheme

**Enable/Disable:**
Set `PHONE_QR_ENABLED=true` or `PHONE_QR_ENABLED=false` in `.env`

**Customize Keywords:**

In `.env`, configure which keywords trigger CALL vs TEXT:

```bash
# Keywords that trigger tel: scheme (phone call)
PHONE_CALL_KEYWORDS=call,dial,phone,reach

# Keywords that trigger sms: scheme (text message)
PHONE_TEXT_KEYWORDS=text,message,sms,contact
```

**Country Code:**

Set your country code for international numbers:
```bash
COUNTRY_CODE=1        # US: +1
COUNTRY_CODE=44       # UK: +44
COUNTRY_CODE=33       # France: +33
```

**Example:**

Send to ntfy with JSON payload:
```bash
curl -X POST https://ntfy.example.com/my-topic \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Support Available",
    "message": "CALL our support team: +1 555-0123",
    "click": "5550123"
  }'
```

Result:
- Message prints with "CALL" keyword detected
- QR code encodes: `tel:+15550123`
- Scanning the QR code initiates a phone call

Or for SMS:
```bash
curl -X POST https://ntfy.example.com/my-topic \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Quick Survey",
    "message": "TEXT your feedback: 555-4567",
    "click": "5554567"
  }'
```

Result:
- Message prints with "TEXT" keyword detected
- QR code encodes: `sms://5554567`
- Scanning opens SMS compose with pre-filled number

### Auto-Updates

The service can automatically check for and install updates from the GitHub repository.

**Requirements:**
- The application must be installed from a git clone (the install script preserves `.git` directory)
- `AUTO_UPDATE=true` in `.env`
- Running in server mode (systemd service)

**Enable auto-updates:**
1. Set `AUTO_UPDATE=true` in your `.env` file
2. Restart the service: `sudo systemctl restart receipt-printer`

The service will:
- Check GitHub every hour (configurable via `UPDATE_CHECK_INTERVAL`)
- Automatically pull latest changes via git
- Restart the service to apply updates
- Send error notifications if updates fail (requires `ERROR_NTFY_TOPIC`)

**Important:** If you see "not a git repository" errors, reinstall using the install script:
```bash
sudo ./scripts/uninstall_service
sudo ./scripts/install_service $(whoami)
```

**Manual update:**
```bash
cd /opt/ReceiptPi
git pull origin main
sudo systemctl restart receipt-printer
```

### Error Notifications

Set `ERROR_NTFY_TOPIC` in `.env` to receive error notifications sent **to a separate topic** from your main print topic.

**Error Format:**
- **Title:** "Application Error on {{hostname}}"
- **Tags:** 🚨 `rotating_light`, `error`
- **Priority:** high
- **Message:** Human-readable error details

**Important:** Use a different topic than `NTFY_TOPIC`:
- `NTFY_TOPIC` = Messages you send TO the printer (to print)
- `ERROR_NTFY_TOPIC` = Error messages FROM the printer (for monitoring)

**You'll receive notifications for:**
- Printer connection failures
- Print job failures
- ntfy connection errors
- Auto-update failures
- USB device disconnections

**Example:**
```bash
ERROR_NTFY_TOPIC=https://ntfy.sh/my-printer-errors
```

### Logging Levels

Control log verbosity with `LOG_LEVEL` in `.env`:
- `DEBUG`: Detailed diagnostic information
- `INFO`: General informational messages (default)
- `WARNING`: Warning messages for potential issues
- `ERROR`: Error messages for serious problems

Set log file location with `LOG_FILE` in `.env` (default: `/var/log/receipt-printer.log`).

In server mode (`--server` flag), logs are written to the configured log file.
## Troubleshooting

### USB Printer Connection Issues

**Problem:** "No such device (it may have been disconnected)" errors

**Solution:** The printer connection has automatic retry logic (3 attempts with 1-second delays). If this persists:
1. Unplug the printer and wait 5 seconds
2. Plug it back in
3. Run calibration again: `python app.py --calibrate`

### Auto-Update Not Working

**Problem:** "not a git repository" error in logs

**Solution:** Reinstall using the install script:
```bash
sudo ./scripts/uninstall_service
sudo ./scripts/install_service $(whoami)
```

The install script now preserves the `.git` directory needed for auto-updates.

### Printer Not Found

**Problem:** "Failed to connect to USB printer" on startup

**Solution:** 
1. Verify printer is connected: `lsusb | grep "0fe6"`
2. Get your printer's vendor/product IDs: `lsusb -v | grep -E "idVendor|idProduct"`
3. Update `PRINTER_VENDOR` and `PRINTER_PRODUCT` in `.env`
4. Optionally set `PRINTER_PROFILE` if your printer model is listed

### Images Printing Incorrectly

**Problem:** Images too large, scaled incorrectly, or poor quality

**Solution:** Adjust in `.env`:
```bash
# Try different image implementations
IMAGE_IMPLS=bitImageColumn,bitImageRaster,graphics,raster

# Reduce scaling if images are too large
IMAGE_SCALE=1

# Adjust contrast for better quality
IMAGE_CONTRAST=1.5
```

### Service Won't Start

**Problem:** `systemctl status receipt-printer` shows errors

**Solution:**
1. Check logs: `journalctl -u receipt-printer -n 50`
2. Verify .env exists: `cat /opt/ReceiptPi/.env`
3. Check permissions: `sudo chown -R $USER:$USER /opt/ReceiptPi`
4. Restart: `sudo systemctl restart receipt-printer`

## License

**ReceiptPi** is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

This means:
- ✅ **Free to use** - No cost, forever
- ✅ **Free to modify** - Source code is yours to customize
- ✅ **Free to distribute** - Share with others freely
- ✅ **Community benefits** - If you modify and use it, improvements must be shared back
- ❌ **Not for profit** - Cannot be sold or used commercially without sharing modifications

### Why AGPL-3.0?

We chose AGPL-3.0 to ensure:
1. ReceiptPi remains free and open forever
2. No one can lock improvements behind commercial walls
3. Community contributions benefit everyone
4. Network use (future service versions) requires source sharing

For the full legal text, see [LICENSE](LICENSE).

## Credits

ReceiptPi is built on excellent open-source projects. Special thanks to:

- **[python-escpos](https://github.com/python-escpos/python-escpos)** - ESC/POS thermal printer driver
- **[Pillow](https://github.com/python-pillow/Pillow)** - Image processing
- **[ntfy.sh](https://ntfy.sh)** - Notification infrastructure
- **[requests](https://github.com/psf/requests)** - HTTP library
- **[qrcode](https://github.com/lincolnloop/python-qrcode)** - QR code generation
- **[pilmoji](https://github.com/jay3332/pilmoji)** - Emoji rendering
- **[psutil](https://github.com/giampaolo/psutil)** - System monitoring
- **[pyusb](https://github.com/pyusb/pyusb)** - USB communication

See [CREDITS.md](CREDITS.md) for detailed dependency information.

## Contributing

We welcome contributions from the community! When you contribute:

1. **Your code stays free** - All contributions are AGPL-3.0 licensed
2. **Help everyone** - Your improvements benefit the entire community
3. **Get credit** - Contributors may be listed in [CREDITS.md](CREDITS.md)

To contribute:
```bash
# Fork the repository on GitHub
# Create a feature branch
git checkout -b feature/your-feature-name

# Make your changes and commit
git add .
git commit -m "Add your feature description"

# Push and create a Pull Request
git push origin feature/your-feature-name
```

**Code guidelines:**
- Follow PEP 8 Python style guide
- Add docstrings to functions
- Include error handling
- Test your changes before submitting

## Support

- **Issues:** [GitHub Issues](https://github.com/VoidLock/ReceiptPi/issues)
- **Discussions:** [GitHub Discussions](https://github.com/VoidLock/ReceiptPi/discussions)
- **Documentation:** [README.md](README.md) and [CREDITS.md](CREDITS.md)
