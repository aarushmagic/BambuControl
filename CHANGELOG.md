# Changelog

All notable changes to **BambuControl** are documented in this file.

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
- Introduced out-of-band verification via institute email to mitigate
  name-based impersonation of authorized users.
- Enables rapid detection and cancellation of fraudulent prints.

### Notes
- No spreadsheet schema changes required.
- Existing v1 deployments can be upgraded by replacing the script and
  adding the new email template.

---

## v1 – Initial Release

### Added
- Google Apps Script–based authorization system for Bambu Lab printers.
- Custom spreadsheet function for matching print submissions against
  an authorized users list.
- Automated email alerts to administrators for unauthorized print jobs.
- Locking mechanism to prevent duplicate email notifications.

### Limitations
- Authorization based solely on exact first and last name matching.
- No student-facing notifications.
- No real-time prevention of impersonation.

---