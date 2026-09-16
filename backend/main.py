import os
import re
import time
import logging
from datetime import date
from decimal import Decimal
from typing import List, Optional
from pathlib import Path
from dotenv import load_dotenv

from fastapi import FastAPI, Depends, HTTPException, status, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text, inspect, func, or_
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate

import sys
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from database import engine, Base, Product, Order, get_db, init_db
except ModuleNotFoundError:
    from backend.database import engine, Base, Product, Order, get_db, init_db

# Load .env from backend and root directories
load_dotenv(dotenv_path=BASE_DIR / ".env")
load_dotenv(dotenv_path=BASE_DIR.parent / ".env")

PROJECT_NAME = "Agentic AI - Product & Order Management"
VERSION = "1.0.0"
PORT = int(os.getenv("PORT", "8000"))
GEMINI_API_KEY = os.getenv("Gemini_Api_Key") or os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("main")

# Initialize database schema
init_db()

# --- PYDANTIC SCHEMAS ---

class ProductBase(BaseModel):
    product_name: str = Field(..., min_length=1, max_length=100)
    category: Optional[str] = Field(None, max_length=50)
    price: Decimal = Field(..., gt=0)
    stock_quantity: int = Field(..., ge=0)

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    product_name: Optional[str] = Field(None, min_length=1, max_length=100)
    category: Optional[str] = Field(None, max_length=50)
    price: Optional[Decimal] = Field(None, gt=0)
    stock_quantity: Optional[int] = Field(None, ge=0)

class ProductResponse(ProductBase):
    product_id: int
    model_config = ConfigDict(from_attributes=True)


class OrderBase(BaseModel):
    product_id: int
    customer_name: str = Field(..., min_length=1, max_length=100)
    quantity: int = Field(..., gt=0)
    order_date: Optional[date] = None
    total_amount: Optional[Decimal] = None

class OrderCreate(OrderBase):
    pass

class OrderUpdate(BaseModel):
    product_id: Optional[int] = None
    customer_name: Optional[str] = Field(None, min_length=1, max_length=100)
    quantity: Optional[int] = Field(None, gt=0)
    order_date: Optional[date] = None
    total_amount: Optional[Decimal] = None

class OrderDetailResponse(BaseModel):
    order_id: int
    product_id: Optional[int]
    customer_name: str
    quantity: int
    order_date: Optional[date]
    total_amount: Decimal
    product: Optional[ProductResponse] = None
    model_config = ConfigDict(from_attributes=True)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)

class ChatResponse(BaseModel):
    response: str
    status: str = "success"


class DashboardStats(BaseModel):
    total_products: int
    total_stock_value: float
    total_orders: int
    total_revenue: float
    categories_count: int
    low_stock_count: int


# --- LANGCHAIN + GEMINI AI AGENT ---

CANDIDATE_MODELS = [
    os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
    "gemini-3.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.7-flash",
    "gemini-3.8-flash"
]

FORBIDDEN_KEYWORDS = [
    r"\bDROP\b", r"\bDELETE\b", r"\bUPDATE\b", r"\bINSERT\b", r"\bALTER\b",
    r"\bTRUNCATE\b", r"\bCREATE\b", r"\bREPLACE\b", r"\bGRANT\b", r"\bREVOKE\b",
    r"\bEXEC\b", r"\bEXECUTE\b", r"\bPROCEDURE\b"
]

def extract_text(content) -> str:
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and "text" in part:
                parts.append(part["text"])
        return "\n".join(parts)
    return str(content)

