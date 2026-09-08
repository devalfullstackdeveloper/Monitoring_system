import enum

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Enum, Float, Boolean
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    employee = "employee"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.employee, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    time_entries = relationship("TimeEntry", back_populates="user")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    time_entries = relationship("TimeEntry", back_populates="project")


class TimeEntryStatus(str, enum.Enum):
    active = "active"
    stopped = "stopped"


class TimeEntry(Base):
    __tablename__ = "time_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)

    start_time = Column(DateTime(timezone=True), server_default=func.now())
    end_time = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, default=0)
    status = Column(Enum(TimeEntryStatus), default=TimeEntryStatus.active)

    start_ip_address = Column(String, nullable=True)
    
     # NEW — real idle tracking instead of guessing from screenshots
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    is_idle = Column(Boolean, default=False)

    user = relationship("User", back_populates="time_entries")
    project = relationship("Project", back_populates="time_entries")
    screenshots = relationship("Screenshot", back_populates="time_entry")


class Screenshot(Base):
    __tablename__ = "screenshots"

    id = Column(Integer, primary_key=True, index=True)
    time_entry_id = Column(Integer, ForeignKey("time_entries.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    file_path = Column(String, nullable=False)
    ip_address = Column(String, nullable=False)
    activity_level = Column(Float, nullable=True)  # optional: mouse/keyboard activity %
    captured_at = Column(DateTime(timezone=True), server_default=func.now())

    time_entry = relationship("TimeEntry", back_populates="screenshots")
    user = relationship("User")
