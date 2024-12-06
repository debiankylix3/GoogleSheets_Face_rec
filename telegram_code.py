import os
import requests
import threading
import time
import json

TOKEN = "7859837971:AAEiP-Hfo0mh6Qn6CFOqmCUJ1jkXIB5xqWA"
CHAT_ID = "6861255295"
URL = f"https://api.telegram.org/bot{TOKEN}/"

def sendCustomerDataToTelegram(namaPelanggan):
    # Send "Pelanggan Terdeteksi" message
    caption = f"Pelanggan Terdeteksi: {namaPelanggan}"
    resp = requests.post(URL + "sendMessage", data={"chat_id": CHAT_ID, "text": caption})
    if resp.status_code != 200:
        print(f"Error sending initial message: {resp.text}")
        return
    
    # Store the message ID of the initial message
    initial_message_id = resp.json().get("result", {}).get("message_id")
    
    # Prepare the buttons
    inline_buttons = {
        "inline_keyboard": [
            [{"text": "Burger", "callback_data": "burger_selected"}],
            [{"text": "Ayam", "callback_data": "ayam_selected"}],
            [{"text": "Pelanggan Tidak Membeli", "callback_data": "no_purchase"}],
        ]
    }
    reply_markup = json.dumps(inline_buttons)
    
    # Send the second message with buttons
    menu_caption = "Pilih Menu Yang Dibeli Pelanggan:"
    resp = requests.post(
        URL + "sendMessage",
        data={"chat_id": CHAT_ID, "text": menu_caption, "reply_markup": reply_markup},
    )
    if resp.status_code != 200:
        print(f"Error sending menu message: {resp.text}")
        return
    
    # Store the message ID of the menu message
    menu_message_id = resp.json().get("result", {}).get("message_id")
    print("Messages sent successfully. Waiting for user interaction...")
    
    # Start polling for updates
    pollForUpdates(initial_message_id, menu_message_id)

def pollForUpdates(initial_message_id, menu_message_id):
    last_update_id = None

    while True:
        resp = requests.get(URL + "getUpdates", params={"offset": last_update_id, "timeout": 100})
        if resp.status_code != 200:
            print(f"Error fetching updates: {resp.text}")
            time.sleep(1)
            continue

        updates = resp.json().get("result", [])
        for update in updates:
            last_update_id = update["update_id"] + 1

            # Check for callback queries (button presses)
            if "callback_query" in update:
                callback_query = update["callback_query"]
                handleCallbackQuery(callback_query, initial_message_id, menu_message_id)

        time.sleep(1)  # Avoid flooding Telegram with requests

def handleCallbackQuery(callback_query, initial_message_id, menu_message_id):
    query_id = callback_query["id"]
    chat_id = callback_query["message"]["chat"]["id"]
    callback_data = callback_query["data"]

    # Acknowledge the callback query
    requests.post(URL + "answerCallbackQuery", data={"callback_query_id": query_id})

    # Respond based on the callback data
    if callback_data == "burger_selected":
        response_text = "Terima kasih telah memilih Burger!"
    elif callback_data == "ayam_selected":
        response_text = "Terima kasih telah memilih Ayam!"
    elif callback_data == "no_purchase":
        response_text = "Terima kasih, kami menghargai keputusan Anda!"
    else:
        response_text = "Pilihan tidak dikenali."
    
    # Send a thank-you message
    resp = requests.post(URL + "sendMessage", data={"chat_id": chat_id, "text": response_text})
    if resp.status_code != 200:
        print(f"Error sending thank-you message: {resp.text}")
        return

    # Store the thank-you message ID
    thank_you_message_id = resp.json().get("result", {}).get("message_id")

    # Delete the initial message
    delete_initial = requests.post(
        URL + "deleteMessage",
        data={"chat_id": chat_id, "message_id": initial_message_id},
    )
    if delete_initial.status_code != 200:
        print(f"Error deleting initial message: {delete_initial.text}")
    else:
        print("Initial message deleted.")

    # Delete the menu message with buttons
    delete_menu = requests.post(
        URL + "deleteMessage",
        data={"chat_id": chat_id, "message_id": menu_message_id},
    )
    if delete_menu.status_code != 200:
        print(f"Error deleting menu message: {delete_menu.text}")
    else:
        print("Menu message deleted.")

    # Schedule deletion of the thank-you message after a delay
    time.sleep(5)  # Delay of 5 seconds (adjust as needed)
    delete_thank_you = requests.post(
        URL + "deleteMessage",
        data={"chat_id": chat_id, "message_id": thank_you_message_id},
    )
    if delete_thank_you.status_code != 200:
        print(f"Error deleting thank-you message: {delete_thank_you.text}")
    else:
        print("Thank-you message deleted.")

    print("Chat cleared successfully.")

# Example customer name
namaPelanggan = "John Doe"

# Run the bot in a separate thread
telegramThread = threading.Thread(target=sendCustomerDataToTelegram, args=(namaPelanggan,))
telegramThread.start()