/**
 * Calculates Levenshtein Distance between two strings.
 */
function levenshtein(a, b) {
  if (!a.length) {
    return b.length;
  }

  if (!b.length) {
    return a.length;
  }

  const matrix = [];

  for (let i = 0; i <= b.length; i++) {
    matrix[i] = [i];
  }

  for (let j = 0; j <= a.length; j++) {
    matrix[0][j] = j;
  }

  for (let i = 1; i <= b.length; i++) {
    for (let j = 1; j <= a.length; j++) {
      if (b.charAt(i - 1).toLowerCase() === a.charAt(j - 1).toLowerCase()) {
        matrix[i][j] = matrix[i - 1][j - 1];
      } else {
        matrix[i][j] = Math.min(
          matrix[i - 1][j - 1] + 1,
          matrix[i][j - 1] + 1,
          matrix[i - 1][j] + 1
        );
      }
    }
  }

  return matrix[b.length][a.length];
}

/**
 * Finds the closest match in a list of authorized people.
 *
 * @param {string} firstName The first name to check.
 * @param {string} lastName The last name to check.
 * @param {Range} authorizedFirstNames Column of authorized first names.
 * @param {Range} authorizedLastNames Column of authorized last names.
 * @param {Range} authorizedValues Column of values to return (e.g., emails).
 * @return The matched authorized value, or "Not Authorized".
 * 
 * Usage:
 *   =FUZZYMATCH(B2, C2, 'Authorized People'!A2:A, 'Authorized People'!B2:B, 'Authorized People'!C2:C)
 */
function FUZZYMATCH(firstName, lastName, authorizedFirstNames, authorizedLastNames, authorizedValues) {
  const fNames = authorizedFirstNames.map(r => r[0]);
  const lNames = authorizedLastNames.map(r => r[0]);
  const vals = authorizedValues.map(r => r[0]);

  let bestIndex = -1;
  let bestScore = 999;

  for (let i = 0; i < fNames.length; i++) {
    const fScore = levenshtein(String(firstName.trim()), String(fNames[i] || ""));
    const lScore = levenshtein(String(lastName.trim()), String(lNames[i] || ""));
    const total = fScore + lScore;

    if (total < bestScore) {
      bestScore = total;
      bestIndex = i;
    }
  }

  if (bestScore <= 3) {
    return vals[bestIndex];
  } else {
    return "Not Authorized";
  }
}


/**
 * Scans the 'Logs' sheet for unauthorized users and sends alert emails.
 * This function acquires a script lock to prevent race conditions, iterates through 
 * the log data, and identifies rows where the email address is "Not Authorized". 
 * If found, it compiles an HTML email using the 'NoEmail' template and sends it 
 * to the administrators.
 *
 * In addition, for authorized print jobs, this function sends a confirmation
 * email to the student's institute email address using the 'StartEmail' template.
 * This serves as an out-of-band verification mechanism to detect name-based
 * impersonation of authorized users.
 *
 * Finally, the function updates the 'Sent' column (L) to true so repeat
 * emails are not sent for the same log entry.
 *
 * @return {void} No return value.
 */
function sendEmail() {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(30000);
  }
  catch (e) {
    console.log('Could not obtain lock after 30 seconds.');
    return;
  }

  const sheet = SpreadsheetApp.getActiveSpreadsheet();
  SpreadsheetApp.setActiveSheet(sheet.getSheetByName('Logs'));
  const lastRow = parseInt(sheet.getLastRow());
  const formRange = sheet.getRange(`B2:J${lastRow}`);
  const formData = formRange.getValues();
  const sentRange = sheet.getRange(`L2:L${lastRow}`);
  const sentData = sentRange.getValues();


  for (let i = 0; i < formData.length; i++) {
    const row = formData[i];
    var [firstName, lastName, emailAddress, printer, date, time, duration, endTime, fileName] = row;
    const sent = sentData[i][0];

    if (sent == true || !emailAddress) {
      continue;
    }

    sentData[i][0] = true;

    if (emailAddress == "Not Authorized") {
      const template = HtmlService.createTemplateFromFile('NoEmail');
      template.fullName = firstName + " " + lastName;
      template.printer = printer;
      template.fileName = fileName;
      const message = template.evaluate().getContent();
      MailApp.sendEmail({
        name: 'Organization 3D Printer',
        to: "administrator@example.com",
        subject: "3D Print Issue on " + printer,
        htmlBody: message
      });
    } else if (emailAddress.includes("@")) {
      const template = HtmlService.createTemplateFromFile('StartEmail');
      template.firstName = firstName;
      template.printer = printer;
      template.endTime = endTime.getHours() + ":" + endTime.getMinutes();
      template.fileName = fileName;
      const message = template.evaluate().getContent();
      MailApp.sendEmail({
        name: 'Organization 3D Printer',
        to: emailAddress.trim(),
        subject: "3D Print Started on " + printer,
        htmlBody: message,
        replyTo: 'administrator@example.com'
      });
    }
  }

  sentRange.setValues(sentData);
  SpreadsheetApp.flush();

  lock.releaseLock();

  return;
}

/**
 * Receives log data from the Python script via HTTP POST and records it in the 'Activity' sheet.
 * * This function acts as a webhook listener. It acquires a script lock to prevent concurrent 
 * writes from overlapping, parses the JSON payload containing the print job details, 
 * and appends a new row with the timestamp, printer name, user, print time, and enforcement action.
 *
 * @param {Object} e The event parameter for the web app, containing the postData.
 * @return {TextOutput} A JSON response indicating whether the operation was a 'success' or 'error'.
 */
function doPost(e) {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(30000); 
  } catch (e) {
    return ContentService.createTextOutput(JSON.stringify({result: 'error', error: 'Lock timeout'}));
  }

  try {
    const params = JSON.parse(e.postData.contents);
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    let sheet = ss.getSheetByName("Activity");
    sheet.insertRowAfter(1);
    if (sheet.getLastRow() > 2) {
      sheet.getRange("A3:G3").copyFormatToRange(sheet, 1, 7, 2, 2);
    } else {
      sheet.getRange("A2:G2")
           .setFontWeight("normal")
           .setBackground(null);
    }
    sheet.getRange(2, 1, 1, 7).setValues([[
      params.timestamp, 
      params.printer, 
      params.user, 
      params.print_time,    
      params.action, 
      params.action_success,
      params.reason
    ]]);
    
    return ContentService.createTextOutput(JSON.stringify({result: 'success'}));
    
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({result: 'error', error: error.toString()}));
  } finally {
    lock.releaseLock();
  }
}