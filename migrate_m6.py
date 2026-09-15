import sqlite3

conn = sqlite3.connect("diagnostic.db")
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS notification_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    centre_id INTEGER NOT NULL,
    report_id INTEGER NOT NULL,
    patient_id INTEGER NOT NULL,
    notification_type VARCHAR(64) NOT NULL DEFAULT 'REPORT_RELEASED',
    channel VARCHAR(32) NOT NULL DEFAULT 'SMS',
    recipient VARCHAR(255) NOT NULL,
    message_payload TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    last_error TEXT,
    last_attempt_at DATETIME,
    sent_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (centre_id) REFERENCES centres (id),
    FOREIGN KEY (report_id) REFERENCES report_documents (id),
    FOREIGN KEY (patient_id) REFERENCES patients (id),
    CONSTRAINT uq_notification_idempotency UNIQUE (centre_id, report_id, notification_type, channel)
);
""")

c.execute("CREATE INDEX IF NOT EXISTS ix_notification_jobs_centre_id ON notification_jobs (centre_id);")
c.execute("CREATE INDEX IF NOT EXISTS ix_notification_jobs_report_id ON notification_jobs (report_id);")
c.execute("CREATE INDEX IF NOT EXISTS ix_notification_jobs_status ON notification_jobs (status);")

conn.commit()
conn.close()
print("Migration: notification_jobs table and indexes ensured.")
