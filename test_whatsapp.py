import requests

META_ACCESS_TOKEN = "EAAg9Gan6drsBSsJJeNZCAuP3YmBX9gPZCd7UP07ZAyCMZCtdeY18wS6xN0rPQ7ECArQ4zhIUzTFuKxVpzo0y2j3ZAFZAwAxGBn2dCFHd67rbgchn6wrpDpR2pm8RyFH9I1YSnpeMPHZCI3uPvjUNYoT8oqz3SD5CP34n7ejztVte9eKTDuJyVrUygQw6GwsQKZCeI7VboHa6VznQi4eKeCyICFaDVr2rrjZArR969t3uZAtphDJzTa9IdZCH8LZANA2ElzRSybLnXRaB5brohPUuoYz7dwZDZD"
META_PHONE_ID = "1358122214045364"
ADMIN_WHATSAPP = "918173031237"

url = f"https://graph.facebook.com/v20.0/{META_PHONE_ID}/messages"

headers = {
    "Authorization": f"Bearer {META_ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

# Standard hello_world template
payload = {
    "messaging_product": "whatsapp",
    "to": ADMIN_WHATSAPP,
    "type": "template",
    "template": {
        "name": "hello_world",
        "language": {
            "code": "en_US"
        }
    }
}

response = requests.post(url, json=payload, headers=headers)
print("Status Code:", response.status_code)
print("Response:", response.text)