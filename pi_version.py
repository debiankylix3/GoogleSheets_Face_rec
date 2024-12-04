import os
import gspread
import requests
import face_recognition
import pickle
import sqlite3
import numpy as np
from google.oauth2.service_account import Credentials
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from picamera2 import Picamera2
from time import sleep

# Google Sheets and Drive Config
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
CREDENTIALS_FILE = 'credentials.json'
SHEET_ID = '1RAeSlGL50t6DuOLLKYG3r65WUbOxNj4I_paCWDT6828'

# Authenticate with Google Sheets
credentials = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
client = gspread.authorize(credentials)
sheet = client.open_by_key(SHEET_ID)
worksheet = sheet.get_worksheet(0)

# Local Directory for Images
SAVE_DIR = 'google_sheet_images'
os.makedirs(SAVE_DIR, exist_ok=True)

# SQLite Database Setup
DB_FILE = "face_recognition.db"
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# Create database table
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    makanan TEXT NOT NULL,
    encoding BLOB NOT NULL
)
''')
conn.commit()

def extract_file_id(image_url):
    """Extracts the file ID from Google Drive URL."""
    if "id=" in image_url:
        return parse_qs(urlparse(image_url).query).get('id', [None])[0]
    elif "/file/d/" in image_url:
        return image_url.split("/file/d/")[1].split('/')[0]
    return None

def download_image(image_url, save_path):
    """Downloads the image from Google Drive and saves it locally."""
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
    """Check if a user already exists in the database by name."""
    cursor.execute("SELECT 1 FROM users WHERE name = ?", (name,))
    return cursor.fetchone() is not None

def process_google_sheet():
    """Fetch and process only new Google Sheets data, save images locally, and populate database."""
    data = worksheet.get_all_records()

    for row in data:
        name = row.get('Nama (Nama depan saja)', 'Unknown')
        makanan = row.get('Makanan', 'Unknown')
        image_url = row.get('Foto wajah')

        if not image_url:
            print(f"Skipping {name} due to missing image.")
            continue

        if user_exists_in_db(name):
            print(f"User {name} already exists in the database. Skipping...")
            continue

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_filename = f"{name}_{timestamp}.jpg"
        save_path = os.path.join(SAVE_DIR, image_filename)

        if download_image(image_url, save_path):
            image = face_recognition.load_image_file(save_path)
            boxes = face_recognition.face_locations(image, model="hog")
            encodings = face_recognition.face_encodings(image, boxes)

            if encodings:
                encoding = encodings[0]
                cursor.execute('INSERT INTO users (name, makanan, encoding) VALUES (?, ?, ?)',
                               (name, makanan, pickle.dumps(encoding)))
                conn.commit()
                print(f"Data for {name} saved to the database.")
            else:
                print(f"No face detected in {name}'s image.")

def recognize_and_order_from_db():
    """Recognize users and process their orders using SQLite database."""
    cursor.execute("SELECT name, makanan, encoding FROM users")
    rows = cursor.fetchall()

    if not rows:
        print("No data in the database. Please process the Google Sheet first.")
        return

    known_face_encodings = []
    known_face_names = []
    known_face_orders = {}

    for row in rows:
        name, makanan, encoding_blob = row
        encoding = pickle.loads(encoding_blob)
        known_face_encodings.append(encoding)
        known_face_names.append(name)
        known_face_orders[name] = makanan

    print("Starting face recognition...")
    picam2 = Picamera2()
    config = picam2.create_preview_configuration(main={"size": (640, 480)})
    picam2.configure(config)
    picam2.start()
    sleep(2)

    try:
        while True:
            frame = picam2.capture_array()
            face_locations = face_recognition.face_locations(frame)
            face_encodings = face_recognition.face_encodings(frame, face_locations)

            for face_encoding in face_encodings:
                matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
                face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
                best_match_index = np.argmin(face_distances)

                if matches[best_match_index]:
                    name = known_face_names[best_match_index]
                    makanan = known_face_orders[name]
                    print(f"Welcome back, {name}! Your order is {makanan}.")
                    return
                else:
                    print("Face not recognized. Please register first.")
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        picam2.stop()

if __name__ == "__main__":
    while True:
        print("\nOptions: ")
        print("1. Process Google Sheet and Save to Database")
        print("2. Recognize User and Process Order")
        print("3. Quit")

        choice = input("Select an option: ")
        if choice == "1":
            process_google_sheet()
        elif choice == "2":
            recognize_and_order_from_db()
        elif choice == "3":
            conn.close()
            break
        else:
            print("Invalid choice. Please try again.")
