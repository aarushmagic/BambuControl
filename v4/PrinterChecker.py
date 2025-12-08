import os
import sys
import time
import csv
import io
import requests
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict


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

# Time window (minutes) to consider a log entry "active" for a new print
LOG_TIME_WINDOW = 30 

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("PrinterGuard")

class PrinterMonitor:
    def __init__(self):
        self.token = os.getenv("token")
        if not self.token:
            logger.critical("Error: $token environment variable not set.")
            sys.exit(1)
        self.checked_prints = {}
        
        self.clients = []

    def fetch_latest_log(self, printer_name: str) -> Optional[Dict]:
        try:
            response = requests.get(SHEET_URL)
            response.raise_for_status()
            f = io.StringIO(response.text)
            reader = csv.DictReader(f)
            rows = list(reader)
            for row in reversed(rows):
                if row['Printer Name'].strip() == printer_name:
                    try:
                        date_str = row['Start Date'].strip()
                        time_str = row['Start Time'].strip()
                        log_dt = datetime.strptime(f"{date_str} {time_str}", "%m/%d/%Y %I:%M:%S %p")
                        if datetime.now() - log_dt < timedelta(minutes=LOG_TIME_WINDOW):
                            return row
                        else:
                            logger.warning(f"Found old log for {printer_name} from {log_dt}, ignoring.")
                            return None
                    except ValueError as e:
                        logger.error(f"Date parsing error in log: {e}")
                        continue
            
            return None

        except Exception as e:
            logger.error(f"Failed to fetch or parse log sheet: {e}")
            return None

    def enforce_rules(self, device_id: str, client: MQTTClient):
        printer_name = PRINTER_MAP.get(device_id, "Unknown")
        logger.info(f"Checking authorization for {printer_name}...")

        log_entry = self.fetch_latest_log(printer_name)

        if not log_entry:
            logger.warning(f"VIOLATION: No active log found for {printer_name}. Cancelling print.")
            self.cancel_print(client, printer_name, "Unlogged Print")
            return

        user_name = log_entry['FirstName']
        authorized = log_entry['AuthorizedUser(Yes/No)'].strip().lower()

        logger.info(f"Found log for {printer_name}: User={user_name}, Auth={authorized}")

        if authorized != "yes":
            logger.warning(f"VIOLATION: Unauthorized user ({user_name}) on {printer_name}. Cancelling print.")
            self.cancel_print(client, printer_name, f"Unauthorized: {user_name}")
        else:
            logger.info(f"Print authorized for {user_name}. Allowed to proceed.")

    def cancel_print(self, client: MQTTClient, printer_name: str, reason: str):
        logger.info(f"Stopping print on {printer_name} due to: {reason}")
        try:
            client.stop_print()
            logger.info("Stop command sent successfully.")
        except Exception as e:
            logger.error(f"Failed to send stop command: {e}")

    def on_message(self, device_id: str, data: dict):
        if 'print' not in data:
            return

        print_data = data['print']
        gcode_state = print_data.get('gcode_state', '')
        if gcode_state != 'RUNNING':
            if device_id in self.checked_prints and gcode_state in ['IDLE', 'FINISH', 'FAILED']:
                del self.checked_prints[device_id]
            return

        layer_num = print_data.get('layer_num')
        subtask_id = print_data.get('subtask_id', 'unknown')
        if layer_num == 1:
            if self.checked_prints.get(device_id) != subtask_id:
                logger.info(f"[{PRINTER_MAP.get(device_id)}] Detected Layer 1. Verifying log...")
                client = next((c for c in self.clients if c.device_id == device_id), None)
                if client:
                    threading.Thread(target=self.enforce_rules, args=(device_id, client)).start()
                    self.checked_prints[device_id] = subtask_id

    def start(self):
        printers = [printer1, printer2]
        logger.info(f"Starting Printer Police for UID: {USER_UID}")
        logger.info(f"Monitoring: {', '.join(PRINTER_MAP.values())}")

        for serial in printers:
            try:
                client = MQTTClient(
                    username=USER_UID,
                    access_token=self.token,
                    device_id=serial,
                    on_message=self.on_message
                )
                client.connect(blocking=False)
                self.clients.append(client)
                logger.info(f"Connected to {PRINTER_MAP.get(serial, serial)}")
            except Exception as e:
                logger.error(f"Failed to connect to {serial}: {e}")
                
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Stopping monitoring...")
            for client in self.clients:
                client.disconnect()

if __name__ == "__main__":
    monitor = PrinterMonitor()
    monitor.start()