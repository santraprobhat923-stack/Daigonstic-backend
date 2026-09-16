"""Create or reset a local/staging centre-admin account.

This script deliberately reads the password from an environment variable so no
plaintext credential is committed to Git.

Example:
  DIAGNOSTIC_ADMIN_EMAIL='stagingadmin@diagnostic-demo.local' \
  DIAGNOSTIC_ADMIN_PASSWORD='change-me' \
  python scripts/seed_admin.py

Optional:
  DIAGNOSTIC_CENTRE_ID=1

If no centre ID is supplied, the first existing centre is used. If there are no
centres, a clearly named demo centre is created.
"""

import os
import sys
from pathlib import Path

# Allow running this file directly from the repository root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import models, utils  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402


EMAIL = os.getenv("DIAGNOSTIC_ADMIN_EMAIL", "").strip().lower()
PASSWORD = os.getenv("DIAGNOSTIC_ADMIN_PASSWORD", "")
CENTRE_ID = os.getenv("DIAGNOSTIC_CENTRE_ID", "").strip()


def main() -> None:
    if not EMAIL or not PASSWORD:
        raise SystemExit(
            "Set DIAGNOSTIC_ADMIN_EMAIL and DIAGNOSTIC_ADMIN_PASSWORD before running this script."
        )
    if len(PASSWORD) < 10:
        raise SystemExit("DIAGNOSTIC_ADMIN_PASSWORD must be at least 10 characters.")

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if CENTRE_ID:
            centre = db.query(models.Centre).filter(models.Centre.id == int(CENTRE_ID)).first()
            if not centre:
                raise SystemExit(f"No centre exists with id {CENTRE_ID}.")
        else:
            centre = db.query(models.Centre).order_by(models.Centre.id.asc()).first()
            if not centre:
                centre = models.Centre(
                    name="Demo Diagnostic Centre",
                    address="Local staging environment",
                    account_status="ACTIVE",
                )
                db.add(centre)
                db.flush()

        user = db.query(models.User).filter(models.User.email == EMAIL).first()
        password_hash = utils.hash_password(PASSWORD)

        if user:
            user.hashed_password = password_hash
            user.centre_id = centre.id
            user.role = "admin"
            user.is_active = True
            action = "reset"
        else:
            user = models.User(
                email=EMAIL,
                hashed_password=password_hash,
                centre_id=centre.id,
                role="admin",
                is_active=True,
            )
            db.add(user)
            action = "created"

        db.commit()
        print(f"Admin account {action} successfully.")
        print(f"Email: {EMAIL}")
        print(f"Centre ID: {centre.id}")
        print("Password: the value supplied in DIAGNOSTIC_ADMIN_PASSWORD")
    finally:
        db.close()


if __name__ == "__main__":
    main()
