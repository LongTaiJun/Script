import smtplib
import os
import argparse
import re
import socket
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

# Define email account and password
GMAIL_USER = "test@gmail.com"
GMAIL_PASS = "xxxxxxxx"

# Log directory
LOG_DIR = '/tmp/mail/'

# Ensure the log directory exists
def ensure_log_directory():
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
        print(f"[INFO] Log directory {LOG_DIR} created.")
    else:
        print(f"[INFO] Log directory {LOG_DIR} already exists.")

# Check and set proxy if needed based on local IP
def check_and_set_proxy():
    local_ip = get_internal_ip()
    
    if local_ip.startswith("192.168.100"):
        os.environ['http_proxy'] = "http://192.168.100.10:7890"
        os.environ['https_proxy'] = "http://192.168.100.10:7890"
        os.environ['ALL_PROXY'] = "http://192.168.100.10:7890"
        print("[INFO] Proxy set as the local IP starts with 192.168.100.")
    else:
        print(f"[INFO] Current IP is {local_ip}, no proxy needed.")

# Get internal network IP address (skip 127.0.0.1)
def get_internal_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

# Function to log email details
def log_email_details(target_email, subject, body, attachments=None, cc_emails=None, bcc_emails=None):
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S-%f")[:-3]  # Accurate to milliseconds
    log_filename = f"mail-{timestamp}.log"
    log_path = os.path.join(LOG_DIR, log_filename)
    
    with open(log_path, 'w') as log_file:
        log_file.write(f"Time: {timestamp}\n")
        log_file.write(f"To: {target_email}\n")
        log_file.write(f"Subject: {subject}\n")
        log_file.write(f"Body: {body}\n")
        if cc_emails:
            log_file.write(f"CC: {', '.join(cc_emails)}\n")
        if bcc_emails:
            log_file.write(f"BCC: {', '.join(bcc_emails)}\n")
        if attachments:
            log_file.write(f"Attachments: {', '.join(attachments)}\n")
        log_file.write("Email sent successfully.\n")
    print(f"[INFO] Email log saved to {log_path}")

# Validate each email in a comma-separated list
def are_valid_emails(email_string):
    emails = email_string.split(',')
    for email in emails:
        email = email.strip()  # Remove any leading/trailing whitespace
        if not is_valid_email(email):
            print(f"[ERROR] Invalid email address: {email}")
            return False
    return True

# Validate email format for individual addresses
def is_valid_email(email):
    regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(regex, email)

# Function to send email
def send_email(target_email, subject, body, attachments=None, is_html=False, cc_emails=None, bcc_emails=None):
    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    recipients = [email.strip() for email in target_email.split(',')]
    msg['To'] = ', '.join(recipients)

    if cc_emails:
        cc_emails = [email.strip() for email in ','.join(cc_emails).split(',')]
        msg['Cc'] = ', '.join(cc_emails)
        recipients.extend(cc_emails)

    if bcc_emails:
        bcc_emails = [email.strip() for email in ','.join(bcc_emails).split(',')]
        recipients.extend(bcc_emails)

    msg['Subject'] = subject

    # Attach email body
    msg.attach(MIMEText(body, 'html' if is_html else 'plain'))

    # Handle attachments
    if attachments:
        for path in attachments:
            attach_file(msg, path)

    try:
        print("[INFO] Connecting to Gmail server...")
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, recipients, msg.as_string())
            print("[SUCCESS] Email sent successfully!")
            log_email_details(target_email, subject, body, attachments, cc_emails, bcc_emails)
    except smtplib.SMTPAuthenticationError:
        print("[ERROR] Login failed, please check email credentials.")
    except smtplib.SMTPException as e:
        print(f"[ERROR] Email sending failed: {e}")

# Attach a file to the email
def attach_file(msg, path):
    if os.path.isfile(path):
        try:
            with open(path, 'rb') as file:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(file.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename={os.path.basename(path)}')
                msg.attach(part)
                print(f"[INFO] Attachment {os.path.basename(path)} added successfully.")
        except Exception as e:
            print(f"[ERROR] Unable to read attachment '{path}': {e}")
    else:
        print(f"[ERROR] File '{path}' not found.")

# Parse command line arguments
def parse_arguments():
    parser = argparse.ArgumentParser(description='Send an email with optional attachments.')
    parser.add_argument('--to', help='Recipient email addresses (comma separated).', required=True)
    parser.add_argument('--subject', help='Email subject.', required=True)
    parser.add_argument('--body', help='Email body or file path.', required=True)
    parser.add_argument('--attachments', nargs='*', help='List of attachment file paths.')
    parser.add_argument('--cc', nargs='*', help='CC email addresses (optional, comma separated).')
    parser.add_argument('--bcc', nargs='*', help='BCC email addresses (optional, comma separated).')
    parser.add_argument('--html', action='store_true', help='Send body as HTML.')

    return parser.parse_args()

# Read body content from a file or return the string directly
def read_body_content(body_arg):
    if os.path.isfile(body_arg):
        try:
            with open(body_arg, 'r') as file:
                return file.read()
        except Exception as e:
            print(f"[ERROR] Unable to read body file {body_arg}: {e}")
            exit(1)
    return body_arg

if __name__ == '__main__':
    ensure_log_directory()  # Ensure the log directory exists
    check_and_set_proxy()   # Check and set proxy before sending email

    args = parse_arguments()

    # Validate recipient, cc, and bcc email formats
    if not are_valid_emails(args.to):
        exit(1)
    if args.cc and not are_valid_emails(','.join(args.cc)):
        exit(1)
    if args.bcc and not are_valid_emails(','.join(args.bcc)):
        exit(1)

    # Read the email body
    body_content = read_body_content(args.body)

    # Send the email
    send_email(
        target_email=args.to,
        subject=args.subject,
        body=body_content,
        attachments=args.attachments,
        is_html=args.html,
        cc_emails=args.cc,
        bcc_emails=args.bcc
    )
