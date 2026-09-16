import sqlite3
import shutil
import os
from datetime import datetime

DB = "diagnostic.db"
BACKUP = f"diagnostic.db.backup_phase1_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

print("=" * 70)
print("DIAGNOSTIC BACKEND — SCHEMA REPAIR PHASE 1")
print("=" * 70)

if not os.path.exists(DB):
    raise SystemExit(f"ERROR: {DB} not found")

# ------------------------------------------------------------
# 1. BACKUP
# ------------------------------------------------------------
shutil.copy2(DB, BACKUP)
print(f"[OK] Database backup created: {BACKUP}")

db = sqlite3.connect(DB)
db.execute("PRAGMA foreign_keys=ON")
cur = db.cursor()


def table_exists(name):
    return cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)
    ).fetchone() is not None


def columns(table):
    return {
        row[1]
        for row in cur.execute(f'PRAGMA table_info("{table}")').fetchall()
    }


def add_column(table, name, definition):
    if name not in columns(table):
        print(f"[ADD COLUMN] {table}.{name}")
        cur.execute(
            f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}'
        )
    else:
        print(f"[EXISTS] {table}.{name}")


# ------------------------------------------------------------
# 2. CENTRES
# ------------------------------------------------------------
if table_exists("centres"):
    add_column("centres", "account_status", "VARCHAR DEFAULT 'ACTIVE'")


# ------------------------------------------------------------
# 3. USERS
# ------------------------------------------------------------
if table_exists("users"):
    # Compatibility fields used by older authentication code.
    add_column("users", "created_at", "DATETIME")


# ------------------------------------------------------------
# 4. PATIENTS
# ------------------------------------------------------------
if table_exists("patients"):
    add_column("patients", "phone", "VARCHAR")
    add_column("patients", "email", "VARCHAR")


# ------------------------------------------------------------
# 5. REPORT INGESTION JOBS
# ------------------------------------------------------------
if table_exists("report_ingestion_jobs"):

    # Current image-first pipeline.
    add_column("report_ingestion_jobs", "patient_id", "INTEGER")
    add_column("report_ingestion_jobs", "extracted_data", "TEXT")
    add_column("report_ingestion_jobs", "verified_data", "TEXT")
    add_column("report_ingestion_jobs", "verified_at", "DATETIME")
    add_column("report_ingestion_jobs", "verified_by", "INTEGER")
    add_column("report_ingestion_jobs", "final_report_id", "INTEGER")

    # Worker/retry compatibility fields.
    add_column("report_ingestion_jobs", "attempt_count", "INTEGER DEFAULT 0")
    add_column("report_ingestion_jobs", "max_retries", "INTEGER DEFAULT 3")
    add_column("report_ingestion_jobs", "last_error", "TEXT")
    add_column("report_ingestion_jobs", "started_at", "DATETIME")
    add_column("report_ingestion_jobs", "completed_at", "DATETIME")


# ------------------------------------------------------------
# 6. REPORT DOCUMENTS
# ------------------------------------------------------------
if table_exists("report_documents"):

    # Current authoritative report lifecycle.
    add_column("report_documents", "release_status", "VARCHAR DEFAULT 'HELD_PAYMENT'")
    add_column("report_documents", "is_released", "BOOLEAN DEFAULT 0")
    add_column("report_documents", "released_at", "DATETIME")
    add_column("report_documents", "released_by", "INTEGER")

    # Authoritative PDF metadata.
    add_column("report_documents", "pdf_path", "VARCHAR")
    add_column("report_documents", "pdf_filename", "VARCHAR")
    add_column("report_documents", "pdf_hash", "VARCHAR")
    add_column("report_documents", "pdf_size", "INTEGER")

    # Verification linkage.
    add_column("report_documents", "ingestion_job_id", "INTEGER")
    add_column("report_documents", "verified_at", "DATETIME")
    add_column("report_documents", "verified_by", "INTEGER")


# ------------------------------------------------------------
# 7. NOTIFICATION JOBS
# ------------------------------------------------------------
if not table_exists("notification_jobs"):
    print("[CREATE TABLE] notification_jobs")

    cur.execute("""
        CREATE TABLE notification_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            centre_id INTEGER NOT NULL,
            report_id INTEGER,
            patient_id INTEGER,
            notification_type VARCHAR NOT NULL,
            channel VARCHAR NOT NULL,
            recipient VARCHAR,
            message_payload TEXT,
            status VARCHAR DEFAULT 'PENDING',

            attempt_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,

            last_error TEXT,

            next_attempt_at DATETIME,
            locked_at DATETIME,
            locked_by VARCHAR,

            started_at DATETIME,
            last_attempt_at DATETIME,
            sent_at DATETIME,
            completed_at DATETIME,
            dead_lettered_at DATETIME,

            original_filename VARCHAR,
            file_size INTEGER,
            source_image_hash VARCHAR,
            source_image_path VARCHAR,

            created_at DATETIME
        )
    """)
else:
    print("[EXISTS] notification_jobs")


# ------------------------------------------------------------
# 8. AUDIT EVENTS
# ------------------------------------------------------------
if not table_exists("audit_events"):
    print("[CREATE TABLE] audit_events")

    cur.execute("""
        CREATE TABLE audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            centre_id INTEGER NOT NULL,

            event_type VARCHAR NOT NULL,
            entity_type VARCHAR NOT NULL,
            entity_id INTEGER,

            payload TEXT,
            schema_version INTEGER DEFAULT 1,

            canonical_payload TEXT,

            previous_event_hash VARCHAR,
            event_hash VARCHAR,

            is_chained BOOLEAN DEFAULT 1,
            sequence_id INTEGER,

            timestamp DATETIME,
            created_at DATETIME
        )
    """)
