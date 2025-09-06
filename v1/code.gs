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
 *   =MATCH(B2, C2, 'Authorized People'!A2:A, 'Authorized People'!B2:B, 'Authorized People'!C2:C)
 */
function MATCH(firstName, lastName, authorizedFirstNames, authorizedLastNames, authorizedValues) {
  if (!firstName || !lastName) {
    return "Not Authorized";
  }

  var searchFirst = firstName.toString().trim().toLowerCase();
  var searchLast = lastName.toString().trim().toLowerCase();

  for (var i = 0; i < authorizedFirstNames.length; i++) {
    var rowFirst = authorizedFirstNames[i][0];
    var rowLast = authorizedLastNames[i][0];

    if (!rowFirst || !rowLast) {
      continue;
    }

    var cleanRowFirst = rowFirst.toString().trim().toLowerCase();
    var cleanRowLast = rowLast.toString().trim().toLowerCase();

    if (searchFirst === cleanRowFirst && searchLast === cleanRowLast) {
      return authorizedValues[i][0];
    }
  }

  return "Not Authorized";
}


/**
 * Scans the 'Logs' sheet for unauthorized users and sends alert emails.
 * This function acquires a script lock to prevent race conditions, iterates through 
 * the log data, and identifies rows where the email address is "Not Authorized". 
 * If found, it compiles an HTML email using the 'NoEmail' template and sends it 
 * to the administrators. Finally, it updates the 'Sent' column (L) to true so repeat
 * emails are not sent.
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
    }
  }

  sentRange.setValues(sentData);
  SpreadsheetApp.flush();

  lock.releaseLock();

  return;
}