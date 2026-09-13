from app.routers import report_ingest
from app.routers import patient_auth, patient_reports
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from app.database import Base, engine
from app import models
from app.routers import (
    centres, users, auth, patients, tests, orders, billing, reports, credits, dashboard
)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Diagnostic Centre Management API",
    description="Multi-tenant backend with RBAC, multi-test orders, billing, bulk reports, and credit SaaS tier.",
    version="3.0.0",
)

app.include_router(auth.router)
app.include_router(centres.router)
app.include_router(users.router)
app.include_router(patients.router)
app.include_router(tests.router)
app.include_router(orders.router)
app.include_router(billing.router)
app.include_router(reports.router)
app.include_router(credits.router)
app.include_router(dashboard.router)
# app.include_router(patient_auth.router)  # Deprecated per project direction
# app.include_router(patient_reports.router)  # Deprecated per project direction
app.include_router(report_ingest.router)


@app.get("/")
def health_check():
    return {
        "status": "online",
        "system": "Diagnostic Centre Backend",
        "version": "3.0.0",
    }



@app.get("/upload-test", response_class=HTMLResponse)
def upload_test_page():
    return """
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Bulk Report Upload Test</title>
        <style>
            body { font-family: sans-serif; padding: 18px; background: #0f172a; color: #f8fafc; margin: 0; }
            .container { max-width: 540px; margin: 0 auto; }
            input, button { display: block; margin: 12px 0; font-size: 15px; width: 100%; box-sizing: border-box; }
            input[type="text"], input[type="password"] { padding: 10px; border-radius: 6px; border: 1px solid #334155; background: #1e293b; color: #fff; }
            input[type="file"] { padding: 10px; background: #1e293b; border: 1px dashed #475569; border-radius: 6px; }
            button { padding: 12px; background: #2563eb; color: white; border: none; border-radius: 6px; font-weight: bold; cursor: pointer; }
            pre { background: #020617; padding: 12px; border-radius: 6px; overflow-x: auto; color: #38bdf8; font-size: 13px; max-height: 350px; }
            .status { font-size: 14px; margin-top: 8px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h3>Bulk Report Ingestion Portal</h3>
            
            <div style="background: #1e293b; padding: 14px; border-radius: 8px; margin-bottom: 15px;">
                <label style="font-size: 12px; color: #94a3b8;">Username / Email:</label>
                <input type="text" id="username" value="admin@apex.com">
                <label style="font-size: 12px; color: #94a3b8;">Password:</label>
                <input type="password" id="password" value="admin123">
                <button type="button" onclick="doLogin()" style="background: #059669;">1. Authenticate</button>
                <div id="authStatus" class="status" style="color: #cbd5e1;">Status: Not authenticated</div>
            </div>

            <label style="font-size: 12px; color: #94a3b8;">Select Multiple PDFs:</label>
            <input type="file" id="fileInput" multiple accept=".pdf,.png,.jpg">
            
            <button type="button" id="uploadBtn" onclick="submitFiles()" style="background: #3b82f6;" disabled>2. Upload Batch</button>
            
            <h4>Server Response:</h4>
            <pre id="output">Waiting for files...</pre>
        </div>

        <script>
        let token = '';

        async function doLogin() {
            const u = document.getElementById('username').value.trim();
            const p = document.getElementById('password').value.trim();
            const status = document.getElementById('authStatus');
            status.innerHTML = '<span style="color: #38bdf8;">Authenticating...</span>';

            const form = new URLSearchParams();
            form.append('username', u);
            form.append('password', p);

            // Try standard /login first, then /auth/login
            const endpoints = ['/login', '/auth/login'];
            let succeeded = false;

            for (let ep of endpoints) {
                try {
                    let res = await fetch(ep, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                        body: form
                    });

                    // If form-urlencoded fails, try JSON body
                    if (res.status === 422) {
                        res = await fetch(ep, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ email: u, password: p, username: u })
                        });
                    }

                    if (res.ok) {
                        const data = await res.json();
                        token = data.access_token || data.token;
                        if (token) {
                            status.innerHTML = '<b style="color: #4ade80;">✓ Authenticated successfully (' + ep + ')</b>';
                            document.getElementById('uploadBtn').disabled = false;
                            succeeded = true;
                            break;
                        }
                    }
                } catch (err) {
                    console.log('Error on ' + ep, err);
                }
            }

                status.innerHTML = '<b style="color: #f87171;">✕ Login failed. Check terminal or credentials.</b>';
            }
        }

        async function submitFiles() {
            const input = document.getElementById('fileInput');
            const out = document.getElementById('output');
            
                alert('Please authenticate first.');
                return;
            }
                alert('Select files to upload.');
                return;
            }

            const formData = new FormData();
            for (let i = 0; i < input.files.length; i++) {
                formData.append('files', input.files[i]);
            }

            out.textContent = 'Processing ' + input.files.length + ' file(s)...';

            try {
                const res = await fetch('/reports/bulk-upload', {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + token },
                    body: formData
                });
                const data = await res.json();
                out.textContent = JSON.stringify(data, null, 2);
            } catch (err) {
                out.textContent = 'Upload error: ' + err.message;
            }
        }
        </script>
    </body>
    </html>
    """


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
