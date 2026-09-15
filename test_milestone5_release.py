import sqlite3
from fastapi.testclient import TestClient
from main import app
from app.utils import create_access_token
from app import models

client = TestClient(app)

def run_tests():
    print("=== Running Milestone 5 Payment-Gated Release Tests ===")
    
    conn = sqlite3.connect("diagnostic.db")
    c = conn.cursor()
    
    # 1. Fetch an existing report document to test
    c.execute("SELECT id, centre_id, order_id, file_path FROM report_documents LIMIT 1;")
    rep = c.fetchone()
    
    if not rep:
        print("[!] Error: No report_documents found in DB.")
        conn.close()
        return

    rep_id, centre_id, order_id, fpath = rep

    # Ensure order linkage
    if not order_id:
        c.execute("SELECT id FROM orders WHERE centre_id = ? LIMIT 1;", (centre_id,))
        ord_row = c.fetchone()
        order_id = ord_row[0] if ord_row else 1
        c.execute("UPDATE report_documents SET order_id = ? WHERE id = ?;", (order_id, rep_id))

    # Reset to pending payment & unreleased state
    c.execute("""
        INSERT OR REPLACE INTO billing (id, order_id, centre_id, total_amount, paid_amount, pending_amount, payment_status)
        VALUES (
            (SELECT id FROM billing WHERE order_id = ?),
            ?, ?, 500.0, 0.0, 500.0, 'pending'
        );
    """, (order_id, order_id, centre_id))

    c.execute("""
        UPDATE report_documents 
        SET is_released = 0, release_status = 'HELD_PAYMENT', released_at = NULL, released_by = NULL 
        WHERE id = ?;
    """, (rep_id,))
    
    # 2. Get technician/staff user for this centre
    c.execute("SELECT id, email, role, centre_id FROM users WHERE centre_id = ? AND role in ('technician', 'centre_admin', 'admin') LIMIT 1;", (centre_id,))
    user_row = c.fetchone()

    if not user_row:
        print(f"[!] No staff user found for centre {centre_id}")
        conn.close()
        return

    user_id, email, role, u_centre = user_row
    token = create_access_token(data={"sub": str(user_id), "centre_id": u_centre, "role": role})
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Create or fetch a user belonging to another centre for Tenant Isolation test
    other_centre = 9999
    c.execute("INSERT OR IGNORE INTO centres (id, name) VALUES (?, 'Other Centre');", (other_centre,))
    c.execute("""
        INSERT OR IGNORE INTO users (id, email, hashed_password, role, is_active, centre_id)
        VALUES (8888, 'foreign_staff@test.com', 'fake_hash', 'technician', 1, ?);
    """, (other_centre,))
    conn.commit()
    conn.close()

    foreign_token = create_access_token(data={"sub": "8888", "centre_id": other_centre, "role": "technician"})
    foreign_headers = {"Authorization": f"Bearer {foreign_token}"}

    print(f"[*] Authenticated as: {email} (Role: {role}, Centre: {u_centre})")
    print(f"[*] Testing with Report ID: {rep_id}, Order ID: {order_id}")

    # --- TEST 1: Unreleased download blocked (402 Payment Required) ---
    res = client.get(f"/reports/final/{rep_id}/download", headers=headers)
    print(f"Test 1 - Download before release: HTTP {res.status_code}")
    assert res.status_code == 402, f"Expected 402, got {res.status_code}: {res.text}"
    print("  [PASS] Download successfully blocked with 402 Payment Required.")

    # --- TEST 2: Release attempt while pending payment fails (402) ---
    res = client.post(f"/reports/final/{rep_id}/release", headers=headers)
    print(f"Test 2 - Release trigger while unpaid: HTTP {res.status_code}")
    assert res.status_code == 402, f"Expected 402, got {res.status_code}: {res.text}"
    print("  [PASS] Release gated strictly against pending balance.")

    # --- TEST 3: Clear payment balance in billing ---
    conn = sqlite3.connect("diagnostic.db")
    c = conn.cursor()
    c.execute("UPDATE billing SET payment_status = 'paid', paid_amount = 500.0, pending_amount = 0.0 WHERE order_id = ?;", (order_id,))
    conn.commit()
    conn.close()
    print("[*] Payment settled: Order marked PAID with pending_amount = 0.0")

    # --- TEST 4: Query status endpoint (Should now be eligible) ---
    res = client.get(f"/reports/final/{rep_id}/status", headers=headers)
    print(f"Test 4 - Release status check: HTTP {res.status_code}")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    data = res.json()
    assert data["is_eligible_for_release"] is True, f"Expected eligible, got: {data}"
    print(f"  [PASS] Eligibility confirmed: {data['eligibility_reason']}")

    # --- TEST 5: Authoritative Release Trigger ---
    res = client.post(f"/reports/final/{rep_id}/release", headers=headers)
    print(f"Test 5 - Authoritative Release: HTTP {res.status_code}")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    release_data = res.json()
    assert release_data["is_released"] is True
    assert release_data["release_status"] == "RELEASED"
    print(f"  [PASS] Report transitioned to RELEASED (Released at: {release_data['released_at']})")

    # --- TEST 6: Download after release succeeds (200 OK) ---
    res = client.get(f"/reports/final/{rep_id}/download", headers=headers)
    print(f"Test 6 - Download after release: HTTP {res.status_code}")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    assert "application/pdf" in res.headers.get("content-type", "")
    print("  [PASS] Report PDF accessible and streamed successfully.")

    # --- TEST 7: Idempotency check ---
    res_repeat = client.post(f"/reports/final/{rep_id}/release", headers=headers)
    print(f"Test 7 - Duplicate release call: HTTP {res_repeat.status_code}")
    assert res_repeat.status_code == 200
    assert res_repeat.json()["is_released"] is True
    print("  [PASS] Re-release is safely idempotent.")

    # --- TEST 8: Multi-Tenant Isolation ---
    res_cross = client.get(f"/reports/final/{rep_id}/download", headers=foreign_headers)
    print(f"Test 8 - Cross-tenant download blocked: HTTP {res_cross.status_code}")
    assert res_cross.status_code == 404, f"Expected 404, got {res_cross.status_code}"
    print("  [PASS] Strict tenant boundary enforced (HTTP 404 Not Found across tenants).")

    print("\n[SUCCESS] All Milestone 5 Payment-Gated Release checks passed successfully!")

if __name__ == "__main__":
    run_tests()
