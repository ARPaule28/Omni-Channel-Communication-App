# app.py - Main Streamlit application file

import streamlit as st
import psycopg2
import os
import uuid
import base64
from datetime import datetime
from twilio.rest import Client
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import imaplib
import email
from email.header import decode_header
from O365 import Account, FileSystemTokenBackend, Message
from twilio.twiml.voice_response import VoiceResponse
from flask import Flask, request
from threading import Thread
from dotenv import load_dotenv

load_dotenv()  # Add this near the top of your file, after imports

# Initialize Flask app
flask_app = Flask(__name__)

# Twilio credentials
account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')
twilio_number = os.getenv('TWILIO_PHONE_NUMBER')
client = Client(account_sid, auth_token)

# Database connection
def get_db_connection():
    conn = psycopg2.connect(
        host="localhost",
        database="omni_channel_db",
        user="postgres",
        password=os.getenv('DB_PASSWORD')
    )
    return conn

# Initialize database tables
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Create users table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(50) UNIQUE NOT NULL,
        email VARCHAR(100) UNIQUE NOT NULL,
        phone_number VARCHAR(20) UNIQUE NOT NULL,
        password VARCHAR(100) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create messages table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id SERIAL PRIMARY KEY,
        sender_id INTEGER REFERENCES users(id),
        receiver_id INTEGER REFERENCES users(id),
        message_type VARCHAR(20) NOT NULL,  -- 'email', 'sms', 'chat', 'call'
        content TEXT,
        attachment_path TEXT,
        status VARCHAR(20) NOT NULL,  -- 'sent', 'delivered', 'read'
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create calls table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS calls (
        id SERIAL PRIMARY KEY,
        caller_id INTEGER REFERENCES users(id),
        receiver_phone VARCHAR(20),
        start_time TIMESTAMP,
        end_time TIMESTAMP,
        status VARCHAR(20),  -- 'ongoing', 'completed', 'missed'
        direction VARCHAR(10),  -- 'inbound', 'outbound'
        call_sid VARCHAR(34),  -- Twilio Call SID
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Insert demo users if they don't exist
    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        cur.execute("""
        INSERT INTO users (username, email, phone_number, password)
        VALUES 
        ('user1', 'user1@example.com', '+1234567890', 'password1'),
        ('user2', 'user2@example.com', '+1987654321', 'password2')
        """)
    
    conn.commit()
    cur.close()
    conn.close()

# Add a route for the root URL
@flask_app.route('/')
def index():
    return "Welcome to the Omni-Channel Communication App!"

# Add a route for the favicon
@flask_app.route('/favicon.ico')
def favicon():
    return '', 204

# Function to handle incoming calls
@flask_app.route("/incoming-call", methods=["POST"])
def incoming_call():
    # Get call details from Twilio
    from_number = request.form.get('From', '')
    print(f"Incoming call from: {from_number}")
    
    # Look up the caller in the database
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username FROM users WHERE phone_number = %s", (from_number,))
    caller = cur.fetchone()
    
    # Find user2 to receive the call
    cur.execute("SELECT phone_number FROM users WHERE username = 'user2'")
    receiver = cur.fetchone()
    receiver_phone = receiver[0] if receiver else None
    
    # Record the call in database
    if caller and receiver_phone:
        cur.execute("""
        INSERT INTO calls (caller_id, receiver_phone, start_time, status, direction)
        VALUES (%s, %s, NOW(), 'ongoing', 'inbound')
        RETURNING id
        """, (caller[0], receiver_phone))
        call_id = cur.fetchone()[0]
        conn.commit()
        print(f"Call recorded with ID: {call_id}")
    
    cur.close()
    conn.close()
    
    # Create TwiML response to forward the call to user2's phone number
    response = VoiceResponse()
    response.say("Hello, this is a call from the Omni-Channel Communication App.")
    response.dial(receiver_phone)
    
    return str(response)

# Functions for handling each communication channel
def send_email(sender_id, receiver_email, subject, content, attachment=None):
    """
    Send an email to any email address, not just registered users.
    
    Args:
        sender_id: ID of the sending user
        receiver_email: Email address of the recipient (can be any email)
        subject: Subject line of the email
        content: Body content of the email
        attachment: Optional file attachment
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get sender details
    cur.execute("SELECT email, username FROM users WHERE id = %s", (sender_id,))
    sender_data = cur.fetchone()
    sender_email = sender_data[0]
    sender_username = sender_data[1]
    
    # Check if receiver exists in our system
    cur.execute("SELECT id FROM users WHERE email = %s", (receiver_email,))
    receiver_result = cur.fetchone()
    receiver_id = receiver_result[0] if receiver_result else None
    
    # Save attachment if provided
    attachment_path = None
    if attachment is not None:
        # Save attachment to disk
        file_extension = attachment.name.split('.')[-1]
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        attachment_path = os.path.join("attachments", unique_filename)
        os.makedirs("attachments", exist_ok=True)
        
        with open(attachment_path, "wb") as f:
            f.write(attachment.getbuffer())
    
    # Save message to database
    cur.execute("""
    INSERT INTO messages (sender_id, receiver_id, message_type, content, subject, attachment_path, status)
    VALUES (%s, %s, 'email', %s, %s, %s, 'sent')
    """, (sender_id, receiver_id, content, subject, attachment_path))
    
    conn.commit()
    cur.close()
    conn.close()
    
    # Send the email using smtplib
    try:
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        smtp_username = os.getenv('GMAIL_USERNAME')
        smtp_password = os.getenv('GMAIL_APP_PASSWORD')
        
        # Create message
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = receiver_email
        msg["Subject"] = subject
        
        # Attach message body
        msg.attach(MIMEText(content, "plain"))
        
        # Attach file if provided
        if attachment_path:
            with open(attachment_path, "rb") as file:
                part = MIMEApplication(file.read(), Name=os.path.basename(attachment_path))
                part["Content-Disposition"] = f'attachment; filename="{os.path.basename(attachment_path)}"'
                msg.attach(part)
        
        # Send email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
        
        st.success(f"Email sent successfully from {sender_email} to {receiver_email}")
        return True
        
    except Exception as e:
        st.error(f"Error sending email: {str(e)}")
        return False

def send_sms(sender_id, receiver_id, content, attachment=None):
    """
    Send an SMS to any phone number, not just registered users.
    
    Args:
        sender_id: ID of the sending user
        receiver_id: ID of the receiving user
        content: Body content of the SMS
        attachment: Optional file attachment (for MMS)
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get sender and receiver details
    cur.execute("SELECT phone_number FROM users WHERE id = %s", (sender_id,))
    sender_phone = cur.fetchone()[0]
    
    cur.execute("SELECT phone_number FROM users WHERE id = %s", (receiver_id,))
    receiver_phone = cur.fetchone()[0]
    
    # Save attachment if provided
    attachment_path = None
    if attachment is not None:
        # Save attachment to disk
        file_extension = attachment.name.split('.')[-1]
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        attachment_path = os.path.join("attachments", unique_filename)
        os.makedirs("attachments", exist_ok=True)
        
        with open(attachment_path, "wb") as f:
            f.write(attachment.getbuffer())
    
    # Save message to database
    cur.execute("""
    INSERT INTO messages (sender_id, receiver_id, message_type, content, attachment_path, status)
    VALUES (%s, %s, 'sms', %s, %s, 'sent')
    """, (sender_id, receiver_id, content, attachment_path))
    
    conn.commit()
    cur.close()
    conn.close()
    
    # Send the SMS using Twilio
    try:
        account_sid = 'AC286c1c9bc019897af671fe9c3a558ccd'  # Replace with your Twilio Account SID
        auth_token = 'a2be9cec0c8b7d75ca4a73676eb23ad5'  # Replace with your Twilio Auth Token
        client = Client(account_sid, auth_token)
        
        message = client.messages.create(
            from_='+18508134976',  # Replace with your Twilio phone number
            body=content,
            to='+18777804236'
        )
        
        st.success(f"SMS sent successfully from {sender_phone} to {receiver_phone}")
        return True
        
    except Exception as e:
        st.error(f"Error sending SMS: {str(e)}")
        return False

def send_chat(sender_id, receiver_id, content, attachment=None):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Save attachment if provided
    attachment_path = None
    if attachment is not None:
        # Save attachment to disk
        file_extension = attachment.name.split('.')[-1]
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        attachment_path = os.path.join("attachments", unique_filename)
        os.makedirs("attachments", exist_ok=True)
        
        with open(attachment_path, "wb") as f:
            f.write(attachment.getbuffer())
        
        # Debugging: Print the attachment path
        print(f"Attachment saved at: {attachment_path}")
    
    # Debugging: Print the values to be inserted into the database
    print(f"Inserting into database: sender_id={sender_id}, receiver_id={receiver_id}, content={content}, attachment_path={attachment_path}")
    
    # Save message to database
    cur.execute("""
    INSERT INTO messages (sender_id, receiver_id, message_type, content, attachment_path, status)
    VALUES (%s, %s, 'chat', %s, %s, 'sent')
    """, (sender_id, receiver_id, content, attachment_path))
    
    conn.commit()
    cur.close()
    conn.close()
    
    st.success("Chat message sent")
    return True

def make_call(caller_id, receiver_phone, direction):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get caller details
    cur.execute("SELECT phone_number FROM users WHERE id = %s", (caller_id,))
    caller_phone = cur.fetchone()[0]
    
    # Make the call using Twilio
    try:
        account_sid = 'AC286c1c9bc019897af671fe9c3a558ccd'  # Replace with your Twilio Account SID
        auth_token = 'a2be9cec0c8b7d75ca4a73676eb23ad5'  # Replace with your Twilio Auth Token
        client = Client(account_sid, auth_token)
        
        call = client.calls.create(
            url='https://4824-64-224-134-197.ngrok-free.app/incoming-call',  # Replace with your ngrok URL
            to=receiver_phone,
            from_='+18508134976'  # Replace with your Twilio phone number
        )
        
        call_sid = call.sid
        
        # Record call in database
        cur.execute("""
        INSERT INTO calls (caller_id, receiver_phone, start_time, status, direction, call_sid)
        VALUES (%s, %s, %s, 'ongoing', %s, %s)
        RETURNING id
        """, (caller_id, receiver_phone, datetime.now(), direction, call_sid))
        
        call_id = cur.fetchone()[0]
        
        conn.commit()
        cur.close()
        conn.close()
        
        st.success(f"Call initiated from {caller_phone} to {receiver_phone}")
        return call_id
        
    except Exception as e:
        st.error(f"Error making call: {str(e)}")
        return None

def end_call(call_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get the call SID from the database
    cur.execute("SELECT call_sid FROM calls WHERE id = %s", (call_id,))
    call_sid = cur.fetchone()[0]
    
    # End the call using Twilio
    try:
        account_sid = 'AC286c1c9bc019897af671fe9c3a558ccd'  # Replace with your Twilio Account SID
        auth_token = 'a2be9cec0c8b7d75ca4a73676eb23ad5'  # Replace with your Twilio Auth Token
        client = Client(account_sid, auth_token)
        
        call = client.calls(call_sid).update(status='completed')
        
        # Update call record in database
        cur.execute("""
        UPDATE calls SET end_time = %s, status = 'completed'
        WHERE id = %s
        """, (datetime.now(), call_id))
        
        conn.commit()
        cur.close()
        conn.close()
        
        st.success("Call ended")
        return True
        
    except Exception as e:
        st.error(f"Error ending call: {str(e)}")
        return False

def get_messages(user_id, message_type=None):
    conn = get_db_connection()
    cur = conn.cursor()
    
    if message_type:
        cur.execute("""
        SELECT m.id, sender.username, receiver.username, m.message_type, m.content, m.attachment_path, m.status, m.created_at
        FROM messages m
        JOIN users sender ON m.sender_id = sender.id
        JOIN users receiver ON m.receiver_id = receiver.id
        WHERE (m.sender_id = %s OR m.receiver_id = %s) AND m.message_type = %s
        ORDER BY m.created_at DESC
        """, (user_id, user_id, message_type))
    else:
        cur.execute("""
        SELECT m.id, sender.username, receiver.username, m.message_type, m.content, m.attachment_path, m.status, m.created_at
        FROM messages m
        JOIN users sender ON m.sender_id = sender.id
        JOIN users receiver ON m.receiver_id = receiver.id
        WHERE m.sender_id = %s OR m.receiver_id = %s
        ORDER BY m.created_at DESC
        """, (user_id, user_id))
    
    messages = cur.fetchall()
    cur.close()
    conn.close()
    
    return messages

def get_calls(user_id, direction=None):
    conn = get_db_connection()
    cur = conn.cursor()
    
    if direction:
        cur.execute("""
        SELECT c.id, caller.username, c.receiver_phone, c.start_time, c.end_time, c.status, c.direction
        FROM calls c
        JOIN users caller ON c.caller_id = caller.id
        WHERE c.caller_id = %s AND c.direction = %s
        ORDER BY c.created_at DESC
        """, (user_id, direction))
    else:
        cur.execute("""
        SELECT c.id, caller.username, c.receiver_phone, c.start_time, c.end_time, c.status, c.direction
        FROM calls c
        JOIN users caller ON c.caller_id = caller.id
        WHERE c.caller_id = %s
        ORDER BY c.created_at DESC
        """, (user_id,))
    
    calls = cur.fetchall()
    cur.close()
    conn.close()
    
    return calls

def get_users():
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT id, username FROM users")
    users = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return users

# Function to fetch emails from an external email account
def fetch_emails(limit=5):
    email_user = os.getenv('GMAIL_USERNAME')
    email_password = os.getenv('GMAIL_APP_PASSWORD')
    imap_server = "imap.gmail.com"
    imap_port = 993
    
    # Connect to the server
    mail = imaplib.IMAP4_SSL(imap_server, imap_port)
    
    # Login to the account
    mail.login(email_user, email_password)
    
    # Select the mailbox you want to check
    mail.select("inbox")
    
    # Search for all emails in the inbox
    status, messages = mail.search(None, "ALL")
    
    # Convert messages to a list of email IDs
    email_ids = messages[0].split()
    
    # Limit the number of emails fetched to the latest 'limit' emails
    email_ids = email_ids[-limit:]
    
    emails = []
    
    for email_id in email_ids:
        # Fetch the email by ID
        status, msg_data = mail.fetch(email_id, "(RFC822)")
        
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                # Parse the email content
                msg = email.message_from_bytes(response_part[1])
                
                # Decode the email subject
                subject, encoding = decode_header(msg["Subject"])[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding if encoding else "utf-8")
                
                # Decode the email sender
                from_ = msg.get("From")
                
                # Get the email body and attachments
                body = ""
                attachments = []
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        content_disposition = str(part.get("Content-Disposition"))
                        
                        if "attachment" in content_disposition:
                            # Extract attachment
                            filename = part.get_filename()
                            if filename:
                                attachments.append(filename)
                                filepath = os.path.join("attachments", filename)
                                os.makedirs("attachments", exist_ok=True)
                                with open(filepath, "wb") as f:
                                    f.write(part.get_payload(decode=True))
                        elif content_type == "text/plain" and "attachment" not in content_disposition:
                            # Extract plain text email body
                            body = part.get_payload(decode=True).decode()
                        elif content_type == "text/html" and "attachment" not in content_disposition:
                            # Extract HTML email body
                            body = part.get_payload(decode=True).decode()
                else:
                    body = msg.get_payload(decode=True).decode()
                
                emails.append({
                    "from": from_,
                    "subject": subject,
                    "body": body,
                    "is_html": content_type == "text/html",
                    "attachments": attachments
                })
    
    # Close the connection and logout
    mail.close()
    mail.logout()
    
    return emails

def get_incoming_calls():
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
    SELECT c.id, caller.username, c.receiver_phone, c.start_time, c.status, c.direction
    FROM calls c
    JOIN users caller ON c.caller_id = caller.id
    WHERE c.direction = 'inbound' AND c.status = 'ongoing'
    ORDER BY c.start_time DESC
    """)
    
    calls = cur.fetchall()
    cur.close()
    conn.close()
    
    return calls

# Function to check for incoming calls
def check_incoming_calls(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check for ongoing inbound calls where this user is the receiver
    cur.execute("""
    SELECT c.id, u.username, u.phone_number
    FROM calls c
    JOIN users u ON c.caller_id = u.id
    WHERE c.receiver_id = %s AND c.status = 'ongoing' AND c.direction = 'inbound'
    AND c.end_time IS NULL
    ORDER BY c.start_time DESC
    LIMIT 1
    """, (user_id,))
    
    incoming_call = cur.fetchone()
    cur.close()
    conn.close()
    
    return incoming_call

# Main Streamlit app
def main():
    st.title("Omni-Channel Communication App")
    
    # Initialize database
    init_db()
    
    # Session state for login
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'user_id' not in st.session_state:
        st.session_state.user_id = None
    if 'username' not in st.session_state:
        st.session_state.username = None
    
    # Login section
    if not st.session_state.logged_in:
        st.header("Login")
        
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        
        if st.button("Login"):
            # Verify login (in real app, you'd hash passwords)
            conn = get_db_connection()
            cur = conn.cursor()
            
            cur.execute("SELECT id, username FROM users WHERE username = %s AND password = %s", (username, password))
            user = cur.fetchone()
            
            cur.close()
            conn.close()
            
            if user:
                st.session_state.logged_in = True
                st.session_state.user_id = user[0]
                st.session_state.username = user[1]
                st.success(f"Welcome {user[1]}!")
                st.rerun()
            else:
                st.error("Invalid username or password")
    
    # Main app after login
    else:
        st.sidebar.title(f"Welcome {st.session_state.username}")
        
        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.user_id = None
            st.session_state.username = None
            st.rerun()
        
        # Communication options
        option = st.sidebar.selectbox(
            "Select Communication Channel",
            ["Email", "SMS", "Chat", "Calls", "All Messages"]
        )
        
        # Get list of users for recipient selection
        users = get_users()
        user_options = [(user[0], user[1]) for user in users if user[0] != st.session_state.user_id]
        
        if option == "Email":
            st.header("Email")
            
            # Compose Email section
            st.subheader("Compose Email")
            recipient_email = st.text_input("To")
            subject = st.text_input("Subject")
            content = st.text_area("Message")
            attachment = st.file_uploader("Attachment")
            
            if st.button("Send Email"):
                if send_email(st.session_state.user_id, recipient_email, subject, content, attachment):
                    st.success("Email sent successfully!")
            
            # Add a separator between compose and inbox
            st.markdown("---")
            
            # Inbox section
            st.subheader("Inbox")
            emails = fetch_emails(limit=2)
            
            for email in emails:
                with st.container():
                    st.markdown("""
                    ---
                    **From:** {}  
                    **Subject:** {}
                    """.format(email['from'], email['subject']))
                    
                    with st.expander("View Message"):
                        # Display the content without HTML tags
                        from bs4 import BeautifulSoup
                        
                        if email['is_html']:
                            soup = BeautifulSoup(email['body'], 'html.parser')
                            clean_text = soup.get_text(separator='\n')
                            st.write(clean_text)
                        else:
                            st.write(email['body'])
                        
                        if email['attachments']:
                            st.markdown("**Attachments:**")
                            for attachment in email['attachments']:
                                st.download_button(
                                    label=f"📎 {attachment}",
                                    data=open(os.path.join("attachments", attachment), "rb"),
                                    file_name=attachment
                                )
                    st.markdown("---")
        
        elif option == "SMS":
            st.header("SMS")
            
            # Compose SMS section
            st.subheader("Send SMS")
            recipient = st.selectbox("To", user_options, format_func=lambda x: x[1])
            content = st.text_area("Message")
            
            if st.button("Send SMS"):
                if send_sms(st.session_state.user_id, recipient[0], content):
                    st.success("SMS sent successfully!")
            
            # Show SMS history
            st.subheader("SMS History")
            sms_messages = get_messages(st.session_state.user_id, "sms")
            
            for sms in sms_messages:
                with st.expander(f"From: {sms[1]} - To: {sms[2]} - {sms[7].strftime('%Y-%m-%d %H:%M')}"):
                    st.write(sms[4])  # Content
                    
                    if sms[5]:  # Attachment path
                        st.write("Has attachment")
        
        elif option == "Chat":
            st.header("Chat")
            
            # Display chat history
            chat_messages = get_messages(st.session_state.user_id, "chat")
            filtered_messages = [msg for msg in chat_messages if 
                                (msg[1] == recipient[1] or msg[2] == recipient[1])]
            
            for msg in reversed(filtered_messages):
                if msg[1] == st.session_state.username:
                    st.write(f"You: {msg[4]}")
                else:
                    st.write(f"{msg[1]}: {msg[4]}")
                
                if msg[5]:  # Attachment
                    attachment_path = msg[5]
                    if attachment_path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                        st.image(attachment_path, caption="Attachment", use_container_width=True)
                    else:
                        st.markdown(f"[Download Attachment]({attachment_path})")
            
            # Send chat message
            content = st.text_input("Type a message")
            attachment = st.file_uploader("Attachment")
            
            if st.button("Send"):
                if send_chat(st.session_state.user_id, recipient[0], content, attachment):
                    st.rerun()
        
        elif option == "Calls":
            st.header("Calls")
            
            # Make call section
            st.subheader("Make a Call")
            receiver_phone = st.text_input("Enter phone number to call")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Make Outbound Call"):
                    call_id = make_call(st.session_state.user_id, receiver_phone, "outbound")
                    st.session_state.current_call = call_id
                    st.success(f"Calling {receiver_phone}...")
            
            with col2:
                if st.button("End Call") and 'current_call' in st.session_state:
                    end_call(st.session_state.current_call)
                    st.session_state.pop('current_call')
            
            # Display incoming calls
            st.subheader("Incoming Calls")
            incoming_call = check_incoming_calls(st.session_state.user_id)
            if incoming_call:
                call_id, caller_name, caller_phone = incoming_call
                st.warning(f"Incoming call from {caller_name} ({caller_phone})")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Answer Call"):
                        # In a real app, you would connect the call
                        st.success(f"Connected to call with {caller_name}")
                
                with col2:
                    if st.button("Decline Call"):
                        # Update call status
                        conn = get_db_connection()
                        cur = conn.cursor()
                        cur.execute("""
                        UPDATE calls SET status = 'missed', end_time = NOW()
                        WHERE id = %s
                        """, (call_id,))
                        conn.commit()
                        cur.close()
                        conn.close()
                        st.rerun()
            
            # Call history
            st.subheader("Call History")
            calls = get_calls(st.session_state.user_id)
            
            for call in calls:
                direction = "Outgoing" if call[1] == st.session_state.username else "Incoming"
                status = call[5]
                duration = "N/A"
                
                if call[3] and call[4]:  # start_time and end_time
                    duration = str(call[4] - call[3])
                
                st.write(f"{direction} call with {call[2]}")
                st.write(f"Status: {status}, Duration: {duration}")
                st.write("---")
        
        elif option == "All Messages":
            st.header("All Communications")
            
            all_messages = get_messages(st.session_state.user_id)
            all_calls = get_calls(st.session_state.user_id)
            
            # Combine and sort by date
            all_comms = []
            
            for msg in all_messages:
                all_comms.append({
                    'type': msg[3],  # message_type
                    'from': msg[1],  # sender username
                    'to': msg[2],    # receiver username
                    'content': msg[4],
                    'attachment': msg[5],
                    'time': msg[7],
                    'display': f"{msg[3].upper()}: {msg[1]} → {msg[2]}"
                })
            
            for call in all_calls:
                all_comms.append({
                    'type': 'call',
                    'from': call[1],  # caller username
                    'to': call[2],    # receiver username
                    'content': f"Status: {call[5]}, Direction: {call[6]}",
                    'attachment': None,
                    'time': call[3],  # start_time
                    'display': f"CALL: {call[1]} → {call[2]}"
                })
            
            # Sort by time, newest first
            all_comms.sort(key=lambda x: x['time'], reverse=True)
            
            for comm in all_comms:
                with st.expander(f"{comm['display']} - {comm['time'].strftime('%Y-%m-%d %H:%M')}"):
                    st.write(comm['content'])
                    
                    if comm['attachment']:
                        st.write("Has attachment")

if __name__ == "__main__":
    # Run Flask app in a separate thread
    def run_flask():
        flask_app.run(port=5000)
    
    flask_thread = Thread(target=run_flask)
    flask_thread.start()
    
    # Run Streamlit app
    main()