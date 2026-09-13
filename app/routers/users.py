from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas, utils, oauth2
from app.database import get_db

router = APIRouter(
    prefix="/users",
    tags=["Users"]
)


# --- ROUTE 1: GET CURRENT LOGGED-IN USER ---
@router.get("/me", response_model=schemas.UserResponse)
def get_current_user_profile(
    current_user: models.User = Depends(oauth2.get_current_user)
):
    """Protected route: Returns the profile of the currently logged-in user."""
    return current_user


# --- ROUTE 2: REGISTER A NEW USER ---
@router.post("/", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # 1. Verify that the assigned diagnostic centre exists
    centre = db.query(models.Centre).filter(models.Centre.id == user.centre_id).first()
    if not centre:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Diagnostic centre with id {user.centre_id} does not exist."
        )

    # 2. Check if the email is already registered
    existing_user = db.query(models.User).filter(models.User.email == user.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists."
        )

    # 3. Hash the plain-text password
    hashed_pwd = utils.hash_password(user.password)

    # 4. Save the user record tied to the centre_id
    db_user = models.User(
        email=user.email,
        hashed_password=hashed_pwd,
        role=user.role,
        is_active=user.is_active,
        centre_id=user.centre_id,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user


# --- ROUTE 3: LIST ALL USERS ---
@router.get("/", response_model=List[schemas.UserResponse])
def get_all_users(db: Session = Depends(get_db)):
    users = db.query(models.User).all()
    return users
