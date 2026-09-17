from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app import models

LOW_CREDIT_THRESHOLD = 10
# Business pricing: one generated PDF consumes one credit; default price is ₹3/credit.
DEFAULT_PRICE_PER_CREDIT = 3.0
# Temporary development/test allowance. This is not the final commercial onboarding amount.
DEFAULT_TEST_CREDITS = 50

def get_or_create_account(db: Session, centre_id: int) -> models.CentreCreditAccount:
    account = db.query(models.CentreCreditAccount).filter(
        models.CentreCreditAccount.centre_id == centre_id
    ).first()
    if not account:
        account = models.CentreCreditAccount(
            centre_id=centre_id,
            balance=DEFAULT_TEST_CREDITS,
            updated_at=datetime.utcnow()
        )
        db.add(account)
        db.flush()
        tx = models.CreditTransaction(
            centre_id=centre_id,
            amount=DEFAULT_TEST_CREDITS,
            balance_after=DEFAULT_TEST_CREDITS,
            transaction_type=models.TransactionTypeEnum.admin_grant,
            reference_type="test_initial_balance",
            description="Temporary development/test credits",
            created_at=datetime.utcnow()
        )
        db.add(tx)
        db.commit()
        db.refresh(account)
    elif account.balance == 0:
        # Existing test databases created before the 50-credit default get the allowance once.
        prior = db.query(models.CreditTransaction).filter(
            models.CreditTransaction.centre_id == centre_id
        ).first()
        if not prior:
            account.balance = DEFAULT_TEST_CREDITS
            account.updated_at = datetime.utcnow()
            db.add(models.CreditTransaction(
                centre_id=centre_id,
                amount=DEFAULT_TEST_CREDITS,
                balance_after=DEFAULT_TEST_CREDITS,
                transaction_type=models.TransactionTypeEnum.admin_grant,
                reference_type="test_initial_balance",
                description="Temporary development/test credits",
                created_at=datetime.utcnow()
            ))
            db.commit()
            db.refresh(account)
    return account

def add_credits(db: Session, centre_id: int, amount: int, transaction_type: models.TransactionTypeEnum,
                user_id: int = None, reference_type: str = None, reference_id: int = None,
                description: str = None) -> int:
    query = db.query(models.CentreCreditAccount).filter(models.CentreCreditAccount.centre_id == centre_id)
    if db.bind.dialect.name != "sqlite": query = query.with_for_update()
    account = query.first()
    if not account:
        account = models.CentreCreditAccount(centre_id=centre_id, balance=amount, updated_at=datetime.utcnow())
        db.add(account); db.flush()
    else:
        account.balance += amount; account.updated_at = datetime.utcnow()
    tx = models.CreditTransaction(
        centre_id=centre_id, user_id=user_id, amount=amount, balance_after=account.balance,
        transaction_type=transaction_type, reference_type=reference_type, reference_id=reference_id,
        description=description, created_at=datetime.utcnow()
    )
    db.add(tx); db.commit(); db.refresh(account)
    return account.balance

def deduct_credit_locked(db: Session, centre_id: int, amount: int, user_id: int,
                         reference_type: str, reference_id: int = None, description: str = None) -> int:
    query = db.query(models.CentreCreditAccount).filter(models.CentreCreditAccount.centre_id == centre_id)
    if db.bind.dialect.name != "sqlite": query = query.with_for_update()
    account = query.first()
    if not account or account.balance < amount:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED,
                            detail="Insufficient report credits. Please recharge your balance.")
    account.balance -= amount
    account.updated_at = datetime.utcnow()
    tx = models.CreditTransaction(
        centre_id=centre_id, user_id=user_id, amount=-amount, balance_after=account.balance,
        transaction_type=models.TransactionTypeEnum.report_upload, reference_type=reference_type,
        reference_id=reference_id, description=description, created_at=datetime.utcnow()
    )
    db.add(tx); db.flush()
    return account.balance
