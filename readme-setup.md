# Omni-Channel Communication App

A streamlit-based application that supports multiple communication channels including email, SMS, chat, and calls.

## Features

- Email sending & receiving with attachment support
- SMS sending & receiving with attachment support
- Chat messaging with attachment support
- Inbound & outbound calls
- Unified inbox view

## Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/Omni-Channel-Communication-App.git
cd Omni-Channel-Communication-App
```

### 2. Set Up a Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Up PostgreSQL Database

- Install PostgreSQL if not already installed
- Create a new database:

```bash
createdb omnichannel
```

### 5. Create a .env File

Create a `.env` file in the root directory with the following variables:

```
DB_HOST=localhost
DB_NAME=omnichannel
DB_USER=postgres
DB_PASSWORD=your_password

# For email functionality
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USERNAME=your-email@gmail.com
EMAIL_PASSWORD=your-app-password

# For SMS and call functionality (Twilio)
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_PHONE_NUMBER=your_twilio_phone
```

### 6. Run the Application

```bash
streamlit run app.py
```

## Demo Users

The application automatically creates two demo users:

1. Username: `user1`, Password: `password1`
2. Username: `user2`, Password: `password2`

You can use these accounts to test the communication features.

## Project Structure

- `app.py`: Main Streamlit application
- `requirements.txt`: Python dependencies
- `attachments/`: Directory where message attachments are stored

## Notes for Production

For a production environment, you would need to:
- Implement proper password hashing and authentication
- Set up actual email and SMS services (like SendGrid, Twilio)
- Configure HTTPS for secure connections
- Implement rate limiting and security measures
