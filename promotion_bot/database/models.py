import datetime
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Boolean, DateTime, Float, ForeignKey
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class SenderAccount(Base):
    __tablename__ = "sender_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone = Column(String(50), unique=True, nullable=False, index=True)
    session_string = Column(Text, nullable=False)
    user_id = Column(BigInteger, nullable=True)
    username = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    is_premium = Column(Boolean, default=False)
    is_active = Column(Boolean, default=False)  # Currently selected account for broadcasting
    status = Column(String(50), default="ACTIVE")  # ACTIVE, NEED_LOGIN, MUTED, BANNED
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class Group(Base):
    __tablename__ = "target_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(BigInteger, nullable=True, index=True)
    title = Column(String(255), nullable=True)
    identifier = Column(String(255), unique=True, nullable=False, index=True)  # @username, invite link, or chat_id
    is_joined = Column(Boolean, default=False)
    
    # Status: 'ACTIVE', 'SLOWMODE', 'MUTED', 'BANNED', 'INVALID_LINK', 'RESTRICTED'
    status = Column(String(50), default="ACTIVE", index=True)
    
    last_sent_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    failure_count = Column(Integer, default=0)
    consecutive_failures = Column(Integer, default=0)
    slowmode_seconds = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    logs = relationship("BroadcastLog", back_populates="group", cascade="all, delete-orphan")


class PromoMessage(Base):
    __tablename__ = "promo_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(100), default="Primary Promotion")
    text = Column(Text, nullable=False)
    media_type = Column(String(20), default="none")  # 'none', 'photo', 'video', 'document'
    media_file_id = Column(String(255), nullable=True)
    media_path = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class BroadcastCycle(Base):
    __tablename__ = "broadcast_cycles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Status: 'RUNNING', 'COMPLETED', 'PAUSED', 'STOPPED', 'FAILED'
    status = Column(String(50), default="RUNNING")
    
    total_targets = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    duration_seconds = Column(Integer, default=0)

    logs = relationship("BroadcastLog", back_populates="cycle", cascade="all, delete-orphan")


class BroadcastLog(Base):
    __tablename__ = "broadcast_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cycle_id = Column(Integer, ForeignKey("broadcast_cycles.id", ondelete="CASCADE"), nullable=True)
    group_id = Column(Integer, ForeignKey("target_groups.id", ondelete="CASCADE"), nullable=True)
    group_identifier = Column(String(255), nullable=False)
    
    # Status: 'SENT', 'FAILED', 'SLOWMODE', 'SKIPPED'
    status = Column(String(50), nullable=False)
    error_reason = Column(Text, nullable=True)
    sent_at = Column(DateTime, default=datetime.datetime.utcnow)

    group = relationship("Group", back_populates="group_logs", cascade="none") if hasattr(Group, "group_logs") else relationship("Group", back_populates="logs")
    cycle = relationship("BroadcastCycle", back_populates="logs")


class BotSetting(Base):
    __tablename__ = "bot_settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    description = Column(String(255), nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
