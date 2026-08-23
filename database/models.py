import datetime
from sqlalchemy import (
    Column, Integer, BigInteger, String, Float, Boolean, DateTime, ForeignKey, Text
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
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    emoji = Column(String, default="📦")
    custom_emoji_id = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    image_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)

    category = relationship("Category", back_populates="products")
    variants = relationship("Variant", back_populates="product", cascade="all, delete-orphan")

class Variant(Base):
    __tablename__ = "variants"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False) # e.g. "1 Month Private Profile"
    price = Column(Float, nullable=False)
    variant_type = Column(String, default="Private") # "Private", "Shared", "Key", "Warranty"
    detailed_description = Column(Text, nullable=True) # Full description displayed before payment
    is_active = Column(Boolean, default=True)

    product = relationship("Product", back_populates="variants")
    stocks = relationship("Stock", back_populates="variant", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="variant")

class Stock(Base):
    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True, index=True)
    variant_id = Column(Integer, ForeignKey("variants.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False) # e.g. "email:password", "license_key", etc.
    is_used = Column(Boolean, default=False, index=True)
    added_at = Column(DateTime, default=datetime.datetime.utcnow)
    sold_at = Column(DateTime, nullable=True)
    order_id = Column(Integer, nullable=True)

    variant = relationship("Variant", back_populates="stocks")

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    variant_id = Column(Integer, ForeignKey("variants.id"), nullable=False)
    amount = Column(Float, nullable=False)
    delivered_content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="orders")
    variant = relationship("Variant", back_populates="orders")

class Deposit(Base):
    __tablename__ = "deposits"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    amount = Column(Float, nullable=False)
    utr_number = Column(String, nullable=True)
    proof_file_id = Column(String, nullable=True)
    status = Column(String, default="PENDING") # "PENDING", "APPROVED", "REJECTED"
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    approved_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="deposits")
