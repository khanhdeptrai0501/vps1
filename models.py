"""Database models for GitHub Student Verification Bot."""

from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional
import uuid
import secrets
import string

from sqlalchemy import (
    BigInteger, String, Text, Integer, Boolean,
    DateTime, Enum, ForeignKey, JSON, Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


# ============== Enums ==============

class UserRole(PyEnum):
    """User roles."""
    USER = "USER"
    ADMIN = "ADMIN"


class OrderStatus(PyEnum):
    """Verification order statuses."""
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    PROCESSING = "PROCESSING"
    SUBMITTING = "SUBMITTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PaymentType(PyEnum):
    """Payment types."""
    CREDIT = "CREDIT"
    QR_PAYMENT = "QR_PAYMENT"


# ============== Models ==============

class User(Base):
    """Telegram user model with credits."""
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    
    # Credits system
    credits: Mapped[int] = mapped_column(Integer, default=0)
    
    # Referral system
    referral_code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    referred_by_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    referral_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Status
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    ban_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    joined_channel: Mapped[bool] = mapped_column(Boolean, default=False)
    joined_group: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Role
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.USER, nullable=False
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    
    def is_admin(self) -> bool:
        """Check if user is admin."""
        return self.role == UserRole.ADMIN
    
    def has_joined_all(self) -> bool:
        """Check if user has joined both channel and group."""
        return self.joined_channel and self.joined_group
    
    @staticmethod
    def generate_referral_code() -> str:
        """Generate unique referral code."""
        chars = string.ascii_uppercase + string.digits
        return ''.join(secrets.choice(chars) for _ in range(8))


class PromoCode(Base):
    """Promo code model."""
    __tablename__ = "promo_codes"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    credits_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    current_uses: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    
    def is_valid(self) -> bool:
        """Check if promo code is still valid."""
        if not self.is_active:
            return False
        if self.current_uses >= self.max_uses:
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True


class PromoCodeUsage(Base):
    """Track promo code usage."""
    __tablename__ = "promo_code_usages"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    promo_code_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("promo_codes.id"), nullable=False
    )
    used_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    
    __table_args__ = (
        Index("idx_user_promo", "user_id", "promo_code_id"),
    )


class VerificationOrder(Base):
    """GitHub Student verification order."""
    __tablename__ = "verification_orders"
    
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    
    # Payment
    payment_type: Mapped[PaymentType] = mapped_column(
        Enum(PaymentType), nullable=False
    )
    payment_ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    amount: Mapped[int] = mapped_column(Integer, default=0)  # VND
    
    # Status
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), default=OrderStatus.PENDING_PAYMENT, nullable=False
    )
    
    # GitHub data
    github_cookie: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    github_username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    student_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    card_base64: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    geo_lat: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    geo_lng: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    
    # Result
    submit_result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    __table_args__ = (
        Index("idx_user_status", "user_id", "status"),
        Index("idx_payment_ref", "payment_ref"),
    )


class BotSettings(Base):
    """Bot settings/state."""
    __tablename__ = "bot_settings"
    
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class PaymentLog(Base):
    """Payment webhook log for debugging."""
    __tablename__ = "payment_logs"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), default="SEPAY")
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    order_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
