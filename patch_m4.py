with open("test_milestone4_pdf.py", "r") as f:
    code = f.read()

# Replace urllib imports with TestClient setup
old_header = """import urllib.request
import urllib.parse
import urllib.error
import json
import sqlite3
import io
from pypdf import PdfReader

BASE_URL = "http://127.0.0.1:8000"
DB_PATH = "diagnostic.db"

print("=" * 60)
print("PHASE 5 - MILESTONE 4: FINAL REPORT PDF TEST SUITE")
print("=" * 60)

def get_token(username, password):
    data = urllib.parse.urlencode({"username": username, "password": password}).encode()
    req = urllib.request.Request(f"{BASE_URL}/login", data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())["access_token"]"""

new_header = """import json
import sqlite3
import io
from pypdf import PdfReader
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
DB_PATH = "diagnostic.db"

print("=" * 60)
print("PHASE 5 - MILESTONE 4: FINAL REPORT PDF TEST SUITE")
print("=" * 60)

def get_token(username, password):
    resp = client.post("/auth/login", data={"username": username, "password": password})
    if resp.status_code != 200:
        resp = client.post("/login", data={"username": username, "password": password})
    return resp.json()["access_token"]"""

code = code.replace(old_header, new_header)

# Replace remaining urllib calls throughout the script
code = code.replace("urllib.request.urlopen(req)", "client_open(req)")
code = code.replace("urllib.request.Request(", "create_mock_req(")

# Add helper wrappers right after header
helpers = """
class MockResp:
    def __init__(self, res):
        self.res = res
        self.status = res.status_code
    def read(self):
        return self.res.content

def create_mock_req(url, data=None, headers=None, method="GET"):
    return {"url": url.replace("http://127.0.0.1:8000", ""), "data": data, "headers": headers or {}, "method": method}

def client_open(req):
    url = req["url"]
    headers = req["headers"]
    data = req["data"]
    method = req.get("method", "POST" if data else "GET")
    if method == "POST":
        if isinstance(data, (bytes, bytearray)):
            r = client.post(url, data=data, headers=headers)
        elif isinstance(data, dict):
            r = client.post(url, json=data, headers=headers)
        else:
            r = client.post(url, content=data, headers=headers)
    else:
        r = client.get(url, headers=headers)
    return MockResp(r)
"""

if "def client_open" not in code:
    code = code.replace('return resp.json()["access_token"]\n', 'return resp.json()["access_token"]\n' + helpers)

with open("test_milestone4_pdf.py", "w") as f:
    f.write(code)

print("test_milestone4_pdf.py converted to in-process TestClient.")
