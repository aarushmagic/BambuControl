# BambuControl v1
Version 1 of BambuControl provides a lightweight authorization check for Bambu Lab 3D printer usage using Google Apps Script and Google Sheets. It validates print log submissions against a manually maintained list of authorized users and alerts administrators when unauthorized usage is detected.

## Overview
This version implements two core features:
1. Authorization Matching
* Matches submitted first and last names against an authorized users list.
* Returns the associated email address if authorized.
* Flags unauthorized users as "Not Authorized".
2. Automated Alerting
* Scans print logs for unauthorized prints.
* Sends an alert email to administrators.
* Prevents duplicate alerts for the same log entry.

## File Structure
File Structure on Google Apps Script
```
/
├── code.gs
└── NoEmail.html
```
### code.gs
Contains all Apps Script logic for v1.

`MATCH(...)`
A custom spreadsheet function used to determine whether a user is authorized and display institute email addresses for verified users.

**Purpose:**
* Compares submitted first and last names against the “Authorized Users” sheet.
* Returns a corresponding email address if a match is found.
* Returns "Not Authorized" otherwise.

Usage (Column D of "Logs"): 
```
=MATCH(B2, C2, 'Authorized Users'!B2:B, 'Authorized Users'!A2:A, 'Authorized Users'!C2:C)
```

`sendEmail()`
Scans the Logs sheet for unauthorized print jobs and sends alert emails.

**Behavior:**
* Uses a script lock to prevent race conditions.
* Checks each log entry where:
    * Authorization result = "Not Authorized"
    * Alert has not already been sent
* Sends an HTML email to administrators using the NoEmail.html template for unauthorized prints.
* Marks the row as “Email Sent” to prevent repeat notifications.

**Intended Trigger:**
On Form Submit

### NoEmail.html
HTML email template used for unauthorized print alerts.

Injected Variables:
* `fullName` – User’s full name
* `printer` – Printer name
* `fileName` – Print file name

This template is rendered dynamically using `HtmlService`.

## Deployment Notes
This version assumes:
* No disambiguation for duplicate names.
* Email recipient addresses are hardcoded and must be updated before deployment.

Requires Google Apps Script authorization for:
* Spreadsheet access
* Sending emails