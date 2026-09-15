with open("app/models.py", "r") as f:
    content = f.read()

# Add account_status to Centre if not present
if "account_status" not in content:
    content = content.replace(
        "phone = Column(String, nullable=False)",
        "phone = Column(String, nullable=False)\n    account_status = Column(String, default='ACTIVE', nullable=False)"
    )

# Add CentreActivationKey model at the end of models.py
activation_key_model = """

class CentreActivationKey(Base):
    __tablename__ = 'centre_activation_keys'

    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, ForeignKey('centres.id'), nullable=False, index=True)
    key_hash = Column(String(64), nullable=False, unique=True)
    status = Column(String(20), default='UNUSED', nullable=False) # UNUSED, USED, REVOKED, EXPIRED
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    activated_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
"""

if "CentreActivationKey" not in content:
    content += activation_key_model

with open("app/models.py", "w") as f:
    f.write(content)

print("app/models.py updated with M11 activation models.")
