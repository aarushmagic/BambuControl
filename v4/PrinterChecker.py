import os
import sys
import time
import csv
import io
import json
import requests
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional, List
from bambulab import MQTTClient

# --- Configuration & Environment Variables ---
PRINTER_SERIAL_1 = os.getenv("PRINTER_SERIAL_1", "").strip()
PRINTER_SERIAL_2 = os.getenv("PRINTER_SERIAL_2", "").strip()
BAMBU_USER_ID = os.getenv("BAMBU_USER_ID", "").strip()
BAMBU_ACCESS_TOKEN = os.getenv("BAMBU_ACCESS_TOKEN", "").strip()
LOG_SHEET_URL = os.getenv("LOG_SHEET_URL", "").strip()
AUTH_SHEET_URL = os.getenv("AUTH_SHEET_URL", "").strip()

# Logging Setup
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - [%(levelname)s] %(message)s', 
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("PrinterGuard")

# Validation
required_vars = [
    ("PRINTER_SERIAL_1", PRINTER_SERIAL_1),
    ("PRINTER_SERIAL_2", PRINTER_SERIAL_2),
    ("BAMBU_USER_ID", BAMBU_USER_ID),
    ("BAMBU_ACCESS_TOKEN", BAMBU_ACCESS_TOKEN),
    ("LOG_SHEET_URL", LOG_SHEET_URL),
    ("AUTH_SHEET_URL", AUTH_SHEET_URL)
]

missing_vars = [name for name, val in required_vars if not val]
if missing_vars:
    logger.critical(f"Error: Missing environment variables: {', '.join(missing_vars)}")
    sys.exit(1)

PRINTER_MAP = {
    PRINTER_SERIAL_1: "Printer 1",
    PRINTER_SERIAL_2: "Printer 2"
}

# Column Indices
COL_LOG_FIRST = 1
COL_LOG_LAST = 2
COL_LOG_PRINTER = 4
COL_LOG_START_DATE = 5
COL_LOG_START_TIME = 6
COL_LOG_DURATION = 7

COL_AUTH_LAST = 0
COL_AUTH_FIRST = 1