def invoke_llm_with_fallback(prompt_text: str) -> str:
    """Invoke Google Gemini LLM with automatic model failover if 503 capacity limit occurs."""
    last_error = None
    seen = set()
    models_to_try = [m for m in CANDIDATE_MODELS if m and not (m in seen or seen.add(m))]
    
    for model_name in models_to_try:
        try:
            logger.info(f"Invoking Gemini LLM with model: {model_name}")
            temp_llm = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=GEMINI_API_KEY,
                temperature=0.2,
                max_retries=1,
            )
            response = temp_llm.invoke(prompt_text)
            content_str = extract_text(response.content).strip()
            if content_str:
                return content_str
        except Exception as e:
            logger.warning(f"Model '{model_name}' failed with error: {e}. Trying next candidate...")
            last_error = e
    
    raise RuntimeError(f"All Gemini model candidates failed. Last error: {last_error}")

def is_safe_sql(sql_query: str) -> bool:
    clean_sql = sql_query.strip().strip(";").upper()
    if not (clean_sql.startswith("SELECT") or clean_sql.startswith("WITH")):
        return False
    if ";" in clean_sql:
        return False
    for pattern in FORBIDDEN_KEYWORDS:
        if re.search(pattern, clean_sql):
            return False
    return True

def get_db_schema_summary() -> str:
    inspector = inspect(engine)
    schema_info = []
    for table_name in ["product", "order"]:
        if inspector.has_table(table_name):
            columns = inspector.get_columns(table_name)
            col_desc = ", ".join([f"{c['name']} ({c['type']})" for c in columns])
            schema_info.append(f"Table `{table_name}`: columns [{col_desc}]")
    schema_info.append("Note: Table `order` is a SQL reserved word, so always enclose it in backticks like `order`.")
    schema_info.append("Relationship: `order`.product_id references `product`.product_id.")
    return "\n".join(schema_info)

SQL_PROMPT = PromptTemplate(
    input_variables=["schema", "user_question"],
    template="""You are a senior database AI agent for an e-commerce platform.
Generate a single MySQL read-only SELECT query to answer the user's question based on the live database schema below.

DATABASE SCHEMA:
{schema}

RULES:
1. Return ONLY the raw SQL query inside a code block ```sql ... ``` or plain text. No commentary.
2. Only write read-only SELECT queries. Never write DROP, DELETE, UPDATE, INSERT, ALTER, TRUNCATE.
3. Use backticks for table `order` e.g. FROM `order`.
4. Use aggregation functions (COUNT, SUM, AVG, MAX, MIN), JOINs, ORDER BY, and LIMIT where relevant.
5. Use LIKE / case-insensitive search for names or categories if appropriate.

USER QUESTION: {user_question}

SQL QUERY:"""
)

ANSWER_PROMPT = PromptTemplate(
    input_variables=["user_question", "sql_query", "query_results"],
    template="""You are a helpful e-commerce AI assistant for Product and Order management.
User question: "{user_question}"
SQL query executed: `{sql_query}`
Database records retrieved:
{query_results}

INSTRUCTIONS:
1. Provide a polite, clear, well-formatted response using Markdown.
2. Use markdown tables, bold values, or bullet lists for readability.
3. If no records are found, clearly state that no matching data was found.
4. Format currency figures neatly in ₹ (INR) e.g. ₹1,200.00.
5. Do not hallucinate or assume facts beyond the returned query results.

RESPONSE:"""
)

GREETING_MESSAGE = "Hello! Welcome to the Product & Order Management System. How can I help you today?"