else:
    print("[EXISTS] audit_events")


# ------------------------------------------------------------
# 9. CENTRE ACTIVATION KEYS
# ------------------------------------------------------------
if not table_exists("centre_activation_keys"):
    print("[CREATE TABLE] centre_activation_keys")

    cur.execute("""
        CREATE TABLE centre_activation_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            centre_id INTEGER NOT NULL,
            key_hash VARCHAR NOT NULL,
            status VARCHAR DEFAULT 'ACTIVE',
            created_at DATETIME,
            used_at DATETIME
        )
    """)
else:
    print("[EXISTS] centre_activation_keys")


# ------------------------------------------------------------
# 10. PATIENT REPORT ACCESS TOKENS
# ------------------------------------------------------------
if not table_exists("patient_report_access_tokens"):
    print("[CREATE TABLE] patient_report_access_tokens")

    cur.execute("""
        CREATE TABLE patient_report_access_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            centre_id INTEGER NOT NULL,
            patient_id INTEGER NOT NULL,
            report_id INTEGER NOT NULL,
            token_hash VARCHAR NOT NULL,
            expires_at DATETIME,
            used_at DATETIME,
            status VARCHAR DEFAULT 'ACTIVE',
            created_at DATETIME
        )
    """)
else:
    print("[EXISTS] patient_report_access_tokens")


# ------------------------------------------------------------
# 11. EXISTING OPERATIONAL TABLES — MISSING TIMESTAMP COMPAT
# ------------------------------------------------------------
if table_exists("centre_credit_accounts"):
    add_column("centre_credit_accounts", "created_at", "DATETIME")

if table_exists("credit_purchases"):
    # Existing schema already contains the important business fields.
    pass

if table_exists("credit_transactions"):
    pass


# ------------------------------------------------------------
# 12. INDEXES
# ------------------------------------------------------------
print("[INDEXES] Creating safe indexes")

indexes = [
    (
        "idx_report_ingestion_centre_status",
        "report_ingestion_jobs",
        "(centre_id, status)"
    ),
    (
        "idx_report_ingestion_hash",
        "report_ingestion_jobs",
        "(source_image_hash)"
    ),
    (
        "idx_notification_status_next",
        "notification_jobs",
        "(status, next_attempt_at)"
    ),
    (
        "idx_notification_report",
        "notification_jobs",
        "(centre_id, report_id)"
    ),
    (
        "idx_audit_chain",
        "audit_events",
        "(centre_id, sequence_id)"
    ),
    (
        "idx_activation_centre",
        "centre_activation_keys",
        "(centre_id, status)"
    ),
    (
        "idx_access_token_report",
        "patient_report_access_tokens",
        "(centre_id, report_id, status)"
    ),
]

for name, table, cols in indexes:
    if table_exists(table):
        try:
            cur.execute(
                f'CREATE INDEX IF NOT EXISTS "{name}" '
                f'ON "{table}" {cols}'
            )
            print(f"[OK] {name}")
        except Exception as e:
            print(f"[WARN] Could not create {name}: {e}")


# ------------------------------------------------------------
# 13. NORMALIZE EXISTING NULL DEFAULTS WHERE SAFE
# ------------------------------------------------------------
if table_exists("centres"):
    cur.execute("""
        UPDATE centres
        SET account_status = 'ACTIVE'
        WHERE account_status IS NULL
    """)

if table_exists("report_documents"):
    cur.execute("""
        UPDATE report_documents
        SET release_status = 'HELD_PAYMENT'
        WHERE release_status IS NULL
    """)

    cur.execute("""
        UPDATE report_documents
        SET is_released = 0
        WHERE is_released IS NULL
    """)


# ------------------------------------------------------------
# 14. COMMIT
# ------------------------------------------------------------
db.commit()


# ------------------------------------------------------------
# 15. VERIFICATION
# ------------------------------------------------------------
print()
print("=" * 70)
print("POST-REPAIR VERIFICATION")
print("=" * 70)

tables = [
    "centres",
    "users",
    "patients",
    "orders",
    "billing",
    "report_documents",
    "report_ingestion_jobs",
    "tests",
    "centre_credit_accounts",
    "credit_purchases",
    "credit_transactions",
    "notification_jobs",
    "audit_events",
    "centre_activation_keys",
    "patient_report_access_tokens",
]

for table in tables:
    if table_exists(table):
        count = cur.execute(
            f'SELECT COUNT(*) FROM "{table}"'
        ).fetchone()[0]

        print(f"{table:32} rows={count}")
    else:
        print(f"{table:32} MISSING")

print()
print("Existing critical records:")

for table in ["centres", "users", "patients", "report_ingestion_jobs"]:
    if table_exists(table):
        rows = cur.execute(
            f'SELECT * FROM "{table}" LIMIT 3'
        ).fetchall()

        print(f"\n--- {table} ---")
        for row in rows:
            print(row)

db.close()

print()
print("=" * 70)
print("PHASE 1 COMPLETE")
print(f"Backup: {BACKUP}")
print("=" * 70)
