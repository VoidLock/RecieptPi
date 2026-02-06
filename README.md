# ntfy-receipt-printer

A lightweight Python service that listens to an [ntfy.sh](https://ntfy.sh) topic and prints messages to a connected USB thermal receipt printer.

This project is perfect for creating a physical notification system, a fun message printer for a loved one, or a simple order ticket system.

## Reference Hardware

This service was developed and tested on the following hardware, proving it's a great fit for lightweight, low-power ARM systems:

*   **Board:** Orange Pi Zero 2W (4GB RAM)
*   **OS:** DietPi (minimal image)
*   **Printer:** A standard USB ESC/POS thermal printer.

## Prerequisites

Before you begin, ensure you have the following installed on your system:

```bash
# For Debian/Ubuntu-based systems like DietPi:
sudo apt-get update
sudo apt-get install python3 python3-pip python3-venv git
```

## Installation

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/your-username/ntfy-receipt-printer.git
    cd ntfy-receipt-printer
    ```
    *(Replace `your-username/ntfy-receipt-printer.git` with the actual URL of this repository).*

2.  **Create and activate a Python virtual environment:**

    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install the required Python packages:**

    ```bash
    pip install -r requirements.txt
    ```

## Configuration

All configuration is handled through an `.env` file.

1.  **Create your configuration file:**

    Copy the template to create your local environment file:
    ```bash
    cp .env.template .env
    ```

2.  **Edit the `.env` file:**

    Open the `.env` file and fill in the following values:

    *   `NTFY_HOST`: The URL of your ntfy server (e.g., `https://ntfy.sh`).
    *   `NTFY_TOPIC`: The ntfy topic you want to subscribe to.
    *   `PRINTER_VENDOR`: The USB Vendor ID of your thermal printer.
    *   `PRINTER_PRODUCT`: The USB Product ID of your thermal printer.

    *Tip: You can find your printer's Vendor and Product IDs by running the `lsusb` command.*

## Running the Service

### Manual Execution (for Testing)

You can run the service directly from your terminal to test your configuration. Make sure your virtual environment is activated (`source venv/bin/activate`).

```bash
python app.py
```

Send a message to your configured ntfy topic. If everything is correct, your printer should spring to life! Press `Ctrl+C` to stop the service.

### Installing as a Systemd Service

To ensure the printer service runs automatically on boot, an installation script is provided.

**The installer must be run with `sudo` privileges.**

```bash
sudo ./scripts/install_service.sh $(pwd) $(whoami)
```
This command does three things:
1.  Copies a systemd service file to `/etc/systemd/system/`.
2.  Creates a default environment file at `/etc/default/receipt-printer` (using the values from your `.env` file).
3.  Enables and starts the `receipt-printer` service.

You can check the status of your new service with:
```bash
systemctl status receipt-printer
```

Enjoy your new physical notification system!