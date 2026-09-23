from datetime import datetime, timezone
from typing import Optional 
from pydantic import BaseModel, EmailStr, Field, field_serializer
 
from .models import AlertSeverity, AlertStatus, UserRole, TimeEntryStatus
 
 
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
    organization_id: Optional[int] = None
    manager_id: Optional[int] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(default=None, min_length=12)
    role: Optional[UserRole] = None
    organization_id: Optional[int] = None
    manager_id: Optional[int] = None
    is_active: Optional[bool] = None
 
 
class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: UserRole
    organization_id: Optional[int] = None
    manager_id: Optional[int] = None
    is_active: bool
 
    class Config:
        from_attributes = True


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)


class OrganizationOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=20)
    password: str = Field(min_length=12)


class ConsentCreate(BaseModel):
    policy_version: str = Field(min_length=1, max_length=40)


class ConsentOut(BaseModel):
    id: int
    user_id: int
    organization_id: Optional[int]
    policy_version: str
    accepted_at: datetime

    class Config:
        from_attributes = True


class AlertCreate(BaseModel):
    alert_type: str = Field(min_length=1, max_length=80)
    severity: AlertSeverity = AlertSeverity.warning
    message: str = Field(min_length=1, max_length=500)
    evidence: Optional[dict] = None


class AlertOut(BaseModel):
    id: int
    user_id: int
    alert_type: str
    severity: AlertSeverity
    status: AlertStatus
    message: str
    evidence: Optional[dict]
    created_at: datetime
    acknowledged_at: Optional[datetime]

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


class SettingsOut(BaseModel):
    screenshot_interval_seconds: int
    idle_timeout_seconds: int
    retention_days: int
    screenshot_masking_enabled: bool

    class Config:
        from_attributes = True


class SettingsUpdate(BaseModel):
    screenshot_interval_seconds: int = Field(ge=30, le=3600)
    idle_timeout_seconds: int = Field(ge=30, le=3600)
    retention_days: int = Field(default=90, ge=1, le=3650)
    screenshot_masking_enabled: bool = False