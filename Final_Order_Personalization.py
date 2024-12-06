import os
import gspread
import requests
import face_recognition
import pickle
import cv2
import sqlite3
import numpy as np
from google.oauth2.service_account import Credentials
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import threading
import json
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# === Telegram Bot Configuration ===
TOKEN = "7859837971:AAEiP-Hfo0mh6Qn6CFOqmCUJ1jkXIB5xqWA"
CHAT_ID = "6861255295"
URL = f"https://api.telegram.org/bot{TOKEN}/"

# === Google Sheets and Drive Configuration ===
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
CREDENTIALS_FILE = 'credentials.json'
SHEET_ID = '1RAeSlGL50t6DuOLLKYG3r65WUbOxNj4I_paCWDT6828'

# === Authenticate with Google Sheets ===
credentials = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
client = gspread.authorize(credentials)
sheet = client.open_by_key(SHEET_ID)
worksheet = sheet.get_worksheet(0)

# === Flags and Constants ===
order_update_complete = False  # Flag to track order updates
SAVE_DIR = 'google_sheet_images'  # Directory to store images
os.makedirs(SAVE_DIR, exist_ok=True)  # Ensure SAVE_DIR exists

# === SQLite Database Setup ===
DB_FILE = "face_recognition.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()

# === Create database table ===
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    makanan TEXT NOT NULL,
    encoding BLOB NOT NULL
)
''')
conn.commit()

# === Helper Functions ===

def extract_file_id(image_url):
    """
    Extract the file ID from a Google Drive URL.
    Supports both `id=` query parameter and `/file/d/` format.
    """
    if "id=" in image_url:
        return parse_qs(urlparse(image_url).query).get('id', [None])[0]
    elif "/file/d/" in image_url:
        return image_url.split("/file/d/")[1].split('/')[0]
    return None


def download_image(image_url, save_path):
    """
    Download an image from Google Drive and save it locally.
    """
    file_id = extract_file_id(image_url)
    if file_id:
        direct_download_url = f"https://drive.google.com/uc?id={file_id}"
        response = requests.get(direct_download_url)
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(response.content)
            print(f"Downloaded image: {save_path}")
            return True
    print(f"Failed to download image from {image_url}")
    return False


def user_exists_in_db(name):
    """
    Check if a user with the given name exists in the database.
    """
    cursor.execute("SELECT 1 FROM users WHERE name = ?", (name,))
    return cursor.fetchone() is not None


# === Main Functionalities ===

def process_google_sheet():
    """
    Process Google Sheets data:
    - Fetch rows from Google Sheets.
    - Download images and save locally.
    - Extract face encodings and save to SQLite database.
    """
    data = worksheet.get_all_records()  # Fetch all rows from the sheet

    for row in data:
        name = row.get('Nama (Nama depan saja)', 'Unknown')
        makanan = row.get('Makanan', 'Unknown')
        image_url = row.get('Foto wajah')

        # Skip rows with missing image URLs
        if not image_url:
            print(f"Skipping {name} due to missing image.")
            continue

        # Skip if user already exists in the database
        if user_exists_in_db(name):
            print(f"User {name} already exists in the database. Skipping...")
            continue

        # Generate unique filename and save path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_filename = f"{name}_{timestamp}.jpg"
        save_path = os.path.join(SAVE_DIR, image_filename)

        # Download and process the image
        if download_image(image_url, save_path):
            image = cv2.imread(save_path)
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            boxes = face_recognition.face_locations(rgb, model="hog")
            encodings = face_recognition.face_encodings(rgb, boxes)

            if encodings:
                encoding = encodings[0]
                cursor.execute('INSERT INTO users (name, makanan, encoding) VALUES (?, ?, ?)',
                               (name, makanan, pickle.dumps(encoding)))
                conn.commit()
                print(f"Data for {name} saved to the database.")
            else:
                print(f"No face detected in {name}'s image.")

def recognize_and_order_from_db():
    """
    Recognize users via webcam and process their orders using the SQLite database.
    - Captures images from the webcam.
    - Matches detected faces with the stored encodings in the database.
    - Sends a Telegram message with order suggestions for recognized users.
    """
    # Fetch all user data from the database
    cursor.execute("SELECT name, makanan, encoding FROM users")
    rows = cursor.fetchall()

    if not rows:
        print("No data in the database. Please process the Google Sheet first.")
        return

    # Prepare known face data for recognition
    known_face_encodings = []
    known_face_names = []
    known_face_orders = {}

    for row in rows:
        name, makanan, encoding_blob = row
        encoding = pickle.loads(encoding_blob)  # Decode face encoding from the database
        known_face_encodings.append(encoding)
        known_face_names.append(name)
        known_face_orders[name] = makanan

    print("Processing orders based on database data...")
    
    # Start webcam capture
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Error: Failed to capture image.")
                break

            # Convert the captured frame to RGB for face recognition
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb_frame)
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

            # Match each detected face with known faces
            for face_encoding in face_encodings:
                matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
                face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
                best_match_index = np.argmin(face_distances)  # Find the closest match

                if matches[best_match_index]:
                    # Recognized face
                    name = known_face_names[best_match_index]
                    makanan = known_face_orders[name]
                    print(f"Welcome back, {name}! Your order is {makanan}.")

                    # Trigger Telegram bot to show order options
                    sendCustomerDataWithButtons(name)

                    cap.release()  # Release the webcam after recognition
                    return  # Exit after recognizing one user
                else:
                    # Face not recognized
                    print("Face not recognized. Please register first.")
    finally:
        # Ensure the webcam is released in case of any exception
        cap.release()

def sendCustomerDataWithButtons(name):
    """
    Send customer data to Telegram with menu buttons.
    """
    # Fetch user data from the database
    cursor.execute("SELECT name, makanan FROM users WHERE name = ?", (name,))
    user_data = cursor.fetchone()

    if not user_data:
        message = f"User '{name}' not found in the database."
        requests.post(URL + "sendMessage", data={"chat_id": CHAT_ID, "text": message})
        return

    user_name, makanan = user_data
    message = (
        f"👤 *Customer Detected*\n\n"
        f"*Name:* {user_name}\n"
        f"*Suggested Order:* {makanan}\n\n"
        f"Customer ingin membeli:"
    )

    # Define buttons for the menu
    keyboard = [
        [InlineKeyboardButton("Ayam", callback_data=f"order:{name}:Ayam")],
        [InlineKeyboardButton("Bebek", callback_data=f"order:{name}:Bebek")],
        [InlineKeyboardButton("Ikan", callback_data=f"order:{name}:Ikan")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send message with buttons
    resp = requests.post(
        URL + "sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
            "reply_markup": json.dumps(reply_markup.to_dict()),
        },
    )
    if resp.status_code == 200:
        print("Customer data with buttons sent to Telegram successfully.")
    else:
        print(f"Failed to send message to Telegram: {resp.text}")


def handleButtonClick(callback_query):
    """
    Handle button clicks in Telegram to update user orders.
    """
    data = callback_query['data']
    chat_id = callback_query['message']['chat']['id']
    message_id = callback_query['message']['message_id']

    # Parse callback data (format: "order:NAME:ITEM")
    parts = data.split(':')
    if len(parts) == 3 and parts[0] == "order":
        name = parts[1]
        new_order = parts[2]

        # Update the order in the database
        cursor.execute("UPDATE users SET makanan = ? WHERE name = ?", (new_order, name))
        conn.commit()

        # Acknowledge the update via Telegram
        message = f"Order updated to *{new_order}* for *{name}*!"
        requests.post(
            URL + "editMessageText",
            data={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": message,
                "parse_mode": "Markdown",
            },
        )
        print(f"Order for {name} updated to {new_order} in the database.")
    else:
        print("Invalid callback data.")


def pollTelegramUpdates():
    """
    Poll Telegram for updates and handle button clicks.
    """
    global order_update_complete
    offset = 0
    while True:
        resp = requests.get(URL + "getUpdates", params={"offset": offset, "timeout": 100})
        if resp.status_code == 200:
            updates = resp.json().get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                if "callback_query" in update:
                    handleButtonClick(update["callback_query"])
                    order_update_complete = True
        else:
            print(f"Failed to fetch updates from Telegram: {resp.text}")
        time.sleep(1)


if __name__ == "__main__":
    # Configuration for automation
    google_sheet_interval = 600  # Interval to fetch data from Google Sheets (in seconds)
    recognition_interval = 60    # Interval to check for face recognition (in seconds)
    
    last_google_sheet_time = time.time() - google_sheet_interval  # Ensure immediate first run
    last_recognition_time = time.time() - recognition_interval

    # Start Telegram update polling in a background thread
    threading.Thread(target=pollTelegramUpdates, daemon=True).start()

    print("Automation started. System is running...")
    while True:
        current_time = time.time()

        # Process Google Sheets if the interval has passed
        if current_time - last_google_sheet_time >= google_sheet_interval:
            print("Fetching data from Google Sheets and populating database...")
            process_google_sheet()
            last_google_sheet_time = current_time

        # Perform face recognition if the interval has passed
        if current_time - last_recognition_time >= recognition_interval:
            print("Starting face recognition and order processing...")
            order_update_complete = False
            recognize_and_order_from_db()
            print("Waiting for the user to update their order via Telegram...")
            
            # Wait for Telegram updates or a timeout (to avoid indefinite wait)
            start_wait_time = time.time()
            while not order_update_complete and time.time() - start_wait_time < 300:  # Timeout after 5 minutes
                time.sleep(0.5)
            
            if order_update_complete:
                print("Order updated successfully.")
            else:
                print("No updates received within the timeout period.")
            
            last_recognition_time = current_time

        # Sleep briefly to reduce CPU usage
        time.sleep(1)

