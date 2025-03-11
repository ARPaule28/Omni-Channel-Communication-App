from flask import Flask, request, jsonify
import psycopg2
import os

app = Flask(__name__)

def get_db_connection():
    conn = psycopg2.connect(
        host="localhost",
        database="omni_channel_db",
        user="postgres",
        password="password"  # Replace with actual password or use environment variables
    )
    return conn

@app.route('/webhook/sms', methods=['POST'])
def receive_sms():
    data = request.form
    sender_phone = data['From']
    receiver_phone = data['To']
    content = data['Body']
    
    # Save the received SMS to the database
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get sender and receiver user IDs
    cur.execute("SELECT id FROM users WHERE phone_number = %s", (sender_phone,))
    sender_result = cur.fetchone()
    sender_id = sender_result[0] if sender_result else None
    
    cur.execute("SELECT id FROM users WHERE phone_number = %s", (receiver_phone,))
    receiver_result = cur.fetchone()
    receiver_id = receiver_result[0] if receiver_result else None
    
    # Save message to database
    cur.execute("""
    INSERT INTO messages (sender_id, receiver_id, message_type, content, status)
    VALUES (%s, %s, 'sms', %s, 'received')
    """, (sender_id, receiver_id, content))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    app.run(port=5000)