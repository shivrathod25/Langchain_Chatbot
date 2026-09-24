import os
from pathlib import Path
from datetime import date
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Numeric, Date, ForeignKey, text, inspect
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# Load environment variables from backend and root directories
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")
load_dotenv(dotenv_path=BASE_DIR.parent / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/agentic_ai")

# Fix Render PostgreSQL URL dialect compatibility (postgres:// -> postgresql://)
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def create_db_engine(url: str):
    engine_kwargs = {"pool_pre_ping": True, "echo": False}
    if url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        engine_kwargs["pool_recycle"] = 3600
    return create_engine(url, **engine_kwargs)

engine = create_db_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- DATABASE MODELS ---

class Product(Base):
    __tablename__ = "Product"

    product_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    product_name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=True)
    price = Column(Numeric(10, 2), nullable=False)
    stock_quantity = Column(Integer, nullable=False, default=0)

    orders = relationship("Order", back_populates="product", cascade="all, delete-orphan")


class Order(Base):
    __tablename__ = "Order"

    order_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("Product.product_id"), nullable=True)
    customer_name = Column(String(100), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    order_date = Column(Date, nullable=True)
    total_amount = Column(Numeric(10, 2), nullable=True)

    product = relationship("Product", back_populates="orders")


def init_db():
    """Create tables if they do not exist, falling back to SQLite if primary DB is unavailable."""
    global engine, SessionLocal
    try:
        # Test connection to configured engine
        with engine.connect() as conn:
            pass
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"Primary database connection failed ({e}). Falling back to SQLite local database.")
        sqlite_db_path = BASE_DIR.parent / "agentic_ai.db"
        DATABASE_URL = f"sqlite:///{sqlite_db_path}"
        engine = create_db_engine(DATABASE_URL)
        SessionLocal.configure(bind=engine)
        Base.metadata.create_all(bind=engine)

    # Schema Migration: Ensure total_amount column exists on Order table
    try:
        with engine.connect() as conn:
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            for tname in tables:
                if tname.lower() == "order":
                    cols = [c["name"] for c in inspector.get_columns(tname)]
                    if "total_amount" not in cols:
                        if str(engine.url).startswith("sqlite"):
                            conn.execute(text(f'ALTER TABLE "{tname}" ADD COLUMN total_amount NUMERIC(10, 2);'))
                        else:
                            conn.execute(text(f'ALTER TABLE "{tname}" ADD COLUMN IF NOT EXISTS total_amount NUMERIC(10, 2);'))
                        conn.commit()
    except Exception as alter_err:
        print(f"Schema migration note: {alter_err}")

    # Populate any missing total_amount values in Order table
    try:
        with engine.connect() as conn:
            conn.execute(text('UPDATE "Order" SET total_amount = (SELECT price FROM "Product" WHERE "Product".product_id = "Order".product_id) * quantity WHERE total_amount IS NULL AND product_id IS NOT NULL;'))
            conn.commit()
    except Exception as pop_err:
        print(f"Total amount update note: {pop_err}")

    # Seed sample data if database is empty
    db = SessionLocal()
    try:
        if db.query(Product).count() == 0:
            print("Seeding initial database records...")
            sample_products = [
                Product(product_name="Wireless Noise-Canceling Headphones", category="Electronics", price=199.99, stock_quantity=45),
                Product(product_name="Mechanical Gaming Keyboard", category="Electronics", price=129.50, stock_quantity=30),
                Product(product_name="Ergonomic Mesh Office Chair", category="Furniture", price=249.00, stock_quantity=12),
                Product(product_name="Stainless Steel Smart Water Bottle", category="Accessories", price=39.99, stock_quantity=80),
                Product(product_name="Ultra-Wide 4K Gaming Monitor", category="Electronics", price=499.99, stock_quantity=8),
                Product(product_name="Organic Cotton Hoodie", category="Apparel", price=59.95, stock_quantity=50),
            ]
            db.add_all(sample_products)
            db.commit()

            sample_orders = [
                Order(product_id=1, customer_name="Alice Smith", quantity=1, order_date=date(2026, 9, 15), total_amount=199.99),
                Order(product_id=2, customer_name="Bob Jones", quantity=2, order_date=date(2026, 9, 18), total_amount=259.00),
                Order(product_id=3, customer_name="Carol White", quantity=1, order_date=date(2026, 9, 20), total_amount=249.00),
                Order(product_id=4, customer_name="David Brown", quantity=3, order_date=date(2026, 9, 21), total_amount=119.97),
            ]
            db.add_all(sample_orders)
            db.commit()
            print("Seed completed successfully.")
    except Exception as seed_err:
        db.rollback()
        print(f"Database seeding note: {seed_err}")
    finally:
        db.close()


def get_db():
    """Dependency that yields a database session and ensures clean closure."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

