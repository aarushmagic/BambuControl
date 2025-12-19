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

PRINTER_SERIAL_1 = os.getenv("PRINTER_SERIAL_1")
PRINTER_SERIAL_2 = os.getenv("PRINTER_SERIAL_2")
BAMBU_USER_ID = os.getenv("BAMBU_USER_ID")
BAMBU_ACCESS_TOKEN = os.getenv("BAMBU_ACCESS_TOKEN")
LOG_SHEET_URL = os.getenv("LOG_SHEET_URL")
AUTH_SHEET_URL = os.getenv("AUTH_SHEET_URL")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger("PrinterGuard")

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
                    matrix[i][j] = min(
                        matrix[i - 1][j - 1] + 1,
                        matrix[i][j - 1] + 1,
                        matrix[i - 1][j] + 1
                    )
        
        return matrix[len(b)][len(a)]

    def is_authorized(self, log_first: str, log_last: str) -> bool:
        try:
            response = requests.get(f"{AUTH_SHEET_URL}&t={int(time.time())}")
            response.raise_for_status()
            reader = csv.reader(io.StringIO(response.text))
            auth_rows = list(reader)

            log_f = log_first.strip()
            log_l = log_last.strip()
            
            best_score = 999
            
            start_idx = 1 if auth_rows and "LAST" in str(auth_rows[0][0]).upper() else 0

            for row in auth_rows[start_idx:]:
                if len(row) < 2: continue
                
                auth_l = row[COL_AUTH_LAST].strip()
                auth_f = row[COL_AUTH_FIRST].strip()

                f_score = self.levenshtein(log_f, auth_f)
                l_score = self.levenshtein(log_l, auth_l)
                total_score = f_score + l_score

                if total_score < best_score:
                    best_score = total_score
            
            return best_score <= 3

        except Exception as e:
            logger.error(f"   [Auth Check] Failed to fetch/parse authorized list: {e}")
            return False

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
            response = requests.get(url)
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
                logger.warning(f"  [Sheet] No history found for {printer_name}")
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
                logger.error(f"  [Sheet] Date Error: {e}")
                return None
        except Exception as e:
            logger.error(f"  [Sheet] Network Error: {e}")
            return None

    def enforce_rules(self, device_id: str, client: MQTTClient):
        printer_name = PRINTER_MAP.get(device_id, "Unknown")
        
        log_entry = self.fetch_active_log(printer_name)

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
            command = {
                "print": {
                    "command": "stop",
                    "sequence_id": seq_id
                }
            }
            payload = json.dumps(command)
            client.client.publish(f"device/{client.device_id}/request", payload)
            logger.info(f"[{printer_name}] STOP COMMAND SENT (Seq: {seq_id})")
        except Exception as e:
            logger.error(f"[{printer_name}] Failed to send stop command: {e}")

    def on_message(self, device_id: str, data: dict):
        if 'print' not in data: return

        if device_id not in self.printer_states: self.printer_states[device_id] = {}
        self.printer_states[device_id].update(data['print'])
        
        current_state = self.printer_states[device_id]
        gcode_state = current_state.get('gcode_state', 'UNKNOWN')
        try: layer_num = int(current_state.get('layer_num', 0))
        except: layer_num = 0
        subtask_id = current_state.get('subtask_id', 'unknown')
        printer_name = PRINTER_MAP.get(device_id, device_id)

        if gcode_state == 'RUNNING' and layer_num >= 1:
            if self.checked_prints.get(device_id) != subtask_id:
                client = next((c for c in self.clients if c.device_id == device_id), None)
                if client:
                    threading.Thread(target=self.enforce_rules, args=(device_id, client)).start()
                    self.checked_prints[device_id] = subtask_id
        
        if gcode_state in ['IDLE', 'FINISH', 'FAILED'] and device_id in self.checked_prints:
            del self.checked_prints[device_id]
            logger.info(f"[{printer_name}] Print finished/stopped. Monitoring for next job.")

    def start(self):
        printers = [PRINTER_SERIAL_1, PRINTER_SERIAL_2]
        logger.info(f"Starting Printer Police (Library Version) for UID: {BAMBU_USER_ID}")

        for serial in printers:
            client = MQTTClient(username=BAMBU_USER_ID, access_token=self.token, device_id=serial, on_message=self.on_message)
            client.connect(blocking=False)
            time.sleep(1)
            
            self.clients.append(client)
            time.sleep(0.5)

        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            for client in self.clients: client.disconnect()

if __name__ == "__main__":
    monitor = PrinterMonitor()
    monitor.start()