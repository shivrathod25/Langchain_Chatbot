import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Numeric, Date, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# Load environment variables
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://root:@localhost:3306/agentic_ai")

# Fix Render PostgreSQL URL dialect compatibility (postgres:// -> postgresql://)
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Configure SQLAlchemy engine based on database dialect
engine_kwargs = {
    "pool_pre_ping": True,
    "echo": False
}

if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_recycle"] = 3600

engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- DATABASE MODELS ---

class Product(Base):
    __tablename__ = "product"

    product_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    product_name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=True)
    price = Column(Numeric(10, 2), nullable=False)
    stock_quantity = Column(Integer, nullable=False, default=0)

    orders = relationship("Order", back_populates="product", cascade="all, delete-orphan")


class Order(Base):
    __tablename__ = "order"

    order_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("product.product_id"), nullable=True)
    customer_name = Column(String(100), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    order_date = Column(Date, nullable=True)
    total_amount = Column(Numeric(10, 2), nullable=False)

    product = relationship("Product", back_populates="orders")


def init_db():
    """Create tables if they do not exist."""
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"Database connection note: {e}")


def get_db():
    """Dependency that yields a database session and ensures clean closure."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
