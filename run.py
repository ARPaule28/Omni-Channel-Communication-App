import threading
import os
from app import flask_app

def run_flask():
    flask_app.run(host='0.0.0.0', port=5000)

def run_streamlit():
    # Use the full path to the Streamlit executable
    streamlit_path = r'C:\Users\angel\AppData\Roaming\Python\Python313\Scripts\streamlit.exe'
    os.system(f'"{streamlit_path}" run app.py')

if __name__ == '__main__':
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Run Streamlit in the main thread
    run_streamlit()