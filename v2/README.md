# BambuControl v2
Version 2 of BambuControl extends the core authorization system introduced in v1 by adding print-start confirmation emails for authorized users. This feature helps detect and deter name impersonation, where unauthorized users submit print jobs using the names of authorized students.

## What’s New in v2
### Print Start Confirmation Emails
For every authorized print submission:
* An email is automatically sent to the student’s institute email address
* The email confirms:
    * Printer used
    * File name
    * Approximate completion time
* Students are instructed to reply immediately if the print was not started by them

This enables staff to:
* Cancel fraudulent prints early
* Investigate misuse
* Protect authorized students from privilege loss due to impersonation

### Security Motivation
In v1, unauthorized users could bypass detection by submitting print jobs under the names of authorized students.

v2 mitigates this risk by introducing out-of-band verification:
* Only the legitimate student has access to their institute email
* Any impersonation attempt triggers a real-time alert to the victim
* Staff can intervene before material or printer time is wasted

## File Structure
File Structure on Google Apps Script
```
/
├── code.gs
├── NoEmail.html
└── StartEmail.html
```
### code.gs
Contains all Apps Script logic for v1.

Updated Email Logic (`sendEmail()`)

The `sendEmail()` function now supports two distinct email paths:
#### 1. Unauthorized Print Alert (Staff)

Trigger condition
```js
emailAddress == "Not Authorized"
```
Behavior:
* Sends an alert email to administrators
* Uses NoEmail.html
* Marks the log entry as “Email Sent” to prevent duplicates

#### 2. Authorized Print Confirmation (Student)
Trigger condition
```js
emailAddress.includes("@")
```
Behavior:
* Sends a confirmation email to the student
* Uses StartEmail.html
* Includes:
    * Student’s first name
    * Printer name
    * File name
    * Estimated completion time
* Encourages immediate reply if the print is not theirs

### StartEmail.html
An HTML email template sent to authorized students when their print begins.

Injected Variables:
* `firstName`
* `printer`
* `fileName`
* `endTime`

Key Features:
* Clear impersonation warning
* Explicit call to action
* Reply-to set to program administrators

This template is rendered dynamically using `HtmlService`.

## Deployment Notes
* The same “Email Sent” column is used for both staff and student emails
* Only one email is sent per log entry

Requires Google Apps Script authorization for:
* Spreadsheet access
* Sending emails

## Upgrade Notes (v1 → v2)
* No spreadsheet schema changes required
* Add `StartEmail.html`
* Replace `sendEmail()` with v2 implementation
* Update administrator email addresses as needed