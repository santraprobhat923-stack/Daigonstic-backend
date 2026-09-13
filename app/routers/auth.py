from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app import models, schemas, utils
from app.database import get_db

router = APIRouter(tags=["Authentication"])


@router.post("/login", response_model=schemas.Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    # OAuth2PasswordRequestForm sends the email in a field named 'username'
    user = db.query(models.User).filter(models.User.email == form_data.username).first()

    if not user or not utils.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Payload embedded directly inside the secure token
    token_payload = {
        "sub": str(user.id),
        "centre_id": user.centre_id,
        "role": user.role
    }

    access_token = utils.create_access_token(data=token_payload)

    return {"access_token": access_token, "token_type": "bearer"}
