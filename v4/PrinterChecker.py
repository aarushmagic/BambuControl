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


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bambulab import MQTTClient

printer1 = "asdfghjkl1234"
printer2 = "asdfghjkl5678"
USER_UID = "0123456789"

PRINTER_MAP = {
    printer1: "Printer 1",
    printer2: "Printer 2"
}


SHEET_URL = "https://docs.google.com/spreadsheets/d/e/PUBLISHED_GOOGLE_SHEET_URL&single=true&output=csv"

COL_FIRST_NAME = 0
COL_PRINTER_NAME = 1
COL_START_DATE = 2
COL_START_TIME = 3
COL_DURATION = 4
COL_AUTHORIZED = 7

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger("PrinterGuard")

class PrinterMonitor:
    def __init__(self):
        self.token = os.getenv("token")
        if not self.token:
            logger.critical("Error: $token environment variable not set.")
            sys.exit(1)
        self.checked_prints = {}
        self.printer_states = {}
        self.clients = []

    def parse_duration(self, duration_str: str) -> timedelta:
        try:
            parts = list(map(int, duration_str.split(':')))
            if len(parts) == 3: return timedelta(hours=parts[0], minutes=parts[1], seconds=parts[2])
            elif len(parts) == 2: return timedelta(hours=parts[0], minutes=parts[1])
        except: pass
        return timedelta(hours=1)
    
    def fetch_active_log(self, printer_name: str) -> Optional[List[str]]:
        try:
            url = f"{SHEET_URL}&t={int(time.time())}"
            response = requests.get(url)
            response.raise_for_status()
            reader = csv.reader(io.StringIO(response.text))
            rows = list(reader)
            
            last_entry = None
            for row in reversed(rows):
                if len(row) <= COL_AUTHORIZED: continue
                if row[COL_PRINTER_NAME].strip() == printer_name:
                    last_entry = row
                    break
            
            if not last_entry:
                logger.warning(f"  [Sheet] No history found for {printer_name}")
                return None

            try:
                date_str = last_entry[COL_START_DATE].strip()
                time_str = last_entry[COL_START_TIME].strip()
                duration_str = last_entry[COL_DURATION].strip()
                start_dt = datetime.strptime(f"{date_str} {time_str}", "%m/%d/%Y %I:%M:%S %p")
                duration = self.parse_duration(duration_str)
                end_dt = start_dt + duration
                
                if datetime.now() <= end_dt:
                    logger.info(f"  [Sheet] Valid: {last_entry[COL_FIRST_NAME]} until {end_dt.strftime('%H:%M')}")
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
        logger.info(f"[{printer_name}] CHECKING GOOGLE SHEET...")

        log_entry = self.fetch_active_log(printer_name)

        if not log_entry:
            logger.warning(f"[{printer_name}] 🛑 VIOLATION: Unlogged Print. Sending STOP command.")
            self.cancel_print(client, printer_name, "Unlogged")
            return

        user_name = log_entry[COL_FIRST_NAME]
        authorized = log_entry[COL_AUTHORIZED].strip().lower()

        if authorized != "yes":
            logger.warning(f"[{printer_name}] 🛑 VIOLATION: Unauthorized ({user_name}). Sending STOP command.")
            self.cancel_print(client, printer_name, f"Unauthorized: {user_name}")
        else:
            logger.info(f"[{printer_name}] ✅ SUCCESS: Print Authorized for {user_name}.")

    def cancel_print(self, client: MQTTClient, printer_name: str, reason: str):
        try:
            # === INTEGRATED FIX: USE WORKING KILL CODE LOGIC ===
            
            # 1. Use Integer Sequence ID
            seq_id = int(time.time())
            
            command = {
                "print": {
                    "command": "stop",
                    "sequence_id": seq_id
                }
            }
            
            payload = json.dumps(command)
            logger.info(f"[{printer_name}] Sending Kill Payload: {payload}")
            
            # 2. Use raw publish via internal client
            info = client.client.publish(f"device/{client.device_id}/request", payload)
            
            # 3. Wait for publish confirmation
            info.wait_for_publish()
            logger.info(f"[{printer_name}] STOP COMMAND CONFIRMED SENT (Seq: {seq_id})")
            
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

        # Verbose heartbeat (Optional: comment out if too noisy)
        print(f"[{printer_name}] State: {gcode_state} | Layer: {layer_num} | ID: {subtask_id}", end='\r')

        if gcode_state == 'RUNNING' and layer_num >= 1:
            if self.checked_prints.get(device_id) != subtask_id:
                print(f"\n[{printer_name}] TRIGGERED! Verifying print {subtask_id}...")
                client = next((c for c in self.clients if c.device_id == device_id), None)
                if client:
                    threading.Thread(target=self.enforce_rules, args=(device_id, client)).start()
                    self.checked_prints[device_id] = subtask_id
        
        if gcode_state in ['IDLE', 'FINISH', 'FAILED'] and device_id in self.checked_prints:
            del self.checked_prints[device_id]
            logger.info(f"\n[{printer_name}] Print finished/stopped. Monitoring for next job.")

    def start(self):
        printers = [printer1, printer2]
        logger.info(f"Starting Printer Police (Final) for UID: {USER_UID}")

        for serial in printers:
            client = MQTTClient(username=USER_UID, access_token=self.token, device_id=serial, on_message=self.on_message)
            client.connect(blocking=False)
            time.sleep(1)
            client.request_full_status()
            self.clients.append(client)
            logger.info(f"Connected to {PRINTER_MAP.get(serial, serial)}")

        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            for client in self.clients: client.disconnect()

if __name__ == "__main__":
    monitor = PrinterMonitor()
    monitor.start()