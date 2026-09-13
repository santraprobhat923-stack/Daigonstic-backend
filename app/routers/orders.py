from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas, oauth2
from app.database import get_db

router = APIRouter(
    prefix="/orders",
    tags=["Lab Orders"]
)


@router.post("/", response_model=schemas.OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(
    order_in: schemas.OrderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.require_technician)
):
    if not order_in.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order must contain at least one test item."
        )

    # 1. Verify Patient exists in current centre
    patient = db.query(models.Patient).filter(
        models.Patient.id == order_in.patient_id,
        models.Patient.centre_id == current_user.centre_id
    ).first()
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient {order_in.patient_id} not found in this centre."
        )

    # 2. Validate tests and compute subtotal using price snapshots
    subtotal = 0
    order_items_to_create = []

    for item in order_in.items:
        test = db.query(models.Test).filter(
            models.Test.id == item.test_id,
            models.Test.centre_id == current_user.centre_id
        ).first()

        if not test:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Test {item.test_id} not found in this centre's catalogue."
            )

        quantity = item.quantity if item.quantity and item.quantity > 0 else 1
        subtotal += test.price * quantity

        order_items_to_create.append(
            models.OrderItem(
                test_id=test.id,
                quantity=quantity,
                unit_price=test.price  # Price snapshot
            )
        )

    total_amount = max(0, subtotal - order_in.discount)

    # 3. Create Order
    db_order = models.Order(
        patient_id=order_in.patient_id,
        centre_id=current_user.centre_id,
        subtotal=subtotal,
        discount=order_in.discount,
        total_amount=total_amount,
        status="pending"
    )
    db.add(db_order)
    db.flush()  # Obtain db_order.id

    for order_item in order_items_to_create:
        order_item.order_id = db_order.id
        db.add(order_item)

    db.commit()
    db.refresh(db_order)
    return db_order


@router.get("/", response_model=List[schemas.OrderResponse])
def get_all_orders(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    return db.query(models.Order).filter(
        models.Order.centre_id == current_user.centre_id
    ).all()
