from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

response = client.post(
    "/predict/A3",
    data={"g1": "2", "g2": "1", "penales": ""},
    cookies={"session_token": "test"} # doesn't matter, we can patch get_current_user
)

# wait actually we need a real session or we get "No autenticado"
