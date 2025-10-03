# BambuControl v3
Version 3 of BambuControl improves the authorization system by introducing fuzzy matching algorithms. This update addresses the issue of valid users being flagged as unauthorized due to minor typos or spelling variations in their log submissions.

## What’s New in v3
### Fuzzy Matching
Previous versions relied on exact string matching. If an authorized student named "John Smith" accidentally typed "Jon Smith" or "John Smtih", the system would reject them.

v3 implements the **Levenshtein Distance** algorithm to calculate the similarity between the submitted name and the authorized users list.
* **Threshold:** The system currently accepts matches with an edit distance of 3 or less.
* **Benefit:** Reduces false positives for "Not Authorized" alerts caused by simple human error.

## File Structure
File Structure on Google Apps Script
```
/ 
├── code.gs
├── NoEmail.html
└── StartEmail.html
```

### code.gs
Contains all Apps Script logic for v3.

`levenshtein(a, b)`
A helper function that calculates the minimum number of single-character edits (insertions, deletions, or substitutions) required to change string `a` into string `b`.

`FUZZYMATCH(...)`
Replaces the `MATCH` function from v1 and v2.

**Purpose:**
* Iterates through the "Authorized Users" list.
* Calculates the Levenshtein distance for both First and Last names against the submitted data.
* Returns the email address of the closest match if the total edit score is ≤ 3.
* Returns "Not Authorized" if no close match is found.

**Usage:**
Update the formula in the "Logs" sheet (typically Column D) to:
```
=FUZZYMATCH(B2, C2, 'Authorized Users'!B2:B, 'Authorized Users'!A2:A, 'Authorized Users'!C2:C)
```
`sendEmail()`
The email logic remains the same as v2, supporting both:
1.  **Unauthorized Print Alert:** Notifies staff if the fuzzy match returns "Not Authorized".
2.  **Authorized Print Confirmation:** Notifies the matched student (via the returned email) to verify the print job.

### Email Templates
* **NoEmail.html:** Unchanged. Sent to admins for unauthorized prints.
* **StartEmail.html:** Unchanged. Sent to students for authorized prints.

## Deployment Notes
* **Script Update:** Replace the entire contents of `code.gs` with the v3 code.
* **Spreadsheet Formula Update:** You **must** update the formula in the "Logs" sheet to use `=FUZZYMATCH(...)` instead of `=MATCH(...)`.
* **No Schema Changes:** The columns in the spreadsheet remain the same.

## Upgrade Notes (v2 → v3)
1.  Replace `code.gs` with the v3 implementation.
2.  In the Google Sheet, go to the "Logs" sheet.
3.  Update the cell D2 (or the first row of the Email column) to use the `FUZZYMATCH` function.
4.  Drag/fill the new formula down the column.