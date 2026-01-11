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