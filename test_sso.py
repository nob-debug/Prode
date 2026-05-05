import hmac
import hashlib
import urllib.parse
import os
import requests
from core.sso import generate_sso_signature

def get_sso_url(user_id):
    signature = generate_sso_signature(user_id)
    params = {
        "id": user_id,
        "signature": signature
    }
    query_string = urllib.parse.urlencode(params)
    return f"http://localhost:8000/api/auth/external-login?{query_string}"

if __name__ == "__main__":
    url = get_sso_url("12345")
    print(f"Test SSO Login URL:\n{url}")
    print("\nAttempting to hit URL...")
    try:
        response = requests.get(url, allow_redirects=False)
        print(f"Status Code: {response.status_code}")
        print(f"Headers: {response.headers}")
        if response.status_code == 200:
            print(f"Response Body: {response.text}")
    except Exception as e:
        print(f"Error: {e}")
