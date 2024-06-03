from flask import Flask, render_template, request, jsonify
import asyncio
import json
import os
import re
from getpass import getpass
from dotenv import load_dotenv
from telethon.sync import TelegramClient, errors, functions
from telethon.tl import types

app = Flask(__name__)
load_dotenv()

def get_human_readable_user_status(status: types.TypeUserStatus):
    match status:
        case types.UserStatusOnline():
            return "Currently online"
        case types.UserStatusOffline():
            return status.was_online.strftime("%Y-%m-%d %H:%M:%S %Z")
        case types.UserStatusRecently():
            return "Last seen recently"
        case types.UserStatusLastWeek():
            return "Last seen last week"
        case types.UserStatusLastMonth():
            return "Last seen last month"
        case _:
            return "Unknown"

async def get_names(client: TelegramClient, phone_number: str) -> dict:
    result = {}
    print(f"Checking: {phone_number=} ...", end="", flush=True)
    try:
        contact = types.InputPhoneContact(client_id=0, phone=phone_number, first_name="", last_name="")
        contacts = await client(functions.contacts.ImportContactsRequest([contact]))
        users = contacts.to_dict().get("users", [])
        number_of_matches = len(users)

        if number_of_matches == 0:
            result.update({"error": "No response, the phone number is not on Telegram or has blocked contact adding."})
        elif number_of_matches == 1:
            updates_response: types.Updates = await client(functions.contacts.DeleteContactsRequest(id=[users[0].get("id")]))
            user = updates_response.users[0]
            result.update({
                "id": user.id,
                "username": user.username,
                "usernames": user.usernames,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "fake": user.fake,
                "verified": user.verified,
                "premium": user.premium,
                "mutual_contact": user.mutual_contact,
                "bot": user.bot,
                "bot_chat_history": user.bot_chat_history,
                "restricted": user.restricted,
                "restriction_reason": user.restriction_reason,
                "user_was_online": get_human_readable_user_status(user.status),
                "phone": user.phone,
            })
        else:
            result.update({"error": "This phone number matched multiple Telegram accounts, which is unexpected. Please contact the developer."})
    except Exception as e:
        result.update({"error": f"Unexpected error: {e}."})
        raise
    print("Done.")
    return result

async def validate_users(client: TelegramClient, phone_numbers: str) -> dict:
    result = {}
    phones = [re.sub(r"\s+", "", p, flags=re.UNICODE) for p in phone_numbers.split(",")]
    try:
        for phone in phones:
            if phone not in result:
                result[phone] = await get_names(client, phone)
    except Exception as e:
        print(e)
        raise
    return result

async def login(api_id: str, api_hash: str, phone_number: str) -> TelegramClient:
    print("Logging in...", end="", flush=True)
    client = TelegramClient(phone_number, api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        await client.send_code_request(phone_number)
        try:
            await client.sign_in(phone_number, input("Enter the code (sent on telegram): "))
        except errors.SessionPasswordNeededError:
            pw = getpass("Two-Step Verification enabled. Please enter your account password: ")
            await client.sign_in(password=pw)
    print("Done.")
    return client

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/check', methods=['POST'])
def check():
    phone_numbers = request.form['phone_numbers']
    api_id = request.form['api_id']
    api_hash = request.form['api_hash']
    api_phone_number = request.form['api_phone_number']
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    client = loop.run_until_complete(login(api_id, api_hash, api_phone_number))
    results = loop.run_until_complete(validate_users(client, phone_numbers))
    client.disconnect()
    
    return jsonify(results)

if __name__ == "__main__":
    app.run(debug=True)

