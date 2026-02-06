# Ntfy Receipt Printer 🖨️💬

Turn digital notifications into tangible memories (or useful tickets!) with this simple Python service. It listens to your favorite [ntfy.sh](https://ntfy.sh) topic and instantly prints incoming messages to a connected USB thermal receipt printer.

Imagine:
*   A physical notification system for your home or office.
*   Sending fun, quirky messages to a loved one's printer.
*   A basic, low-cost order ticketing system for a small shop.

Developed with efficiency in mind, this project runs beautifully on lightweight, low-power ARM devices like the **Orange Pi Zero 2W (4GB RAM)** running **DietPi**. Just plug in any standard **USB ESC/POS thermal printer**, and you're ready to go!

---

## Get Started in Minutes! (Manual Run)

Want to see it in action quickly? Follow these steps to get your printer spitting out messages without permanent installation.

### 1. Prepare Your System

First, make sure you have Python 3 and some essential tools installed.

```bash
# For Debian/Ubuntu-based systems (like DietPi):
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git
```

### 2. Grab the Code

Clone this repository to your machine. Remember to replace `your-username/ntfy-receipt-printer.git` with the actual URL from GitHub!

```bash
git clone https://github.com/your-username/ntfy-receipt-printer.git
cd ntfy-receipt-printer
```

### 3. Set Up Your Python Environment

Create a dedicated virtual environment for the project and install the necessary Python libraries.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Configure Your Printer & Ntfy Topic

The service uses a `.env` file for all its settings.

*   **Create the file:**
    ```bash
    cp .env.template .env
    ```
*   **Edit `.env`:** Open the newly created `.env` file and fill in your details:
    *   `NTFY_HOST`: The URL of your ntfy server (e.g., `https://ntfy.sh`).
    *   `NTFY_TOPIC`: The ntfy topic you want to subscribe to.
    *   `PRINTER_VENDOR`: Your USB thermal printer's Vendor ID.
    *   `PRINTER_PRODUCT`: Your USB thermal printer's Product ID.

    **Pro Tip:** Don't know your printer's Vendor/Product IDs? Just run `lsusb` in your terminal and look for your printer!

### 5. Run It!

With your virtual environment still active (`source venv/bin/activate` if you closed your terminal), start the service:

```bash
python app.py
```

Now, send a message to your configured ntfy topic (e.g., using the ntfy app, website, or `curl`). If everything's correct, your printer should instantly print the message! Press `Ctrl+C` in your terminal to stop the service.

---

## Install as a Systemd Service (For Autostart & Reliability)

For a more permanent setup, you can install the service to automatically start when your system boots.

**Important:** You need `sudo` privileges to run the installer.

```bash
sudo ./scripts/install_service.sh $(pwd) $(whoami)
```

This handy script does all the heavy lifting:
1.  It copies a `systemd` service file to `/etc/systemd/system/`.
2.  It creates a default environment file for the service at `/etc/default/receipt-printer`, pulling values from your project's `.env` file.
3.  Finally, it enables and starts the `receipt-printer` service for you.

To check if your new service is running correctly:

```bash
systemctl status receipt-printer
```

Congratulations! Your physical notification system is now fully operational and will automatically start with your machine.

---

Enjoy your new printer!
