from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db
from ..audit import record

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=schemas.UserOut)
def read_current_user(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


@router.get("", response_model=List[schemas.UserOut])
def list_users(db: Session = Depends(get_db), _: models.User = Depends(auth.require_manager_or_above)):
    current_user = _
    return auth.visible_user_filter(db.query(models.User), current_user).order_by(models.User.id).all()


@router.post("", response_model=schemas.UserOut)
def create_user(
    payload: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_manager_or_above),
):
    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    if current_user.role == models.UserRole.manager and payload.role != models.UserRole.employee:
        raise HTTPException(status_code=403, detail="Managers can only create employees")
    if current_user.role == models.UserRole.admin and payload.role == models.UserRole.super_admin:
        raise HTTPException(status_code=403, detail="Only a super admin can create super admins")

    organization_id = payload.organization_id or current_user.organization_id
    manager_id = payload.manager_id
    if current_user.role == models.UserRole.super_admin and payload.role != models.UserRole.super_admin and organization_id is None:
        raise HTTPException(status_code=400, detail="An organization is required for non-super-admin users")
    if current_user.role == models.UserRole.manager:
        organization_id = current_user.organization_id
        manager_id = current_user.id

    _validate_assignment(db, current_user, payload.role, organization_id, manager_id)

    user = models.User(
        name=payload.name,
        email=payload.email,
        hashed_password=auth.hash_password(payload.password),
        role=payload.role,
        organization_id=organization_id,
        manager_id=manager_id,
    )
    db.add(user)
    db.commit()
    record(db, current_user, "user.created", "user", details={"email": user.email, "role": user.role.value})
    db.refresh(user)
    return user

@router.get("/{user_id}", response_model=schemas.UserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_manager_or_above),
):
    user = auth.visible_user_filter(db.query(models.User), current_user).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _validate_assignment(db, actor, role, organization_id, manager_id, target=None):
    if role == models.UserRole.super_admin:
        if organization_id is not None or manager_id is not None:
            raise HTTPException(status_code=400, detail="Super admins cannot belong to an organization or manager")
        if actor.role != models.UserRole.super_admin:
            raise HTTPException(status_code=403, detail="Only a super admin can assign super admins")
        return
    if organization_id is None:
        raise HTTPException(status_code=400, detail="Organization is required")
    if not db.query(models.Organization).filter(models.Organization.id == organization_id).first():
        raise HTTPException(status_code=400, detail="Organization not found")
    if actor.role == models.UserRole.admin and organization_id != actor.organization_id:
        raise HTTPException(status_code=403, detail="Admins can only manage their organization")
    if actor.role == models.UserRole.manager and organization_id != actor.organization_id:
        raise HTTPException(status_code=403, detail="Managers can only manage their organization")
    if manager_id is not None:
        if target is not None and manager_id == target.id:
            raise HTTPException(status_code=400, detail="A user cannot manage themselves")
        manager = db.query(models.User).filter(models.User.id == manager_id).first()
        if not manager or manager.role != models.UserRole.manager or manager.organization_id != organization_id:
            raise HTTPException(status_code=400, detail="Manager must belong to the selected organization")
        if actor.role == models.UserRole.manager and manager.id != actor.id:
            raise HTTPException(status_code=403, detail="Managers can only assign their own team")


@router.patch("/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: int,
    payload: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_manager_or_above),
):
    user = auth.visible_user_filter(db.query(models.User), current_user).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    next_role = payload.role or user.role
    next_org = payload.organization_id if "organization_id" in payload.model_fields_set else user.organization_id
    next_manager = payload.manager_id if "manager_id" in payload.model_fields_set else user.manager_id
    if current_user.role == models.UserRole.manager:
        if next_role != models.UserRole.employee or user.manager_id != current_user.id:
            raise HTTPException(status_code=403, detail="Managers can only edit their own employees")
        next_org = current_user.organization_id
        next_manager = current_user.id
    if current_user.role == models.UserRole.admin and next_role == models.UserRole.super_admin:
        raise HTTPException(status_code=403, detail="Only a super admin can assign super admins")
    _validate_assignment(db, current_user, next_role, next_org, next_manager, user)
    if payload.email and payload.email != user.email and db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    for field in ("name", "email", "is_active"):
        value = getattr(payload, field)
        if value is not None:
            setattr(user, field, value)
    if payload.password:
        user.hashed_password = auth.hash_password(payload.password)
    user.role = next_role
    user.organization_id = next_org
    user.manager_id = next_manager
    record(db, current_user, "user.updated", "user", user.id, {"role": user.role.value, "organization_id": user.organization_id, "manager_id": user.manager_id})
    db.commit()
    db.refresh(user)
    return user