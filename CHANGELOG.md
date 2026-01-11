# Changelog

All notable changes to **BambuControl** are documented in this file.

---

## v4 – Hardware Enforcement & Unified Structure

### Added
- **Hardware Enforcement (Python):** Introduced `PrinterChecker.py`, a local agent that monitors printers via MQTT.
- **Remote Kill Command:** The system can now actively cancel unauthorized or unlogged prints by sending a "stop" command to the printer.
- **Ghost Layer Protection:** Added logic to ignore calibration and bed leveling by verifying the print has sustained "Layer 1" for 15 seconds before checking authorization.
- **Unified File Structure:** Reorganized project into a `src/` directory containing both `google_apps_script` (Cloud) and `printer_guard` (Local) components.

### Changed
- **Architecture:** Transitioned from a purely logging/email-based system to a hybrid Cloud + Local enforcement system.
- **Documentation:** Consolidated version-specific READMEs into a single master `README.md`.

---

## v3 – Fuzzy Matching & Typos Tolerance

### Added
- Levenshtein Distance Algorithm: Implemented a helper function to calculate the edit distance between strings.
- `FUZZYMATCH` Function: A new custom spreadsheet function that replaces strict equality checks with a similarity score.

### Changed
- Authorization Logic: The system now tolerates minor typos (up to 3 character edits) in First or Last names.
- Spreadsheet Integration: The "Logs" sheet formula must be updated to call `=FUZZYMATCH()` instead of `=MATCH()`.

### Security & Usability
- Significantly reduces false alarms where authorized users were flagged as unauthorized due to minor spelling errors (e.g., "Jon" vs. "John").
- Maintains the impersonation detection features introduced in v2.

---

## v2 – Print Start Confirmation & Impersonation Detection

### Added
- Email notification sent to **authorized users** when a 3D print begins.
- New HTML email template (`StartEmail.html`) with program branding.
- Reply-to configuration allowing students to report unauthorized prints.

### Changed
- `sendEmail()` now sends:
  - Alert emails to administrators for unauthorized prints.
  - Confirmation emails to students for authorized prints.
- Email logic consolidated into a single scan of the print log.

### Security
- Introduced out-of-band verification via institute email to mitigate name-based impersonation of authorized users.
- Enables rapid detection and cancellation of fraudulent prints.

---

## v1 – Initial Release

### Added
- Google Apps Script–based authorization system for Bambu Lab printers.
- Custom spreadsheet function for matching print submissions against an authorized users list.
- Automated email alerts to administrators for unauthorized print jobs.
- Locking mechanism to prevent duplicate email notifications.

### Limitations
- Authorization based solely on exact first and last name matching.
- No student-facing notifications.
- No real-time prevention of impersonation.