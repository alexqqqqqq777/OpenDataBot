from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, 
    Enum, JSON, DECIMAL, Date, Index, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
import enum


class Base(DeclarativeBase):
    pass


class CompanyRole(enum.Enum):
    PLAINTIFF = "plaintiff"
    DEFENDANT = "defendant"
    THIRD_PARTY = "third_party"


class ThreatLevel(enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class MonitoredCompany(Base):
    """Companies being monitored for court cases"""
    __tablename__ = "monitored_companies"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    edrpou: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    company_name: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    added_by_user_id: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OpenDataBotSubscription(Base):
    """OpenDataBot subscriptions for court monitoring"""
    __tablename__ = "opendatabot_subscriptions"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    edrpou: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    subscription_type: Mapped[str] = mapped_column(String(50), nullable=False)
    subscription_key: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class WorksectionCase(Base):
    """Cases extracted from Worksection tasks (for deduplication)"""
    __tablename__ = "worksection_cases"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    normalized_case_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    raw_name: Mapped[Optional[str]] = mapped_column(Text)
    task_id: Mapped[str] = mapped_column(String(20), nullable=False)
    project_id: Mapped[Optional[str]] = mapped_column(String(20))
    project_name: Mapped[Optional[str]] = mapped_column(String(255))
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('normalized_case_number', 'task_id', name='uq_case_task'),
    )


class CaseStatus(enum.Enum):
    NEW = "new"                    # Just discovered
    NOTIFIED = "notified"         # Notification sent
    IN_WORKSECTION = "in_worksection"  # Added to Worksection
    MONITORING = "monitoring"      # Actively monitoring
    CLOSED = "closed"             # Case closed


class CourtCase(Base):
    """Court cases from OpenDataBot - local storage"""
    __tablename__ = "court_cases"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True)
    normalized_case_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    court_code: Mapped[Optional[str]] = mapped_column(String(20))
    court_name: Mapped[Optional[str]] = mapped_column(String(255))
    case_type: Mapped[Optional[int]] = mapped_column(Integer)
    case_type_name: Mapped[Optional[str]] = mapped_column(String(100))
    company_role: Mapped[Optional[str]] = mapped_column(String(20))
    plaintiff: Mapped[Optional[str]] = mapped_column(Text)
    defendant: Mapped[Optional[str]] = mapped_column(Text)
    subject: Mapped[Optional[str]] = mapped_column(Text)
    claim_amount: Mapped[Optional[float]] = mapped_column(DECIMAL(15, 2))
    date_opened: Mapped[Optional[datetime]] = mapped_column(Date)
    stage: Mapped[Optional[str]] = mapped_column(String(100))
    judge: Mapped[Optional[str]] = mapped_column(String(255))
    source_link: Mapped[Optional[str]] = mapped_column(String(500))
    edrpou_matches: Mapped[Optional[str]] = mapped_column(JSON)
    raw_data: Mapped[Optional[str]] = mapped_column(JSON)
    
    # Status tracking
    status: Mapped[str] = mapped_column(String(20), default="new")
    threat_level: Mapped[Optional[str]] = mapped_column(String(20))
    is_in_worksection: Mapped[bool] = mapped_column(Boolean, default=False)
    worksection_task_id: Mapped[Optional[str]] = mapped_column(String(20))
    
    # Timestamps
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('ix_case_number_court', 'normalized_case_number', 'court_code'),
    )


class NotificationSent(Base):
    """Sent notifications (for deduplication)"""
    __tablename__ = "notifications_sent"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    case_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    normalized_case_number: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    threat_level: Mapped[Optional[str]] = mapped_column(String(20))
    telegram_message_id: Mapped[Optional[str]] = mapped_column(String(50))
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(50))
    payload_hash: Mapped[Optional[str]] = mapped_column(String(64))
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SyncState(Base):
    """Sync state for incremental updates"""
    __tablename__ = "sync_state"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    key_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    value: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserSubscription(Base):
    """User subscriptions to companies (multi-tenant)"""
    __tablename__ = "user_subscriptions"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    edrpou: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'edrpou', name='uq_user_edrpou'),
    )


class UserSettings(Base):
    """User settings for notification preferences"""
    __tablename__ = "user_settings"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    # False = filter by Worksection (default), True = receive ALL notifications
    receive_all_notifications: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CaseSubscription(Base):
    """User subscriptions to specific court cases (by case number)"""
    __tablename__ = "case_subscriptions"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    case_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    case_name: Mapped[Optional[str]] = mapped_column(String(255))  # Optional description
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'case_number', name='uq_user_case'),
    )
