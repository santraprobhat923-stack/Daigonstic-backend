from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas, oauth2
from app.database import get_db

router = APIRouter(
    prefix="/tests",
    tags=["Lab Tests"]
)


@router.post("/", response_model=schemas.TestResponse, status_code=status.HTTP_201_CREATED)
def create_test(
    test: schemas.TestCreate,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(oauth2.require_admin)  # Restricted to Admin
):
    existing = db.query(models.Test).filter(
        models.Test.centre_id == admin_user.centre_id,
        models.Test.code == test.code
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Test with code '{test.code}' already exists."
        )

    db_test = models.Test(
        name=test.name,
        code=test.code,
        category=test.category,
        price=test.price,
        description=test.description,
        centre_id=admin_user.centre_id
    )
    db.add(db_test)
    db.commit()
    db.refresh(db_test)
    return db_test


@router.get("/", response_model=List[schemas.TestResponse])
def get_all_tests(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)  # Staff can view
):
    return db.query(models.Test).filter(
        models.Test.centre_id == current_user.centre_id
    ).all()
