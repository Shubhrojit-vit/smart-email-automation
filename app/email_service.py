import smtplib
from email.message import EmailMessage
import os
import mimetypes

def send_email(sender_email, app_password, receiver_email, subject, body, attachment_path=None):
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg.set_content(body)

    if attachment_path and os.path.exists(attachment_path):
        ctype, encoding = mimetypes.guess_type(attachment_path)
        if ctype is None or encoding is not None:
            ctype = 'application/octet-stream'
        maintype, subtype = ctype.split('/', 1)
        with open(attachment_path, 'rb') as f:
            msg.add_attachment(f.read(),
                               maintype=maintype,
                               subtype=subtype,
                               filename=os.path.basename(attachment_path))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender_email, app_password)
        smtp.send_message(msg)
    return True

def test_smtp_connection(email, app_password, smtp_server="smtp.gmail.com", port=465):
    try:
        with smtplib.SMTP_SSL(smtp_server, port) as smtp:
            smtp.login(email, app_password)
        return True
    except Exception:
        return False