class PrinterMonitor:
    def __init__(self):
        self.token = BAMBU_ACCESS_TOKEN
        self.checked_prints = {} 
        self.printer_states = {} 
        self.clients = []
        
        # Store the timestamp when we first saw Layer 1
        self.layer_verification_timers = {} 
        self.VERIFICATION_DELAY = 15 # Seconds to wait to confirm Layer 1 is real

    # --- FUZZY MATCHING ---
    def levenshtein(self, a: str, b: str) -> int:
        if not a: return len(b)
        if not b: return len(a)
        matrix = [[0 for _ in range(len(a) + 1)] for _ in range(len(b) + 1)]
        for i in range(len(b) + 1): matrix[i][0] = i
        for j in range(len(a) + 1): matrix[0][j] = j
        for i in range(1, len(b) + 1):
            for j in range(1, len(a) + 1):
                if b[i - 1].lower() == a[j - 1].lower():
                    matrix[i][j] = matrix[i - 1][j - 1]
                else:
                    matrix[i][j] = min(matrix[i - 1][j - 1] + 1, matrix[i][j - 1] + 1, matrix[i - 1][j] + 1)
        return matrix[len(b)][len(a)]

    # --- AUTHORIZATION CHECK ---
    def is_authorized(self, log_first: str, log_last: str) -> bool:
        try:
            response = requests.get(f"{AUTH_SHEET_URL}&t={int(time.time())}", timeout=10)
            response.raise_for_status()
            reader = csv.reader(io.StringIO(response.text))
            auth_rows = list(reader)

            log_f, log_l = log_first.strip(), log_last.strip()
            best_score = 999
            
            start_idx = 1 if auth_rows and "LAST" in str(auth_rows[0][0]).upper() else 0

            for row in auth_rows[start_idx:]:
                if len(row) < 2: continue
                auth_l, auth_f = row[COL_AUTH_LAST].strip(), row[COL_AUTH_FIRST].strip()
                total_score = self.levenshtein(log_f, auth_f) + self.levenshtein(log_l, auth_l)
                if total_score < best_score:
                    best_score = total_score
            
            return best_score <= 3
        except Exception as e:
            logger.error(f"   [Auth Check] Failed to fetch auth list: {e}")
            return False

    # --- LOG PARSING ---
    def parse_duration(self, duration_str: str) -> timedelta:
        try:
            parts = list(map(int, duration_str.split(':')))
            if len(parts) == 3: return timedelta(hours=parts[0], minutes=parts[1], seconds=parts[2])
            elif len(parts) == 2: return timedelta(hours=parts[0], minutes=parts[1])
        except: pass
        return timedelta(hours=1)
    
    def fetch_active_log(self, printer_name: str) -> Optional[List[str]]:
        try:
            url = f"{LOG_SHEET_URL}&t={int(time.time())}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            reader = csv.reader(io.StringIO(response.text))
            rows = list(reader)
            
            last_entry = None
            for row in reversed(rows):
                if len(row) <= COL_LOG_DURATION: continue
                if row[COL_LOG_PRINTER].strip() == printer_name:
                    last_entry = row
                    break
            
            if not last_entry:
                return None

            try:
                date_str = last_entry[COL_LOG_START_DATE].strip()
                time_str = last_entry[COL_LOG_START_TIME].strip()
                duration_str = last_entry[COL_LOG_DURATION].strip()
                
                start_dt = datetime.strptime(f"{date_str} {time_str}", "%m/%d/%Y %I:%M:%S %p")
                duration = self.parse_duration(duration_str)
                end_dt = start_dt + duration
                
                if datetime.now() <= end_dt:
                    user_name = f"{last_entry[COL_LOG_FIRST]} {last_entry[COL_LOG_LAST]}"
                    logger.info(f"  [Sheet] Time Valid: {user_name} until {end_dt.strftime('%H:%M')}")
                    return last_entry
                else:
                    logger.warning(f"  [Sheet] Expired: Ended at {end_dt.strftime('%H:%M')}")
                    return None
            except ValueError as e:
                logger.error(f"  [Sheet] Date Parse Error: {e}")
                return None
        except Exception as e:
            logger.error(f"  [Sheet] Network Error: {e}")
            return None

    # --- ENFORCEMENT LOGIC ---
    def enforce_rules(self, device_id: str, client: MQTTClient):
        printer_name = PRINTER_MAP.get(device_id, "Unknown")
        
        # --- GOOGLE SHEETS LATENCY BUFFER ---
        # Try twice over 10s to ensure we don't fail due to Google API lag
        log_entry = None
        for attempt in range(1, 3): 
            log_entry = self.fetch_active_log(printer_name)
            if log_entry:
                break
            
            if attempt == 1:
                logger.warning(f"[{printer_name}] Layer 1 Verified, but log missing. Waiting 10s for Google update...")
                time.sleep(10)
        # ------------------------------------

        if not log_entry:
            logger.warning(f"[{printer_name}] 🛑 VIOLATION: Unlogged/Expired Print. Sending STOP.")
            self.cancel_print(client, printer_name, "Unlogged")
            return

        first_name = log_entry[COL_LOG_FIRST]
        last_name = log_entry[COL_LOG_LAST]
        full_name = f"{first_name} {last_name}"

        logger.info(f"   [Auth] Verifying user: {full_name}")
        is_allowed = self.is_authorized(first_name, last_name)

        if not is_allowed:
            logger.warning(f"[{printer_name}] 🛑 VIOLATION: Unauthorized User ({full_name}). Sending STOP.")
            self.cancel_print(client, printer_name, f"Unauthorized: {full_name}")
        else:
            logger.info(f"[{printer_name}] ✅ SUCCESS: Print Authorized for {full_name}.")

    def cancel_print(self, client: MQTTClient, printer_name: str, reason: str):
        try:
            seq_id = int(time.time())
            command = {"print": {"command": "stop", "sequence_id": seq_id}}
            payload = json.dumps(command)
            client.client.publish(f"device/{client.device_id}/request", payload)
            logger.info(f"[{printer_name}] STOP COMMAND SENT (Seq: {seq_id})")
        except Exception as e:
            logger.error(f"[{printer_name}] Failed to send stop command: {e}")

    # --- MQTT CALLBACK ---
    def on_message(self, device_id: str, data: dict):
        if 'print' not in data: return

        if device_id not in self.printer_states: self.printer_states[device_id] = {}
        self.printer_states[device_id].update(data['print'])
        
        current_state = self.printer_states[device_id]
        gcode_state = current_state.get('gcode_state', 'UNKNOWN')
        subtask_id = current_state.get('subtask_id', 'unknown')
        printer_name = PRINTER_MAP.get(device_id, device_id)
        
        try: layer_num = int(current_state.get('layer_num', 0))
        except: layer_num = 0

        # --- "GHOST LAYER" PROTECTION ---
        # 1. If we are running and appear to be at Layer 1+, start a timer.
        if gcode_state == 'RUNNING' and layer_num >= 1:
            if device_id not in self.layer_verification_timers:
                self.layer_verification_timers[device_id] = time.time()
                # logger.info(f"[{printer_name}] Layer {layer_num} reported. Starting {self.VERIFICATION_DELAY}s truth timer...")
            
            # 2. Only proceed if the timer has exceeded the delay (proving it's real)
            elapsed = time.time() - self.layer_verification_timers[device_id]
            
            if elapsed > self.VERIFICATION_DELAY:
                # Timer passed! It's real.
                if self.checked_prints.get(device_id) != subtask_id:
                    logger.info(f"[{printer_name}] CONFIRMED: Print {subtask_id} is genuinely at Layer {layer_num}. Verifying...")
                    client = next((c for c in self.clients if c.device_id == device_id), None)
                    if client:
                        threading.Thread(target=self.enforce_rules, args=(device_id, client)).start()
                        self.checked_prints[device_id] = subtask_id
        
        else:
            # If layer drops to 0 (calibration/reset), cancel the timer immediately.
            if device_id in self.layer_verification_timers:
                # logger.info(f"[{printer_name}] Layer reset to {layer_num}. Timer cancelled (was false alarm).")
                del self.layer_verification_timers[device_id]

        # Reset tracker when print finishes or stops
        if gcode_state in ['IDLE', 'FINISH', 'FAILED']:
            if device_id in self.checked_prints:
                del self.checked_prints[device_id]
                logger.info(f"[{printer_name}] Print finished/stopped. Monitoring for next job.")
            
            # Ensure timer is clear
            if device_id in self.layer_verification_timers:
                del self.layer_verification_timers[device_id]

    # --- MAIN LOOP (WATCHDOG) ---
    def start(self):
        printers = [PRINTER_SERIAL_1, PRINTER_SERIAL_2]
        logger.info(f"Starting Printer Guard for UID: {BAMBU_USER_ID}")

        for serial in printers:
            if not serial: continue
            client = MQTTClient(username=BAMBU_USER_ID, access_token=self.token, device_id=serial, on_message=self.on_message)
            client.connect(blocking=False)
            self.clients.append(client)
            logger.info(f"Connecting to {PRINTER_MAP.get(serial, serial)}...")
            time.sleep(1)

        logger.info("Startup complete. Listening for prints...")
        
        last_watchdog_time = 0
        WATCHDOG_INTERVAL = 60 

        try:
            while True:
                current_time = time.time()
                
                if current_time - last_watchdog_time > WATCHDOG_INTERVAL:
                    for client in self.clients:
                        try:
                            client.request_full_status()
                        except Exception as e:
                            logger.error(f"Watchdog failed for {client.device_id}: {e}")
                    
                    last_watchdog_time = current_time

                time.sleep(1) 

        except KeyboardInterrupt:
            logger.info("Stopping...")
            for client in self.clients: 
                client.disconnect()

if __name__ == "__main__":
    monitor = PrinterMonitor()
    monitor.start()