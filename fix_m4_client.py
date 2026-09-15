with open("test_milestone4_pdf.py", "r") as f:
    code = f.read()

import re

new_client_open = '''def create_mock_req(url, data=None, headers=None, method=None):
    clean_url = url.replace("http://127.0.0.1:8000", "")
    if method is None:
        method = "POST" if data is not None else "GET"
    return {"url": clean_url, "data": data, "headers": headers or {}, "method": method}

def client_open(req):
    url = req["url"]
    headers = req["headers"]
    data = req["data"]
    method = req.get("method", "GET")

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
        import io
        raise urllib.error.HTTPError(url, r.status_code, r.text, r.headers, io.BytesIO(r.content))
    return MockResp(r)
'''

# Replace create_mock_req and client_open
code = re.sub(r"def create_mock_req\(.*?def client_open\(req\):.*?(?=\n(?:class|def|conn|\#|\Z))", new_client_open + "\n", code, flags=re.DOTALL)

with open("test_milestone4_pdf.py", "w") as f:
    f.write(code)

print("client_open explicitly enforces POST when data is not None.")