def ask_ai_agent(user_question: str) -> str:
    question_lower = user_question.lower().strip()
    greetings = ["hi", "hello", "hey", "who are you", "what can you do", "help", "hi there", "good morning", "good evening", "good afternoon", "welcome"]
    if question_lower in greetings or (len(question_lower) < 4 and question_lower not in ["products", "orders"]):
        return GREETING_MESSAGE

    try:
        schema = get_db_schema_summary()
        raw_sql = invoke_llm_with_fallback(SQL_PROMPT.format(schema=schema, user_question=user_question))

        sql_match = re.search(r"```(?:sql)?\s*(.*?)\s*```", raw_sql, re.DOTALL | re.IGNORECASE)
        sql_query = sql_match.group(1).strip() if sql_match else raw_sql.strip()
        logger.info(f"Generated SQL: {sql_query}")

        if not is_safe_sql(sql_query):
            return "⚠️ Security Alert: Only read-only SELECT queries are allowed."

        with engine.connect() as conn:
            result = conn.execute(text(sql_query))
            rows = result.mappings().all()
            formatted_rows = []
            for row in rows[:50]:
                row_dict = {k: (str(v) if v is not None else None) for k, v in row.items()}
                formatted_rows.append(row_dict)

        final_answer = invoke_llm_with_fallback(
            ANSWER_PROMPT.format(
                user_question=user_question,
                sql_query=sql_query,
                query_results=str(formatted_rows) if formatted_rows else "No matching records found."
            )
        )
        return final_answer

    except Exception as e:
        logger.error(f"AI Agent error: {e}", exc_info=True)
        return f"I encountered an error querying the database: {str(e)}. Please try rephrasing your question."



# --- FASTAPI APP INITIALIZATION ---

app = FastAPI(
    title=PROJECT_NAME,
    version=VERSION,
    description="Full-stack AI Agentic Product & Order Management System with LangChain and Google Gemini.",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{time.time() - start_time:.4f}s"
    return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error occurred.", "error": str(exc)},
    )


# --- REST API ENDPOINTS ---

@app.get("/api/health", tags=["System"])
def health_check():
    return {
        "status": "online",
        "project": PROJECT_NAME,
        "version": VERSION,
        "model": GEMINI_MODEL,
        "docs": "/docs"
    }

# STATS
@app.get("/api/stats", response_model=DashboardStats, tags=["Stats"])
def get_stats(db: Session = Depends(get_db)):
    total_products = db.query(func.count(Product.product_id)).scalar() or 0
    total_stock_value = db.query(func.sum(Product.price * Product.stock_quantity)).scalar() or 0.0
    categories_count = db.query(func.count(func.distinct(Product.category))).scalar() or 0
    low_stock_count = db.query(func.count(Product.product_id)).filter(Product.stock_quantity <= 20).scalar() or 0

    total_orders = db.query(func.count(Order.order_id)).scalar() or 0
    total_revenue = db.query(func.sum(Order.total_amount)).scalar() or 0.0

    return DashboardStats(
        total_products=total_products,
        total_stock_value=float(total_stock_value),
        total_orders=total_orders,
        total_revenue=float(total_revenue),
        categories_count=categories_count,
        low_stock_count=low_stock_count
    )

# PRODUCTS
@app.get("/api/products", response_model=List[ProductResponse], tags=["Products"])
def get_products(
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db)
):
    query = db.query(Product)
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(Product.product_name.ilike(pattern), Product.category.ilike(pattern)))
    if category:
        query = query.filter(Product.category == category)
    return query.order_by(Product.product_id.asc()).offset(skip).limit(limit).all()

@app.get("/api/products/categories", response_model=List[str], tags=["Products"])
def get_categories(db: Session = Depends(get_db)):
    results = db.query(Product.category).filter(Product.category.isnot(None)).distinct().all()
    return sorted([r[0] for r in results if r[0]])

@app.get("/api/products/{product_id}", response_model=ProductResponse, tags=["Products"])
def get_product(product_id: int, db: Session = Depends(get_db)):
    prod = db.query(Product).filter(Product.product_id == product_id).first()
    if not prod:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return prod

