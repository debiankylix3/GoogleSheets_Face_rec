import sqlite3
import numpy as np

def view_database():
    conn = sqlite3.connect("face_recognition.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Users")
    rows = cursor.fetchall()
    
    for row in rows:
        print(row)  # Print the entire row to see its structure

    conn.close()

# Run this function to view the database content
view_database()
