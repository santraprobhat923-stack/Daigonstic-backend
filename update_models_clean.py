with open("app/models.py", "r") as f:
    lines = f.readlines()

new_lines = []
skip = False
for line in lines:
    if "class AuditEvent(Base):" in line:
        skip = True
        new_lines.append(line)
        new_lines.append("    __tablename__ = 'audit_events'\n\n")
        new_lines.append("    id = Column(Integer, primary_key=True, index=True)\n")
        new_lines.append("    centre_id = Column(Integer, ForeignKey('centres.id'), nullable=False, index=True)\n")
        new_lines.append("    event_type = Column(String, nullable=False)\n")
        new_lines.append("    entity_type = Column(String, nullable=False)\n")
        new_lines.append("    entity_id = Column(Integer, nullable=False)\n")
        new_lines.append("    payload = Column(JSON, nullable=True)\n")
        new_lines.append("    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)\n")
        new_lines.append("    schema_version = Column(Integer, default=1, nullable=False)\n")
        new_lines.append("    canonical_payload = Column(Text, nullable=True)\n")
        new_lines.append("    previous_event_hash = Column(String(64), nullable=True)\n")
        new_lines.append("    event_hash = Column(String(64), nullable=True)\n")
        new_lines.append("    is_chained = Column(Boolean, default=False, nullable=False)\n")
        new_lines.append("    sequence_id = Column(Integer, nullable=True)\n")
    elif skip and line.strip().startswith("class "):
        skip = False
        new_lines.append(line)
    elif skip:
        continue
    else:
        new_lines.append(line)

with open("app/models.py", "w") as f:
    f.writelines(new_lines)

print("app/models.py successfully updated with M10 cryptographic fields.")
