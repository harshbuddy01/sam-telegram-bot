import datetime
from sqlalchemy import (
    Column, Integer, BigInteger, String, Float, Boolean, DateTime, ForeignKey, Text, Index
)
from sqlalchemy.orm import relationship
from database.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)
    full_name = Column(String, nullable=False, default="")
    balance = Column(Float, default=0.0, nullable=False)
    total_spent = Column(Float, default=0.0, nullable=False)
    referrer_id = Column(BigInteger, nullable=True)
    joined_at = Column(DateTime, default=datetime.datetime.utcnow)
    is_banned = Column(Boolean, default=False)

    orders = relationship("Order", back_populates="user", cascade="all, delete-orphan")
    deposits = relationship("Deposit", back_populates="user", cascade="all, delete-orphan")

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    emoji = Column(String, default="📁")
    custom_emoji_id = Column(String, nullable=True)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    products = relationship("Product", back_populates="category", cascade="all, delete-orphan")

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, nullable=False)
    emoji = Column(String, default="📦")
    custom_emoji_id = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    image_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)

    category = relationship("Category", back_populates="products")
    variants = relationship("Variant", back_populates="product", cascade="all, delete-orphan", passive_deletes=True)

class Variant(Base):
    __tablename__ = "variants"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False) # e.g. "1 Month Private Profile"
    price = Column(Float, nullable=False)
    variant_type = Column(String, default="Private Profile") # "Private Profile", "Shared Profile", "Invite Link", "License Key"
    fulfillment_type = Column(String(20), default="AUTOMATIC") # "AUTOMATIC" (stock draw) or "MANUAL" (dispatch within 1-2h)
    manual_dispatch_time = Column(String(50), default="1–2 Hours") # Expected dispatch time for manual orders
    input_type = Column(String(50), default="ANY") # "PHONE_NUMBER", "EMAIL", "EMAIL_OR_PHONE", "USERNAME", "ANY"
    input_prompt = Column(Text, nullable=True) # Custom prompt e.g. "Please send your mobile number or email:"
    detailed_description = Column(Text, nullable=True) # Full description displayed before payment
    requires_customer_input = Column(Boolean, default=True) # If True, prompts customer for email/phone; if False, delivers immediate receipt and notifies admin to dispatch
    stock_quantity = Column(Integer, default=50) # Manual fulfillment slots available
    is_active = Column(Boolean, default=True)

    product = relationship("Product", back_populates="variants")
    stocks = relationship("Stock", back_populates="variant", cascade="all, delete-orphan", passive_deletes=True)
    orders = relationship("Order", back_populates="variant", passive_deletes=True)

class Stock(Base):
    __tablename__ = "stocks"
    __table_args__ = (
        Index("ix_stocks_variant_unused", "variant_id", "is_used"),
    )

    id = Column(Integer, primary_key=True, index=True)
    variant_id = Column(Integer, ForeignKey("variants.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(Text, nullable=False) # e.g. "email:password | PIN: 1234 | Profile: Screen 1"
    is_used = Column(Boolean, default=False, index=True)
    added_at = Column(DateTime, default=datetime.datetime.utcnow)
    sold_at = Column(DateTime, nullable=True)
    order_id = Column(Integer, nullable=True)

    variant = relationship("Variant", back_populates="stocks")

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    variant_id = Column(Integer, ForeignKey("variants.id", ondelete="SET NULL"), nullable=True, index=True)
    amount = Column(Float, nullable=False)
    quantity = Column(Integer, default=1, nullable=True)  # Number of units purchased
    status = Column(String(30), default="COMPLETED") # "COMPLETED", "PENDING_DISPATCH", "CANCELLED"
    customer_input = Column(Text, nullable=True) # Target email/phone/username provided by customer
    delivered_content = Column(Text, nullable=True, default="") # Delivered accounts, PINs, or activation links
    broadcast_sent = Column(Boolean, default=False, nullable=True) # Prevent duplicate broadcast notifications
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    fulfilled_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="orders")
    variant = relationship("Variant", back_populates="orders")

class Deposit(Base):
    __tablename__ = "deposits"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    utr_number = Column(String, nullable=True)
    proof_file_id = Column(String, nullable=True)
    gateway = Column(String(50), default="MANUAL_UPI") # "MANUAL_UPI", "CASHFREE", "RAZORPAY", "CRYPTO"
    gateway_order_id = Column(String(100), nullable=True)
    gateway_payment_id = Column(String(100), nullable=True)
    status = Column(String(30), default="PENDING") # "PENDING", "APPROVED", "REJECTED", "SUCCESS"
    target_variant_id = Column(Integer, nullable=True) # Set when direct 1-click checkout is used
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    approved_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="deposits")

class BotTemplate(Base):
    __tablename__ = "bot_templates"

    key = Column(String(50), primary_key=True, index=True) # e.g. "welcome_text", "category_products_header", "product_item_format", "variant_detail", "checkout_text", "delivery_text", "profile_text", "support_text"
    content = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
