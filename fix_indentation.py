with open("app/services/background_worker.py", "r") as f:
    lines = f.readlines()

new_lines = []
skip = False
for i, line in enumerate(lines):
    # Fix the target block replacement cleanly
    if "if result.rowcount == 1:" in line:
        new_lines.append(line)
        indent = line[:line.index("if")]
        new_lines.append(indent + "    job = db.query(NotificationJob).filter(NotificationJob.id == job_id).first()\n")
        new_lines.append(indent + "    if job:\n")
        new_lines.append(indent + "        try:\n")
        new_lines.append(indent + "            log_audit_event(\n")
        new_lines.append(indent + "                db=db,\n")
        new_lines.append(indent + "                centre_id=job.centre_id,\n")
        new_lines.append(indent + "                event_type=\"JOB_CLAIMED\",\n")
        new_lines.append(indent + "                entity_type=\"NOTIFICATION_JOB\",\n")
        new_lines.append(indent + "                entity_id=job.id,\n")
        new_lines.append(indent + "                payload={\"job_id\": job.id, \"worker_id\": self.worker_id}\n")
        new_lines.append(indent + "            )\n")
        new_lines.append(indent + "            db.commit()\n")
        new_lines.append(indent + "        except Exception:\n")
        new_lines.append(indent + "            pass\n")
        new_lines.append(indent + "    return job\n")
        # Skip the original lines that followed result.rowcount == 1
        skip = True
    elif skip:
        if "return" in line or "else:" in line or "db.query" in line:
            continue
        else:
            skip = False
            new_lines.append(line)
    else:
        new_lines.append(line)

with open("app/services/background_worker.py", "w") as f:
    f.writelines(new_lines)

print("Indentation fixed successfully!")
