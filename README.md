# BambuControl

BambuControl is a hybrid, software-based access-control system for Bambu Lab 3D printers. It monitors logged 3D print jobs and classifies them as originating from authorized or unauthorized users based on submitted print logs, enforcing rules via hardware commands and email alerts.

## Problem Statement
A university organization operates two Bambu X1C 3D printers for student use. Students are required to complete and pass online training before using the printers. However, preventing unauthorized use in an open, shared space is difficult.

**Technical Constraints:**
1.  **Connectivity:** Internet connectivity is required for remote monitoring.
2.  **Network Limitations:** Printers are on a WPA2-PSK network, preventing direct enterprise (802.1x) user authentication.
3.  **Data Limits:** Print logs only contain names and emails; no ID cards or passwords can be collected.

## System Architecture
BambuControl bridges the gap between a **Google Cloud** administrative backend and **Local Hardware** enforcement.

1.  **The Cloud (Google Apps Script):** Acts as the database and user-facing frontend. It stores the "Authorized Users" list, processes Google Form logs using fuzzy string matching, and handles email notifications.
2.  **The Enforcer (Python Script):** Runs on a local server (e.g., Raspberry Pi). It connects to the printers via MQTT, polls the Google Sheet for valid logs, and issues STOP commands to the printer if an unauthorized job is detected.

---

## Features

### 1. Fuzzy Authorization Logic
Previous iterations relied on exact string matching, causing false positives when students made typos (e.g., "Jon" vs. "John").
* **Algorithm:** Uses the **Levenshtein Distance** algorithm to calculate similarity.
* **Threshold:** Accepts matches with an edit distance of **3 or less**.
* **Benefit:** Significantly reduces false "Not Authorized" flags due to simple human error.

### 2. Impersonation Detection (Security)
To prevent unauthorized users from submitting logs under an authorized student's name:
* **Verification Email:** Every authorized print triggers an immediate email to the student's official institute address.
* **Action:** If the student did not start the print, they are instructed to reply immediately. This allows staff to cancel fraudulent prints and investigate misuse.

### 3. Hardware Enforcement
* **Active Monitoring:** The local Python script subscribes to the printer's MQTT feed.
* **Ghost Layer Protection:** The system waits until the printer reaches **Layer 1** and sustains it for 15 seconds before checking authorization. This prevents false alarms during calibration or bed leveling.
* **Remote Kill:** If a print is deemed unauthorized (or unlogged), the script sends a JSON payload to the printer to cancel the job immediately.

---

## File Structure

```text
/
├── src/
│   ├── Google Apps Script/
│   │   ├── code.gs           # Main logic (Fuzzy Match + Emails)
│   │   ├── NoEmail.html      # Template: Alert to admins
│   │   └── StartEmail.html   # Template: Confirmation to students
│   └── Python/
│       └── PrinterChecker.py # Local MQTT enforcement script
├── requirements.txt          # Python dependencies
└── README.md
```

## Deployment: Part 1 (Google Cloud)

### 1. Spreadsheet Setup

Create a Google Sheet with two tabs: `Logs` and `Authorized Users`.

**Sheet 1: Authorized Users**
Manually maintained list of trained students.
| LAST NAME | FIRST NAME | EMAIL |
| :--- | :--- | :--- |
| Smith | John | jsmith@example.edu |

**Sheet 2: Logs**
Receives data from a linked Google Form.

* **Columns A-B, D-E, G, J:** Populated by Form responses.
* **Column C (Institute Email):** Populated by the `FUZZYMATCH` script function.
* **Columns F, H, I:** Calculated formulas.

| Col | Header | Source/Formula |
| --- | --- | --- |
| A | Timestamp | Form Response |
| B | First Name | Form Response |
| C | Last Name | Form Response |
| D | Institute Email | `=FUZZYMATCH(B2, C2, 'Authorized Users'!B2:B, 'Authorized Users'!A2:A, 'Authorized Users'!C2:C)` |
| E | Printer Name | Form Response |
| F | Start Date | `=DATE(YEAR(A2), MONTH(A2), DAY(A2))` |
| G | Start Time | `=TIME(HOUR(A2), MINUTE(A2), SECOND(A2))` |
| H | Print Duration | Form Response (Format: HH:MM:SS) |
| I | End Time | `=G2+H2` |
| J | File Name | Form Response |
| L | Email Sent | Used by Script (Do not edit) |

*[Note: Adjust column references in formulas based on your exact layout]*.

### 2. Apps Script Installation

1. Open the Sheet, go to **Extensions > Apps Script**.
2. Copy the contents of `src/Google Apps Script/code.gs` into the editor.
3. Create two HTML files in the editor: `NoEmail.html` and `StartEmail.html` and paste the respective code.
4. **Update Email Addresses:** In `code.gs`, update the `administrator@example.com` variable to your actual admin email.
5. **Set Trigger:**
* Go to **Triggers** (alarm clock icon).
* Add Trigger: `sendEmail` | Head | On form submit.



### 3. Publish for Python Access

The local Python script needs to read the Logs to verify prints.

1. Go to **File > Share > Publish to web**.
2. Select "Logs" -> "Comma-separated values (.csv)". Copy the URL.
3. Select "Authorized Users" -> "Comma-separated values (.csv)". Copy the URL.
4. Save these URLs for Part 2.

---

## Deployment: Part 2 (Local Enforcement)

The `PrinterChecker.py` script runs on a local device (e.g., Raspberry Pi, PC) that is always on and connected to the internet.

*Note: This software has been tested on Bambu X1Cs running firmware version 01.08.02.00*

### 1. Prerequisites

* Python 3.9+
* Bambu Lab Account (User ID and Access Token)
    * More information: https://github.com/coelacant1/Bambu-Lab-Cloud-API
* Printer Serial Numbers
    *Note: This software has been tested on Bambu X1Cs running version 01.08.02.00*

### 2. Installation

```bash
# Clone the repo
git clone https://github.com/aarushmagic/BambuControl.git
cd bambucontrol

# Install dependencies
pip install -r requirements.txt
```

*(Requires `bambu-lab-cloud-api` and `requests`)*.

### 3. Configuration

Set the following Environment Variables. You can do this via a `.env` file or system export.

```bash
export PRINTER_SERIAL_1="00M00A123456789"
export PRINTER_SERIAL_2="00M00A987654321"
export PRINTER_NAME_1="Printer 1" #Must match printer name in google sheet
export PRINTER_NAME_2="Printer 2" #Must match printer name in google sheet
export BAMBU_USER_ID="12345678"
export BAMBU_ACCESS_TOKEN="your_access_token_here"
export LOG_SHEET_URL="https://docs.google.com/.../pub?gid=0&single=true&output=csv"
export AUTH_SHEET_URL="https://docs.google.com/.../pub?gid=123&single=true&output=csv"
```

### 4. Running the Guard

```bash
python src/Python/PrinterChecker.py
```

The script will now:

1. Connect to both printers via MQTT.
2. Monitor for active print jobs (Layer > 1).
3. Cross-reference the `LOG_SHEET_URL` to see if the current time falls within a valid print window for that printer.
4. Kill the print if no valid log is found or if the user is unauthorized.

---

## Disclaimer

BambuControl is an unofficial, independent project developed for the John H. Martinson Honors Program (JMHP) at the Georgia Institute of Technology. It is not affiliated with, endorsed by, or supported by Bambu Lab, Google, or any of their subsidiaries or partners in any way.

The software is provided as-is, without warranty of any kind. Use, modify, and deploy this code at your own risk.