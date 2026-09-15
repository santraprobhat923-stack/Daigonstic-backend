with open("test_milestone4_pdf.py", "r") as f:
    content = f.read()

# Make sure BASE_URL is defined as empty string
if "BASE_URL =" not in content:
    content = "BASE_URL = ''\n" + content

# Make sure urllib and HTTPError exist
header_additions = """import urllib
class MockHTTPError(Exception):
    def __init__(self, code, msg="HTTP Error"):
        self.code = code
        self.msg = msg
        super().__init__(f"HTTP {code}: {msg}")

import types
urllib.error = types.ModuleType("urllib.error")
urllib.error.HTTPError = MockHTTPError
"""

if "MockHTTPError" not in content:
    content = header_additions + content

# Update client_open to raise MockHTTPError on 4xx/5xx if expected
patch_client_open = """def client_open(req):
    url = req["url"]
    headers = req["headers"]
    data = req["data"]
    method = req.get("method", "POST" if data is not None else "GET")
    if method == "POST":
        if isinstance(data, (bytes, bytearray)):
            r = client.post(url, content=data, headers=headers)
        elif isinstance(data, dict):
            r = client.post(url, json=data, headers=headers)
        else:
            r = client.post(url, data=data, headers=headers)
    else:
        r = client.get(url, headers=headers)
    
    if r.status_code >= 400:
        raise urllib.error.HTTPError(r.status_code, r.text)
    return MockResp(r)
"""

import re
content = re.sub(r"def client_open\(req\):.*?(?=\n\w|\Z)", patch_client_open, content, flags=re.DOTALL)

with open("test_milestone4_pdf.py", "w") as f:
    f.write(content)

print("test_milestone4_pdf.py fixed successfully.")
