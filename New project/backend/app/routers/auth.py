import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    try:
        user = db.query(models.User).filter(models.User.email == form_data.username).first()
    except Exception:
        logger.exception("Login failed while querying user from database")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable. Please check the backend server and database connection.",
        )

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    if not user.hashed_password:
        logger.error("Login failed: user %s has no hashed_password set", user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="This account has no password set. Please reset it or recreate the user.",
        )

    try:
        password_ok = auth.verify_password(form_data.password, user.hashed_password)
    except Exception:
        logger.exception("Login failed while verifying password for user %s", user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password verification failed. The stored password hash may be corrupted or in an unexpected format.",
        )

    if not password_ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    try:
        token = auth.create_access_token(subject=user.email)
    except Exception:
        logger.exception("Login failed while creating access token for user %s", user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to issue access token. Check JWT_SECRET_KEY/JWT_ALGORITHM configuration and that python-jose is installed correctly.",
        )

    return schemas.Token(access_token=token)
