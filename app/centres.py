from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(
    prefix="/centres",
    tags=["Diagnostic Centres"]
)


@router.post("/", response_model=schemas.CentreResponse, status_code=status.HTTP_201_CREATED)
def create_centre(centre: schemas.CentreCreate, db: Session = Depends(get_db)):
    # 1. Convert Pydantic schema data into an ORM model instance
    db_centre = models.Centre(
        name=centre.name,
        address=centre.address,
        phone=centre.phone
    )
    
    # 2. Add and commit to SQLite
    db.add(db_centre)
    db.commit()
    
    # 3. Refresh to populate generated attributes (like id and created_at)
    db.refresh(db_centre)
    
    return db_centre


@router.get("/", response_model=List[schemas.CentreResponse])
def get_all_centres(db: Session = Depends(get_db)):
    # Fetch all diagnostic centre records
    centres = db.query(models.Centre).all()
    return centres
