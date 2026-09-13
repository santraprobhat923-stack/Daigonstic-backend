path = '/storage/emulated/0/diagnostic_backend/main.py'

portal_html = """
@app.get("/portal", response_class=HTMLResponse)
def bulk_upload_portal():
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Diagnostic Upload Portal</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 20px; }
        .card { max-width: 520px; margin: 0 auto; background: #1e293b; border-radius: 12px; padding: 24px; box-shadow: 0 10px 25px rgba(0,0,0,0.4); }
        h2 { margin-top: 0; color: #38bdf8; font-size: 1.3rem; }
        label { display: block; font-size: 0.85rem; color: #94a3b8; margin: 12px 0 4px; }
        input[type="text"], input[type="password"] { width: 100%; padding: 12px; background: #0f172a; border: 1px solid #334155; border-radius: 6px; color: #fff; font-size: 1rem; }
        input[type="file"] { width: 100%; padding: 10px; background: #0f172a; border: 1px dashed #475569; border-radius: 6px; color: #94a3b8; }
        button { width: 100%; padding: 14px; margin-top: 14px; border: none; border-radius: 6px; font-weight: 700; font-size: 1rem; cursor: pointer; }
        .btn-green { background: #10b981; color: white; }
        .btn-blue { background: #2563eb; color: white; }
        .btn-blue:disabled { background: #475569; cursor: not-allowed; }
        .status-box { margin-top: 10px; padding: 8px 12px; border-radius: 6px; font-size: 0.85rem; }
        .status-ok { background: #064e3b; color: #6ee7b7; }
        .status-err { background: #7f1d1d; color: #fca5a5; }
        pre { background: #020617; border: 1px solid #1e293b; border-radius: 6px; padding: 12px; color: #38bdf8; font-size: 0.8rem; overflow-x: auto; max-height: 350px; }
    </style>
</head>
<body>
    <div class="card">
        <h2>Diagnostic Centre: Bulk Portal</h2>
        
        <div id="authSection">
            <label>Username / Email</label>
            <input type="text" id="user" value="admin@apex.com">
            <label>Password</label>
            <input type="password" id="pass" value="admin123">
            <button class="btn-green" type="button" onclick="login()">1. Log In & Verify</button>
            <div id="loginMsg"></div>
        </div>

        <hr style="border: 0; border-top: 1px solid #334155; margin: 20px 0;">

        <div>
            <label>Choose Multiple Reports (PDF/Images):</label>
            <input type="file" id="filePicker" multiple accept=".pdf,.png,.jpg,.jpeg">
            <button id="uploadBtn" class="btn-blue" type="button" onclick="upload()" disabled>2. Upload Batch</button>
        </div>

        <label style="margin-top: 20px;">Server Response:</label>
        <pre id="output">Waiting for upload...</pre>
    </div>

    <script>
        let jwtToken = sessionStorage.getItem("token") || "";

        if (jwtToken) {
            document.getElementById("loginMsg").innerHTML = '<div class="status-box status-ok">✓ Logged in from previous session</div>';
            document.getElementById("uploadBtn").disabled = false;
        }

        async function login() {
            const msg = document.getElementById("loginMsg");
            msg.innerHTML = '<div class="status-box" style="background:#1e293b;color:#38bdf8;">Authenticating...</div>';
            
            const formData = new URLSearchParams();
            formData.append("username", document.getElementById("user").value);
            formData.append("password", document.getElementById("pass").value);

            try {
                const res = await fetch("/login", {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: formData
                });
                
                const data = await res.json();
                if (res.ok && data.access_token) {
                    jwtToken = data.access_token;
                    sessionStorage.setItem("token", jwtToken);
                    msg.innerHTML = '<div class="status-box status-ok">✓ Authenticated successfully!</div>';
                    document.getElementById("uploadBtn").disabled = false;
                } else {
                    msg.innerHTML = '<div class="status-box status-err">✕ Login failed: ' + (data.detail || JSON.stringify(data)) + '</div>';
                }
            } catch (err) {
                msg.innerHTML = '<div class="status-box status-err">✕ Network error: ' + err.message + '</div>';
            }
        }

        async function upload() {
            const files = document.getElementById("filePicker").files;
            const output = document.getElementById("output");
            
            if (!files.length) {
                alert("Please choose at least one file first.");
                return;
            }

            output.textContent = "Uploading " + files.length + " files to backend...";

            const body = new FormData();
            for (let i = 0; i < files.length; i++) {
                body.append("files", files[i]);
            }

            try {
                const res = await fetch("/reports/bulk-upload", {
                    method: "POST",
                    headers: {
                        "Authorization": "Bearer " + jwtToken
                    },
                    body: body
                });

                const json = await res.json();
                output.textContent = JSON.stringify(json, null, 2);
            } catch (e) {
                output.textContent = "Upload error: " + e.message;
            }
        }
    </script>
</body>
</html>'''
"""

with open(path, 'r') as f:
    content = f.read()

# Replace or append the portal route
if '@app.get("/portal"' in content:
    print("Portal route already present.")
else:
    content += "\n" + portal_html
    with open(path, 'w') as f:
        f.write(content)
    print("Appended /portal route to main.py successfully!")
