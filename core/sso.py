import hmac
import hashlib
import os

SSO_SECRET_KEY = os.environ.get("SSO_SECRET_KEY", "prode_sso_secret_12345")

def verify_sso_signature(user_id: str, signature: str) -> bool:
    payload = str(user_id).encode('utf-8')
    expected_signature = hmac.new(
        SSO_SECRET_KEY.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)

def generate_sso_signature(user_id: str) -> str:
    payload = str(user_id).encode('utf-8')
    return hmac.new(
        SSO_SECRET_KEY.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
