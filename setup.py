import os
import json
import subprocess

# File konfigurasi
CONFIG_FILE = "config.json"
SERVICE_FILE = "/etc/systemd/system/checker.service"
CHECKER_PATH = os.path.abspath("checker.py")

# Fungsi untuk membuat file konfigurasi
def create_config():
    print("\n=== Setup Symphony Checker ===\n")
    rpc_url = input("Masukkan RPC URL (default: http://127.0.0.1:26657): ") or "http://127.0.0.1:26657"
    lcd_url = input("Masukkan LCD API URL (default: http://127.0.0.1:1317): ") or "http://127.0.0.1:1317"
    telegram_token = input("Masukkan Telegram Bot Token: ")
    telegram_chat_id = input("Masukkan Telegram Chat ID: ")
    validator_address = input("Masukkan Validator Address: ")

    config = {
        "rpc_url": rpc_url,
        "lcd_url": lcd_url,
        "telegram_token": telegram_token,
        "telegram_chat_id": telegram_chat_id,
        "validator_address": validator_address
    }

    with open(CONFIG_FILE, "w") as file:
        json.dump(config, file, indent=4)

    print(f"\nFile konfigurasi '{CONFIG_FILE}' berhasil dibuat.")

# Fungsi untuk membuat file systemd service
def create_service():
    print("\n=== Membuat Systemd Service ===\n")

    service_content = f"""[Unit]
Description=Symphony Checker Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 {CHECKER_PATH}
WorkingDirectory={os.path.dirname(CHECKER_PATH)}
Restart=on-failure
RestartSec=60
User={os.getenv('USER')}

[Install]
WantedBy=multi-user.target
"""

    with open(SERVICE_FILE, "w") as file:
        file.write(service_content)

    subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
    subprocess.run(["sudo", "systemctl", "enable", "checker.service"], check=True)
    print(f"Systemd service '{SERVICE_FILE}' berhasil dibuat dan diaktifkan.")

# Fungsi untuk memulai service
def start_service():
    print("\n=== Memulai Symphony Checker Service ===\n")
    subprocess.run(["sudo", "systemctl", "start", "checker.service"], check=True)
    print("Service Symphony Checker berhasil dimulai.")

# Fungsi utama untuk setup
def main():
    create_config()
    create_service()
    start_service()
    print("\nSetup selesai. Symphony Checker sedang berjalan.")

if __name__ == "__main__":
    main()
