from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas, oauth2
from app.database import get_db
from app.services import credit_service

router = APIRouter(
    prefix="/credits",
    tags=["Centre Credits & Billing"]
)

@router.get("/balance", response_model=schemas.CreditBalanceResponse)
def get_centre_balance(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    account = credit_service.get_or_create_account(db, current_user.centre_id)
    return schemas.CreditBalanceResponse(
        centre_id=account.centre_id,
        balance=account.balance,
        low_credit=account.balance < credit_service.LOW_CREDIT_THRESHOLD,
        threshold=credit_service.LOW_CREDIT_THRESHOLD,
        updated_at=account.updated_at
    )

@router.get("/transactions", response_model=List[schemas.CreditTransactionResponse])
def get_credit_transactions(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    query = db.query(models.CreditTransaction).filter(
        models.CreditTransaction.centre_id == current_user.centre_id
    )
    if start_date:
        query = query.filter(models.CreditTransaction.created_at >= start_date)
    if end_date:
        query = query.filter(models.CreditTransaction.created_at <= end_date)

    return query.order_by(models.CreditTransaction.created_at.desc()).all()

@router.post("/recharge", response_model=schemas.CreditPurchaseResponse, status_code=status.HTTP_201_CREATED)
def request_credit_recharge(
    payload: schemas.CreditRechargeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    price_rate = credit_service.DEFAULT_PRICE_PER_CREDIT
    total_amount = float(payload.credits * price_rate)

    purchase = models.CreditPurchase(
        centre_id=current_user.centre_id,
        amount_paid=total_amount,
        credits=payload.credits,
        price_per_credit=price_rate,
        payment_method=payload.payment_method or "manual",
        payment_reference=payload.payment_reference,
        status=models.PurchaseStatusEnum.pending
    )
    db.add(purchase)
    db.commit()
    db.refresh(purchase)
    return purchase

@router.get("/recharges", response_model=List[schemas.CreditPurchaseResponse])
def get_recharge_requests(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    return db.query(models.CreditPurchase).filter(
        models.CreditPurchase.centre_id == current_user.centre_id
    ).order_by(models.CreditPurchase.created_at.desc()).all()

@router.post("/admin/grant", response_model=schemas.CreditBalanceResponse)
def admin_grant_credits(
    payload: schemas.AdminCreditGrantRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.require_admin)
):
    # DEF-05: Enforce that centre admins can ONLY grant credits to their own centre
    if current_user.role != models.UserRoleEnum.superadmin:
        if payload.centre_id != current_user.centre_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Centre admins cannot modify credits for another tenant."
            )

    target = db.query(models.Centre).filter(models.Centre.id == payload.centre_id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target centre not found.")

    new_balance = credit_service.add_credits(
        db=db,
        centre_id=payload.centre_id,
        amount=payload.amount,
        transaction_type=models.TransactionTypeEnum.admin_grant,
        user_id=current_user.id,
        reference_type="admin_grant",
        description=payload.description
    )

    return schemas.CreditBalanceResponse(
        centre_id=payload.centre_id,
        balance=new_balance,
        low_credit=new_balance < credit_service.LOW_CREDIT_THRESHOLD,
        threshold=credit_service.LOW_CREDIT_THRESHOLD,
        updated_at=datetime.utcnow()
    )

@router.put("/admin/recharge/{purchase_id}/review", response_model=schemas.CreditPurchaseResponse)
def review_recharge_request(
    purchase_id: int,
    action: schemas.RechargeApprovalAction,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.require_admin)
):
    purchase = db.query(models.CreditPurchase).filter(models.CreditPurchase.id == purchase_id).first()
    if not purchase:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recharge request not found.")

    if current_user.role != models.UserRoleEnum.superadmin and purchase.centre_id != current_user.centre_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: Cannot review another tenant's recharge.")

    if purchase.status != models.PurchaseStatusEnum.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recharge is already finalized.")

    if action.approve:
        purchase.status = models.PurchaseStatusEnum.approved
        purchase.approved_at = datetime.utcnow()
        purchase.approved_by = current_user.id

        credit_service.add_credits(
            db=db,
            centre_id=purchase.centre_id,
            amount=purchase.credits,
            transaction_type=models.TransactionTypeEnum.purchase,
            user_id=current_user.id,
            reference_type="purchase",
            reference_id=purchase.id,
            description=f"Purchase approval for Rs. {purchase.amount_paid} ({action.notes or 'Manual'})"
        )
    else:
        purchase.status = models.PurchaseStatusEnum.rejected
        purchase.approved_at = datetime.utcnow()
        purchase.approved_by = current_user.id

    db.commit()
    db.refresh(purchase)
    return purchase
