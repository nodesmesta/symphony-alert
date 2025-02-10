import requests
from telegram import Bot
from telegram.constants import ParseMode
from datetime import datetime, timedelta, timezone
import asyncio
import json
import os

# Konfigurasi
CONFIG_FILE = "config.json"
CACHE_FILE = "status_cache.json"
BLOCK_HEIGHT_THRESHOLD = 100  # Notifikasi jika block height tertinggal lebih dari ini
MIN_UPTIME_FOR_REWARD = 95.0  # Minimum uptime untuk memenuhi syarat reward
MIN_REWARD_PERCENTAGE = 10.0  # Minimum reward dari delegasi yang memenuhi syarat
MIN_STAKE_FOR_REWARD = 10000000.0  # Minimum stake untuk memenuhi syarat reward (dalam note)
REWARD_FILE = "reward.txt"

# Fungsi untuk membaca konfigurasi
def load_config():
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"File konfigurasi '{CONFIG_FILE}' tidak ditemukan.")
    with open(CONFIG_FILE, "r") as file:
        return json.load(file)

config = load_config()
RPC_URL = config["rpc_url"]
LCD_API_URL = config["lcd_url"]
TELEGRAM_TOKEN = config["telegram_token"]
TELEGRAM_CHAT_ID = config["telegram_chat_id"]
VALIDATOR_ADDRESS = config["validator_address"]

# Fungsi untuk mendapatkan IP publik secara otomatis
def get_public_ip():
    try:
        response = requests.get("https://api.ipify.org?format=json", timeout=10)
        if response.status_code == 200:
            return response.json().get("ip", "Unknown IP")
        else:
            return "Unknown IP"
    except Exception:
        return "Unknown IP"

NODE_IP = get_public_ip()

# Fungsi untuk membaca cache
def read_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as file:
            return json.load(file)
    return {}

# Fungsi untuk menulis cache
def write_cache(data):
    with open(CACHE_FILE, "w") as file:
        json.dump(data, file)

# Fungsi untuk mendapatkan periode mingguan
def get_weekly_period():
    now = datetime.now(timezone.utc)
    start_of_week = now - timedelta(days=(now.weekday() - 2) % 7)  # Pindahkan ke Rabu
    start_time = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return start_time.timestamp(), end_time.timestamp()

# Fungsi untuk menghitung uptime delegasi
def calculate_delegator_uptime(delegator_list, tracked_timestamps):
    uptimes = {}
    rewards = {}
    current_time = datetime.now().timestamp()
    start_time, end_time = get_weekly_period()

    for delegator in delegator_list:
        address = delegator["delegator_address"]
        stake = delegator["balance"]

        if address in tracked_timestamps:
            delegator_start = max(tracked_timestamps[address], start_time)  # Mulai dari timestamp atau awal minggu
            delegator_end = min(current_time, end_time)  # Hingga saat ini atau akhir minggu
            active_duration = max(0, delegator_end - delegator_start)
            total_duration = max(1, end_time - start_time)  # Hindari pembagian nol
            uptime_percentage = (active_duration / total_duration) * 100

            # Hitung reward jika uptime memenuhi syarat dan stake cukup
            if uptime_percentage >= MIN_UPTIME_FOR_REWARD and stake >= MIN_STAKE_FOR_REWARD:
                reward = (MIN_REWARD_PERCENTAGE / 100) * stake
            else:
                reward = 0.0

            uptimes[address] = uptime_percentage
            rewards[address] = reward
        else:
            uptimes[address] = 0.0
            rewards[address] = 0.0

    return uptimes, rewards

# Fungsi untuk menyimpan daftar delegator ke file
def save_delegators_to_file(delegator_list, uptimes, rewards):
    # Ambil waktu saat ini dalam UTC
    current_time = datetime.now(timezone.utc).strftime("%A, %d-%m-%Y %H:%M UTC")

    # Format data delegator
    formatted_data = [
        f"{i + 1}. {delegator['delegator_address']} | {delegator['balance'] / 1000000:.6f} MLD | {uptimes.get(delegator['delegator_address'], 0.00):.2f}% | {rewards.get(delegator['delegator_address'], 0.00) / 1000000:.6f} MLD"
        for i, delegator in enumerate(delegator_list)
    ]

    # Tulis ke file delegator.txt
    with open("delegator.txt", "w") as file:
        file.write(f"Update at {current_time}\n")
        file.writelines("\n".join(formatted_data))
        file.write("\n")

# Fungsi untuk menyimpan reward ke file saat periode berakhir
def save_rewards_to_file(rewards):
    current_time = datetime.now(timezone.utc).strftime("%A, %d-%m-%Y %H:%M UTC")

    formatted_rewards = [
        f"{addr} | Reward: {reward / 1000000:.6f} MLD"
        for addr, reward in rewards.items() if reward > 0
    ]

    with open(REWARD_FILE, "w") as file:
        file.write(f"Reward Update at {current_time}\n")
        file.writelines("\n".join(formatted_rewards))
        file.write("\n")

    # Kirim notifikasi Telegram
    asyncio.run(send_telegram_message(
        f"<b>🏅 Reward Calculation Completed</b>\nTotal delegator rewarded: {len(formatted_rewards)}"
    ))

# Fungsi untuk mengirim pesan Telegram
async def send_telegram_message(message):
    header = (
        "<b>🚨 Symphony Alert</b>\n"
        f"<b>🌐 IP Address:</b> {NODE_IP}\n"
        "<b>📊 Node Status:</b>\n"
    )
    bot = Bot(token=TELEGRAM_TOKEN)
    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=f"{header}{message}\n<i>----- Alert by NodeSemesta -----</i>",
        parse_mode=ParseMode.HTML
    )

