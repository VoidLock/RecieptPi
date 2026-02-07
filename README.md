# RecieptPi

This project is a Python service that subscribes to the [ntfy.sh](https://ntfy.sh) *or selfhosted ntfy server* topic and prints received messages to a connected USB thermal receipt printer.

## Purpose

This service was designed for:
*   Creating a physical notification system.
*   Printing messages received from an ntfy topic.
*   Serving as a simple order ticket system.

## Features

* **Prints ntfy messages** to ESC/POS USB thermal printers
* **Preview mode** (no printer required) with image output
* **Structured message support** (plain text, kanban cards, priority alerts)
* **Calibration & alignment tools** for precise print placement
* **Memory protection** with automatic pause/resume under high usage
* **Error notifications** to a separate ntfy topic
* **Auto-updates** via git with configurable polling interval
* **Configurable logging** with file output for server mode
* **Graceful shutdown** via `Q` (interactive) or system signals

### Resource Usage

*Note: The auto-update checker runs as a daemon thread and is idle most of the time.*

* **Memory:** <0.5 MB
* **CPU:** ~0.1% (1s active per hour)
* **Network:** <0.1 MB/day

## Development Hardware

The service was developed and tested on the following hardware:

*   **Board:** Orange Pi Zero 2W (4GB RAM)
*   **OS:** DietPi (minimal image)
*   **Printer:** A standard USB ESC/POS thermal printer.

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
git clone https://github.com/VoidLock/RecieptPi.git
cd RecieptPi
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
*   `LOG_LEVEL`: Logging verbosity - `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (default: `INFO`)
*   `LOG_FILE`: Log file path for server mode (default: `/var/log/receipt-printer.log`)
*   `ERROR_NTFY_TOPIC`: **Separate** ntfy topic URL to send error notifications to (e.g., `https://ntfy.sh/my-printer-errors`). This should be different from your main `NTFY_TOPIC`.
*   `AUTO_UPDATE`: Enable automatic git-based updates - `true` or `false` (default: `false`)
*   `UPDATE_CHECK_INTERVAL`: Seconds between update checks (default: `3600` = 1 hour)
*   `GITHUB_REPO`: GitHub repository for updates (default: `VoidLock/RecieptPi`)

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
GITHUB_REPO=VoidLock/RecieptPi

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

The `app.py` script supports the following command-line flags:

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

### Flag Descriptions

**Connection Flags:**
*   `--host <URL>`: Specify the ntfy host URL (e.g., `https://ntfy.example.com`). Overrides `NTFY_HOST` from `.env`.
*   `--topic <NAME>`: Specify the ntfy topic name. Overrides `NTFY_TOPIC` from `.env`.

**Testing & Calibration Flags:**
*   `--calibrate`: Prints a calibration grid to help determine the printable area and adjust printer settings. The script will output instructions for using the grid.
*   `--test-align`: Prints an alignment test message and exits.
*   `--preview`, `-p`: Runs in preview mode, displaying images in a window instead of sending them to the printer. Useful for testing without consuming thermal paper. Terminal will open image in any image viewer as a preview.
*   `--example <TYPE>`, `-e <TYPE>`: Prints an example message of the specified type (`text` or `kanban`) and exits.

### Calibrating the Print Bounding Box

To optimize printing for your specific thermal printer and paper, you can use the built-in calibration feature:

1.  **Run Calibration:** With your printer connected and the virtual environment active, execute the calibration command:
    ```bash
    python app.py --calibrate
    ```
2.  **Inspect Printout:** The printer will output a calibration grid. Examine it carefully:
    *   Note the rightmost column letter that is clearly visible.
    *   Observe if the text is centered or shifted to one side.
3.  **Adjust `.env` Variables:** Based on your observations, modify the following variables in your `.env` file:
    *   `X_OFFSET_MM`: Adjusts the horizontal centering. Use negative values to shift left, positive to shift right.
    *   `SAFE_MARGIN_MM`: Defines the margin from the paper's edge. Increase this if the right edge of your printout is cut off.
    *   `MAX_HEIGHT_MM`: (Optional) Sets a maximum height for receipts in millimeters.

    *Example .env adjustments:*
    ```
    X_OFFSET_MM=2
    SAFE_MARGIN_MM=5
    # MAX_HEIGHT_MM=150
    ```
    Repeat the calibration process until you are satisfied with the print alignment and bounding box.

## Systemd Service Installation (Permanent Run)

To install the service to run automatically on system boot, use the provided installer script.

**Note:** This script requires `sudo` privileges.

```bash
chmod +x ./scripts/install_service
chmod +x ./scripts/uninstall_service

sudo ./scripts/install_service $(whoami)
```

This script performs the following actions:
1.  Copies the application to `/opt/receipt-printer`.
2.  Moves or creates the `.env` file in `/opt/receipt-printer/.env`.
3.  Creates a virtual environment in `/opt/receipt-printer/venv` and installs dependencies.
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

The service can automatically check for and install updates from the GitHub repository.

**Enable auto-updates:**
1. Set `AUTO_UPDATE=true` in your `.env` file
2. Restart the service: `sudo systemctl restart receipt-printer`

The service will:
- Check GitHub every hour (configurable via `UPDATE_CHECK_INTERVAL`)
- Automatically pull latest changes via git
- Restart the service to apply updates
- Send error notifications if updates fail (requires `ERROR_NTFY_TOPIC`)

**Manual update:**
```bash
cd /path/to/ntfy-receipt-printer
git pull origin main
sudo systemctl restart receipt-printer
```

### Error Notifications

Set `ERROR_NTFY_TOPIC` in `.env` to receive error notifications sent **to a separate topic** from your main print topic.

**Important:** Use a different topic than `NTFY_TOPIC`:
- `NTFY_TOPIC` = Messages you send TO the printer (to print)
- `ERROR_NTFY_TOPIC` = Error messages FROM the printer (for monitoring)

You'll receive notifications when:
- Printer connection fails
- Print jobs fail
- ntfy connection errors occur
- Auto-updates fail

Example:
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
