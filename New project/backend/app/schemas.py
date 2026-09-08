from datetime import datetime, timezone
from typing import Optional
 
from pydantic import BaseModel, EmailStr, field_serializer
 
from .models import UserRole, TimeEntryStatus
 
 
def _as_utc_iso(dt: Optional[datetime]) -> Optional[str]:
    """SQLite drops timezone info on read, but every timestamp we write is
    computed in UTC. Stamp UTC back on before serializing so the frontend's
    `new Date(...)` knows to convert it to the browser's local time instead
    of treating the naive value as already-local."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
 
 
# ---- Auth ----
 
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
 
 
# ---- User ----
 
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: UserRole = UserRole.employee
 
 
class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: UserRole
    is_active: bool
 
    class Config:
        from_attributes = True
 
 
# ---- Project ----
 
class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
 
 
class ProjectOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
 
    class Config:
        from_attributes = True
 
 
# ---- Time entries ----
 
class TimeEntryStart(BaseModel):
    project_id: Optional[int] = None
    ip_address: str
 
 
class TimeEntryOut(BaseModel):
    id: int
    user_id: int
    project_id: Optional[int]
    start_time: datetime
    end_time: Optional[datetime]
    duration_seconds: int
    status: TimeEntryStatus
    start_ip_address: Optional[str] = None
    last_seen_at: Optional[datetime] = None   # NEW
    is_idle: bool = False                     # NEW
 
    class Config:
        from_attributes = True
 
    @field_serializer("start_time", "end_time")
    def serialize_dt(self, dt: Optional[datetime], _info):
        return _as_utc_iso(dt)
    
    # NEW — sent by the tracking client every N seconds while a session is active
class TimeEntryHeartbeat(BaseModel):
    is_idle: bool = False
 
 
# ---- Screenshots ----
 
class ScreenshotOut(BaseModel):
    id: int
    time_entry_id: int
    user_id: int
    file_path: str
    ip_address: str
    activity_level: Optional[float]
    captured_at: datetime
 
    class Config:
        from_attributes = True
 
    @field_serializer("captured_at")
    def serialize_dt(self, dt: datetime, _info):
        return _as_utc_iso(dt)