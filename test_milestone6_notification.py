import sqlite3
from fastapi.testclient import TestClient
from main import app
from app.utils import create_access_token
from app.routers.notifications import default_mock_provider
from app.services.notification_provider import MockNotificationProvider

client = TestClient(app)

def run_tests():
    print("=== Running Milestone 6 Notification Dispatch Tests ===")

    conn = sqlite3.connect("diagnostic.db")
    c = conn.cursor()

    # Get sample centre, report, and patient
    c.execute("SELECT id, centre_id, order_id FROM report_documents LIMIT 1;")
    rep_id, centre_id, order_id = c.fetchone()

    # Ensure patient exists with phone
    c.execute("SELECT patient_id FROM orders WHERE id = ?;", (order_id,))
    p_row = c.fetchone()
    patient_id = p_row[0] if p_row else 1
    c.execute("UPDATE patients SET phone = '9876543210' WHERE id = ?;", (patient_id,))

    # Reset billing to paid
    c.execute("UPDATE billing SET payment_status = 'paid', paid_amount = 500.0, pending_amount = 0.0 WHERE order_id = ?;", (order_id,))
    # Reset report to unreleased
    c.execute("UPDATE report_documents SET is_released = 0, release_status = 'HELD_PAYMENT', released_at = NULL, released_by = NULL WHERE id = ?;", (rep_id,))
    # Clear prior jobs for clean test state
    c.execute("DELETE FROM notification_jobs WHERE report_id = ?;", (rep_id,))
    conn.commit()

    # Get authorized staff user
    c.execute("SELECT id, email, role FROM users WHERE centre_id = ? LIMIT 1;", (centre_id,))
    user_id, email, role = c.fetchone()
    conn.close()

    token = create_access_token(data={"sub": str(user_id), "centre_id": centre_id, "role": role})
    headers = {"Authorization": f"Bearer {token}"}

    # --- TEST 1: Payment blocked prevents release and produces zero jobs ---
    conn = sqlite3.connect("diagnostic.db")
    conn.execute("UPDATE billing SET payment_status = 'pending', pending_amount = 500.0 WHERE order_id = ?;", (order_id,))
    conn.commit()
    conn.close()

    res = client.post(f"/reports/final/{rep_id}/release", headers=headers)
    assert res.status_code == 402, f"Expected 402, got {res.status_code}"
    
    conn = sqlite3.connect("diagnostic.db")
    job_count = conn.execute("SELECT COUNT(*) FROM notification_jobs WHERE report_id = ?;", (rep_id,)).fetchone()[0]
    conn.close()
    assert job_count == 0, f"Expected 0 jobs, found {job_count}"
    print("Test 1 [PASS] Payment blocked: report unreleased, zero notification jobs created.")

    # --- TEST 2: Successful release creates durable notification job ---
    conn = sqlite3.connect("diagnostic.db")
    conn.execute("UPDATE billing SET payment_status = 'paid', pending_amount = 0.0 WHERE order_id = ?;", (order_id,))
    conn.commit()
    conn.close()

    res = client.post(f"/reports/final/{rep_id}/release", headers=headers)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"

    conn = sqlite3.connect("diagnostic.db")
    c = conn.cursor()
    c.execute("SELECT id, status, message_payload, recipient FROM notification_jobs WHERE report_id = ?;", (rep_id,))
    job_row = c.fetchone()
    conn.close()
    assert job_row is not None, "Notification job was not created."
    job_id, job_status, payload, recipient = job_row
    assert job_status == "PENDING"
    print(f"Test 2 [PASS] Report released atomically with durable PENDING NotificationJob (ID: {job_id}).")

    # --- TEST 3: Privacy check - No clinical/test values in notification ---
    forbidden_terms = ["hemoglobin", "sugar", "positive", "negative", "biopsy", "diagnosis", "wbc", "rbc"]
    for term in forbidden_terms:
        assert term not in payload.lower(), f"Sensitive medical word '{term}' leaked in notification payload!"
    print("Test 3 [PASS] Privacy check: Notification payload contains zero clinical findings or test values.")

    # --- TEST 4: Dispatcher handles provider failure with failure isolation ---
    default_mock_provider.set_mode(MockNotificationProvider.MODE_TEMPORARY_FAILURE)
    res_dispatch = client.post(f"/notifications/jobs/{job_id}/dispatch", headers=headers)
    assert res_dispatch.status_code == 200
    data = res_dispatch.json()
    assert data["status"] == "FAILED"
    assert data["attempt_count"] == 1

    # Verify report remains RELEASED despite notification failure
    conn = sqlite3.connect("diagnostic.db")
    rep_status = conn.execute("SELECT release_status FROM report_documents WHERE id = ?;", (rep_id,)).fetchone()[0]
    conn.close()
    assert rep_status == "RELEASED", "Failure in notification corruptly reverted report release status!"
    print("Test 4 [PASS] Failure isolation: Provider failure marks job FAILED without affecting RELEASED report.")

    # --- TEST 5: Retry succeeds ---
    default_mock_provider.set_mode(MockNotificationProvider.MODE_SUCCESS)
    res_retry = client.post(f"/notifications/jobs/{job_id}/dispatch", headers=headers)
    assert res_retry.status_code == 200
    assert res_retry.json()["status"] == "SENT"
    assert res_retry.json()["sent_at"] is not None
    print("Test 5 [PASS] Bounded retry: Job successfully dispatched and transitioned to SENT.")

    # --- TEST 6: Idempotency of release ---
    res_repeat = client.post(f"/reports/final/{rep_id}/release", headers=headers)
    assert res_repeat.status_code == 200
    conn = sqlite3.connect("diagnostic.db")
    total_jobs = conn.execute("SELECT COUNT(*) FROM notification_jobs WHERE report_id = ?;", (rep_id,)).fetchone()[0]
    conn.close()
    assert total_jobs == 1, f"Expected 1 job due to idempotency, got {total_jobs}"
    print("Test 6 [PASS] Idempotency: Repeated release invocations produce zero duplicate notification jobs.")

    # --- TEST 7: Tenant Isolation ---
    foreign_token = create_access_token(data={"sub": "8888", "centre_id": 9999, "role": "technician"})
    foreign_headers = {"Authorization": f"Bearer {foreign_token}"}
    res_cross = client.post(f"/notifications/jobs/{job_id}/dispatch", headers=foreign_headers)
    assert res_cross.status_code == 404, f"Expected 404 for cross-tenant job dispatch, got {res_cross.status_code}"
    print("Test 7 [PASS] Tenant isolation: Cross-tenant notification job access blocked (404 Not Found).")

    # --- TEST 8: Missing contact handling ---
    conn = sqlite3.connect("diagnostic.db")
    c = conn.cursor()
    c.execute("INSERT INTO patients (centre_id, full_name, age, gender, phone) VALUES (?, 'No Contact Patient', 40, 'Other', NULL);", (centre_id,))
    no_contact_p_id = c.lastrowid
    c.execute("INSERT INTO orders (centre_id, patient_id, subtotal, discount, total_amount) VALUES (?, ?, 100.0, 0.0, 100.0);", (centre_id, no_contact_p_id))
    no_contact_ord_id = c.lastrowid
    c.execute("INSERT INTO billing (order_id, centre_id, total_amount, paid_amount, pending_amount, payment_status) VALUES (?, ?, 100.0, 100.0, 0.0, 'paid');", (no_contact_ord_id, centre_id))
    # Fetch full row dynamically to match SQLite schema exactly
    conn.row_factory = sqlite3.Row
    c_temp = conn.cursor()
    c_temp.execute("SELECT * FROM report_documents WHERE id = ?;", (rep_id,))
    row_data = dict(c_temp.fetchone())
    conn.row_factory = None

    del row_data["id"]
    row_data["order_id"] = no_contact_ord_id
    row_data["patient_id"] = no_contact_p_id
    row_data["is_released"] = 0
    row_data["release_status"] = "HELD_PAYMENT"

    cols = list(row_data.keys())
    placeholders = ", ".join(["?"] * len(cols))
    col_str = ", ".join(cols)
    values = [row_data[k] for k in cols]

    c.execute(f"INSERT INTO report_documents ({col_str}) VALUES ({placeholders});", values)
    no_contact_rep_id = c.lastrowid
    conn.commit()
    conn.close()

    res_no_contact = client.post(f"/reports/final/{no_contact_rep_id}/release", headers=headers)
    assert res_no_contact.status_code == 200

    conn = sqlite3.connect("diagnostic.db")
    nc_job = conn.execute("SELECT status, last_error FROM notification_jobs WHERE report_id = ?;", (no_contact_rep_id,)).fetchone()
    conn.close()
    assert nc_job is not None
    assert nc_job[0] == "SKIPPED"
    print("Test 8 [PASS] Missing contact info: Job gracefully handled as SKIPPED without crashing release workflow.")

    print("\n[SUCCESS] All Milestone 6 Notification Dispatch checks passed successfully!")

if __name__ == "__main__":
    run_tests()
