from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db

router = APIRouter(prefix="/users", tags=["users"])


def _is_descendant_of(db: Session, node: models.User, ancestor_id: int) -> bool:
    current = node
    seen = set()
    while current and current.parent_id and current.id not in seen:
        seen.add(current.id)
        if current.parent_id == ancestor_id:
            return True
        current = db.query(models.User).filter(models.User.id == current.parent_id).first()
    return False


def _validate_parent(
    db: Session,
    acting_user: models.User,
    target_role: models.UserRole,
    parent_id: Optional[int],
) -> Optional[models.User]:
    required_role = models.ROLE_HIERARCHY[target_role]
    if required_role is None:
        return None
    if parent_id is None:
        raise HTTPException(status_code=400, detail=f"parent_id is required when role is '{target_role.value}'.")

    parent = db.query(models.User).filter(models.User.id == parent_id).first()
    if not parent:
        raise HTTPException(status_code=404, detail=f"Parent user with id {parent_id} not found")
    if parent.role != required_role:
        raise HTTPException(
            status_code=400,
            detail=f"parent_id {parent_id} must reference a user with role '{required_role.value}'.",
        )
    if acting_user.role != models.UserRole.superadmin and parent.id != acting_user.id and not _is_descendant_of(db, parent, acting_user.id):
        raise HTTPException(status_code=403, detail="You can only assign users under your own reporting chain.")
    return parent


@router.get("/me", response_model=schemas.UserOut)
def read_current_user(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


@router.get("", response_model=List[schemas.UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Return the current user's reporting subtree."""
    if current_user.role == models.UserRole.superadmin:
        return db.query(models.User).all()

    if current_user.role == models.UserRole.user:
        raise HTTPException(status_code=403, detail="You don't have permission to view other users")
    all_users = db.query(models.User).all()
    by_parent = {}
    for user in all_users:
        by_parent.setdefault(user.parent_id, []).append(user)
    result = [current_user]
    frontier = [current_user.id]
    while frontier:
        children = [child for parent_id in frontier for child in by_parent.get(parent_id, [])]
        result.extend(children)
        frontier = [child.id for child in children]
    return result


@router.post("", response_model=schemas.UserOut)
def create_user(
    payload: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_can_manage_users),
):
    allowed = auth.CREATABLE_ROLES.get(current_user.role, set())
    if payload.role not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"A {current_user.role.value} cannot create a {payload.role.value}",
        )

    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    parent = _validate_parent(db, current_user, payload.role, payload.parent_id)
    user = models.User(
        name=payload.name,
        email=payload.email,
        hashed_password=auth.hash_password(payload.password),
        role=payload.role,
        parent_id=parent.id if parent else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}", response_model=schemas.UserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    if not auth.can_manage(db, current_user, user_id):
        raise HTTPException(status_code=404, detail="User not found")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: int,
    payload: schemas.UserUpdate,
    db: Session = Depends(get_db),
    acting_user: models.User = Depends(auth.require_can_manage_users),
):
    if not auth.can_manage(db, acting_user, user_id):
        raise HTTPException(status_code=404, detail="User not found")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    role_changing = payload.role is not None and payload.role != user.role
    new_role = payload.role if payload.role is not None else user.role

    if role_changing:
        if user_id == acting_user.id:
            raise HTTPException(status_code=403, detail="You cannot change your own role")
        allowed = auth.CREATABLE_ROLES.get(acting_user.role, set())
        if payload.role not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"A {acting_user.role.value} cannot assign the {payload.role.value} role",
            )

    required_parent_role = models.ROLE_HIERARCHY[new_role]
    requested_parent_id = payload.parent_id
    if required_parent_role is not None:
        if role_changing or requested_parent_id is not None:
            if requested_parent_id is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"parent_id is required when role is '{new_role.value}'.",
                )
            parent = _validate_parent(db, acting_user, new_role, requested_parent_id)
            user.parent_id = parent.id if parent else None
    else:
        user.parent_id = None

    if payload.role is not None:
        user.role = payload.role

    if payload.name is not None:
        user.name = payload.name

    if payload.is_active is not None:
        if user_id == acting_user.id:
            raise HTTPException(status_code=403, detail="You cannot deactivate your own account")
        user.is_active = payload.is_active

    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", response_model=schemas.UserOut)
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_can_manage_users),
):
    """Soft-delete only (is_active = False). A hard delete would break the
    existing FK from TimeEntry/Screenshot rows, and would silently orphan
    any users this person created — deactivating preserves history and
    keeps their subtree intact under its existing parent relationship."""
    if user_id == current_user.id:
        raise HTTPException(status_code=403, detail="You cannot deactivate your own account")
    if not auth.can_manage(db, current_user, user_id):
        raise HTTPException(status_code=404, detail="User not found")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = False
    db.commit()
    db.refresh(user)
    return user