@app.post("/api/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED, tags=["Products"])
def create_product(product_in: ProductCreate, db: Session = Depends(get_db)):
    db_product = Product(**product_in.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

@app.put("/api/products/{product_id}", response_model=ProductResponse, tags=["Products"])
def update_product(product_id: int, product_in: ProductUpdate, db: Session = Depends(get_db)):
    prod = db.query(Product).filter(Product.product_id == product_id).first()
    if not prod:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    for field, val in product_in.model_dump(exclude_unset=True).items():
        setattr(prod, field, val)
    db.commit()
    db.refresh(prod)
    return prod

@app.delete("/api/products/{product_id}", tags=["Products"])
def delete_product(product_id: int, db: Session = Depends(get_db)):
    prod = db.query(Product).filter(Product.product_id == product_id).first()
    if not prod:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    db.delete(prod)
    db.commit()
    return {"message": f"Product {product_id} deleted successfully", "product_id": product_id}

# ORDERS
@app.get("/api/orders", response_model=List[OrderDetailResponse], tags=["Orders"])
def get_orders(
    search: Optional[str] = Query(None),
    product_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db)
):
    query = db.query(Order).options(joinedload(Order.product))
    if search:
        query = query.filter(Order.customer_name.ilike(f"%{search}%"))
    if product_id:
        query = query.filter(Order.product_id == product_id)
    if start_date:
        query = query.filter(Order.order_date >= start_date)
    if end_date:
        query = query.filter(Order.order_date <= end_date)
    return query.order_by(Order.order_id.desc()).offset(skip).limit(limit).all()

@app.get("/api/orders/{order_id}", response_model=OrderDetailResponse, tags=["Orders"])
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).options(joinedload(Order.product)).filter(Order.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order

@app.post("/api/orders", response_model=OrderDetailResponse, status_code=status.HTTP_201_CREATED, tags=["Orders"])
def create_order(order_in: OrderCreate, db: Session = Depends(get_db)):
    prod = db.query(Product).filter(Product.product_id == order_in.product_id).first()
    if not prod:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Referenced product does not exist")

    order_dict = order_in.model_dump()
    if not order_dict.get("total_amount"):
        order_dict["total_amount"] = Decimal(str(prod.price)) * Decimal(str(order_dict["quantity"]))
    if not order_dict.get("order_date"):
        order_dict["order_date"] = date.today()

    db_order = Order(**order_dict)
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db.query(Order).options(joinedload(Order.product)).filter(Order.order_id == db_order.order_id).first()

@app.put("/api/orders/{order_id}", response_model=OrderDetailResponse, tags=["Orders"])
def update_order(order_id: int, order_in: OrderUpdate, db: Session = Depends(get_db)):
    db_order = db.query(Order).filter(Order.order_id == order_id).first()
    if not db_order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    update_data = order_in.model_dump(exclude_unset=True)
    if "product_id" in update_data and update_data["product_id"] != db_order.product_id:
        prod = db.query(Product).filter(Product.product_id == update_data["product_id"]).first()
        if not prod:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Referenced product does not exist")

    for field, value in update_data.items():
        setattr(db_order, field, value)

    db.commit()
    db.refresh(db_order)
    return db.query(Order).options(joinedload(Order.product)).filter(Order.order_id == db_order.order_id).first()

@app.delete("/api/orders/{order_id}", tags=["Orders"])
def delete_order(order_id: int, db: Session = Depends(get_db)):
    db_order = db.query(Order).filter(Order.order_id == order_id).first()
    if not db_order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    db.delete(db_order)
    db.commit()
    return {"message": f"Order {order_id} deleted successfully", "order_id": order_id}

# CHAT ENDPOINT
@app.post("/api/chat", response_model=ChatResponse, tags=["AI Chatbot"])
def chat(chat_in: ChatRequest):
    if not chat_in.message or not chat_in.message.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message cannot be empty")
    reply = ask_ai_agent(chat_in.message.strip())
    return ChatResponse(response=reply, status="success")

# SERVE FRONTEND SINGLE FILE
@app.get("/", include_in_schema=False)
def serve_frontend():
    possible_paths = [
        BASE_DIR / "index.html",
        BASE_DIR.parent / "fronend" / "index.html",
        BASE_DIR.parent / "frontend" / "index.html",
        BASE_DIR.parent / "index.html",
    ]
    for index_file in possible_paths:
        if index_file.exists():
            return FileResponse(index_file)
    return {"message": "Agentic AI API is running. Access /docs for API documentation."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
