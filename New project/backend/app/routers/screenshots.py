import os
import uuid
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db

load_dotenv()

STORAGE_DIR = os.getenv("SCREENSHOT_STORAGE_DIR", "./storage/screenshots")

router = APIRouter(prefix="/screenshots", tags=["screenshots"])


@router.post("", response_model=schemas.ScreenshotOut)
def upload_screenshot(
    time_entry_id: int = Form(...),
    ip_address: str = Form(...),
    activity_level: Optional[float] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    entry = (
        db.query(models.TimeEntry)
        .filter(models.TimeEntry.id == time_entry_id, models.TimeEntry.user_id == current_user.id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Time entry not found")

    user_dir = os.path.join(STORAGE_DIR, str(current_user.id))
    os.makedirs(user_dir, exist_ok=True)

    ext = os.path.splitext(file.filename or "screenshot.jpg")[1] or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    dest_path = os.path.join(user_dir, filename)

    with open(dest_path, "wb") as out:
        out.write(file.file.read())

    screenshot = models.Screenshot(
        time_entry_id=time_entry_id,
        user_id=current_user.id,
        file_path=dest_path,
        ip_address=ip_address,
        activity_level=activity_level,
    )
    db.add(screenshot)
    db.commit()
    db.refresh(screenshot)
    return screenshot


@router.get("", response_model=List[schemas.ScreenshotOut])
def list_screenshots(
    user_id: Optional[int] = None,
    time_entry_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    query = db.query(models.Screenshot)

    if current_user.role == models.UserRole.admin:
        if user_id is not None:
            query = query.filter(models.Screenshot.user_id == user_id)
    else:
        query = query.filter(models.Screenshot.user_id == current_user.id)

    if time_entry_id is not None:
        query = query.filter(models.Screenshot.time_entry_id == time_entry_id)

    return query.order_by(models.Screenshot.captured_at.desc()).all()
