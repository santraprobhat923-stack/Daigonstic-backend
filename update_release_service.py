with open("app/services/release_service.py", "r") as f:
    code = f.read()

# 1. Ensure required models are imported
if "from app.models import NotificationJob" not in code:
    code = code.replace("from app import models", "from app import models\nfrom app.models import NotificationJob, Order, Patient")

# 2. Add transactional NotificationJob creation right before db.commit()
old_block = """        report.is_released = True
        report.release_status = "RELEASED"
        report.released_at = datetime.utcnow()
        report.released_by = user_id

        db.commit()
        db.refresh(report)

        return True, "Report released successfully.", report"""

new_block = """        report.is_released = True
        report.release_status = "RELEASED"
        report.released_at = datetime.utcnow()
        report.released_by = user_id

        # Milestone 6: Durable Notification Job Creation in same transaction
        existing_job = db.query(NotificationJob).filter(
            NotificationJob.centre_id == centre_id,
            NotificationJob.report_id == report.id,
            NotificationJob.notification_type == "REPORT_RELEASED",
            NotificationJob.channel == "SMS"
        ).first()

        if not existing_job:
            order = db.query(Order).filter(Order.id == report.order_id, Order.centre_id == centre_id).first()
            patient = db.query(Patient).filter(Patient.id == order.patient_id).first() if order else None

            # Safe privacy message: zero clinical findings, diagnosis, or test values
            msg_text = "Your diagnostic report is now available. Please use the authorized access portal provided by your diagnostic centre to view your verified report."

            recipient_contact = None
            if patient:
                recipient_contact = getattr(patient, "phone", None) or getattr(patient, "mobile", None) or getattr(patient, "contact_number", None) or getattr(patient, "email", None)

            if not recipient_contact:
                job = NotificationJob(
                    centre_id=centre_id,
                    report_id=report.id,
                    patient_id=order.patient_id if order else 0,
                    notification_type="REPORT_RELEASED",
                    channel="SMS",
                    recipient="UNKNOWN",
                    message_payload=msg_text,
                    status="SKIPPED",
                    last_error="No usable contact information found for patient"
                )
            else:
                job = NotificationJob(
                    centre_id=centre_id,
                    report_id=report.id,
                    patient_id=order.patient_id if order else 0,
                    notification_type="REPORT_RELEASED",
                    channel="SMS",
                    recipient=str(recipient_contact),
                    message_payload=msg_text,
                    status="PENDING"
                )
            db.add(job)

        db.commit()
        db.refresh(report)

        return True, "Report released successfully.", report"""

if old_block in code:
    code = code.replace(old_block, new_block)
    with open("app/services/release_service.py", "w") as f:
        f.write(code)
    print("Successfully patched ReleaseService with durable NotificationJob creation.")
else:
    print("Could not match exact block. Let us check release_service.py content.")
