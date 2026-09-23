import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from . import models
from .database import get_db

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(subject: str, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if user.role not in (models.UserRole.super_admin, models.UserRole.admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return user


def require_super_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if user.role != models.UserRole.super_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required")
    return user


def require_manager_or_above(user: models.User = Depends(get_current_user)) -> models.User:
    if user.role not in (
        models.UserRole.super_admin,
        models.UserRole.admin,
        models.UserRole.manager,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager access required")
    return user


def visible_user_filter(query, current_user: models.User):
    """Limit organization data to the caller's permitted team boundary."""
    if current_user.role == models.UserRole.super_admin:
        return query
    if current_user.role == models.UserRole.admin:
        return query.filter(
            models.User.organization_id == current_user.organization_id,
            models.User.role != models.UserRole.super_admin,
        )
    if current_user.role == models.UserRole.manager:
        visible_ids = {current_user.id}
        frontier = [current_user.id]
        while frontier:
            child_ids = [row[0] for row in query.session.query(models.User.id).filter(models.User.manager_id.in_(frontier)).all()]
            frontier = [child_id for child_id in child_ids if child_id not in visible_ids]
            visible_ids.update(frontier)
        return query.filter(models.User.id.in_(visible_ids))
    return query.filter(models.User.id == current_user.id)