# Fungsi untuk memantau sinkronisasi node
async def monitor_node_sync(cache):
    try:
        status = requests.get(f"{RPC_URL}/status", timeout=10).json()
        sync_info = status['result']['sync_info']
        catching_up = sync_info['catching_up']
        latest_block = int(sync_info['latest_block_height'])

        # Ambil informasi sebelumnya dari cache
        previous_catching_up = cache.get("catching_up", True)
        previous_block = int(cache.get("latest_block", 0))

        # Update cache
        cache["latest_block"] = latest_block
        cache["catching_up"] = catching_up

        # Kirim notifikasi hanya jika ada perubahan status sinkronisasi
        if catching_up != previous_catching_up:
            if catching_up:
                await send_telegram_message(f"<b>⏳ Node sedang sinkronisasi.</b>\nTinggi blok saat ini: <b>{latest_block}</b>")
            else:
                await send_telegram_message(f"<b>✅ Node sudah sinkron.</b>\nTinggi blok: <b>{latest_block}</b>")
        # Kirim notifikasi jika node tertinggal lebih dari BLOCK_HEIGHT_THRESHOLD
        elif latest_block - previous_block > BLOCK_HEIGHT_THRESHOLD:
            await send_telegram_message(f"<b>⚠️ Node tertinggal lebih dari {BLOCK_HEIGHT_THRESHOLD} blok.</b>\nTinggi blok saat ini: <b>{latest_block}</b>")

    except Exception as e:
        await send_telegram_message(f"<b>❌ Terjadi kesalahan saat memantau sinkronisasi node:</b> {str(e)}")

# Fungsi untuk memantau status validator
async def monitor_validator_status(cache):
    try:
        response = requests.get(f"{LCD_API_URL}/cosmos/staking/v1beta1/validators/{VALIDATOR_ADDRESS}", timeout=10)
        if response.status_code == 200:
            data = response.json()
            jailed = data.get("jailed", False)
            status = "bonded" if not jailed else "jailed"
            if cache.get("validator_status") != (jailed, status):
                cache["validator_status"] = (jailed, status)
                validator_status = "<b>🔴 Jailed</b>" if jailed else "<b>🟢 Bonded</b>"
                await send_telegram_message(f"<b>Status Validator:</b> {validator_status}")
        else:
            raise Exception(f"Error fetching validator status: {response.status_code} {response.text}")
    except Exception as e:
        await send_telegram_message(f"<b>❌ Terjadi kesalahan saat memantau status validator:</b> {str(e)}")

# Fungsi untuk memantau delegator
async def monitor_delegators(cache):
    try:
        response = requests.get(f"{LCD_API_URL}/cosmos/staking/v1beta1/validators/{VALIDATOR_ADDRESS}/delegations", timeout=10)
        if response.status_code == 200:
            delegations = response.json().get("delegation_responses", [])

            delegator_list = [
                {
                    "delegator_address": d["delegation"]["delegator_address"],
                    "shares": float(d["delegation"]["shares"]),
                    "balance": float(d["balance"]["amount"])
                }
                for d in delegations
            ]

            # Lacak timestamp delegasi sejak skrip pertama kali dijalankan
            tracked_timestamps = cache.get("delegator_timestamps", {})
            current_time = datetime.now().timestamp()
            for delegator in delegator_list:
                address = delegator["delegator_address"]
                if address not in tracked_timestamps:
                    tracked_timestamps[address] = current_time
            cache["delegator_timestamps"] = tracked_timestamps

            # Hitung uptime dan reward delegator
            uptimes, rewards = calculate_delegator_uptime(delegator_list, tracked_timestamps)

            # Simpan delegator ke file
            save_delegators_to_file(delegator_list, uptimes, rewards)

            # Deteksi perubahan dalam daftar delegator
            old_delegators = {d['delegator_address']: d['balance'] for d in cache.get("delegator_list", [])}
            new_delegators = {d['delegator_address']: d['balance'] for d in delegator_list}

            changes = []
            for addr, balance in new_delegators.items():
                if addr not in old_delegators:
                    changes.append(f"➕ Delegator Baru: {addr} | {balance / 1000000:.6f} MLD")
                elif old_delegators[addr] != balance:
                    if old_delegators[addr] < balance:
                        changes.append(f"🔼 Penambahan Stake: {addr} | {balance / 1000000:.6f} MLD")
                    else:
                        changes.append(f"🔽 Pengurangan Stake: {addr} | {balance / 1000000:.6f} MLD")

            for addr in old_delegators:
                if addr not in new_delegators:
                    changes.append(f"❌ Delegator Keluar: {addr}")

            # Simpan perubahan ke cache
            cache["delegator_list"] = delegator_list

            # Kirim notifikasi jika ada perubahan
            if changes:
                await send_telegram_message("\n".join(changes))

        else:
            raise Exception(f"Error fetching delegators: {response.status_code} {response.text}")

    except Exception as e:
        await send_telegram_message(f"❌ Terjadi kesalahan saat mengambil data delegator: {str(e)}")

# Fungsi utama untuk memantau semua
async def main():
    cache = read_cache()
    while True:
        await monitor_node_sync(cache)
        await monitor_validator_status(cache)
        await monitor_delegators(cache)
        write_cache(cache)

if __name__ == "__main__":
    asyncio.run(main())
