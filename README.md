# Agentic AI - Product & Order Management System with Gemini AI Chatbot

A consolidated, high-performance full-stack AI e-commerce management system powered by **FastAPI**, **LangChain**, **Google Gemini AI**, **SQLAlchemy**, **MySQL / PostgreSQL**, and a self-contained modern **Single-File Frontend (`index.html`)**.

---

## 📁 Project Architecture & File Structure

```text
Chatbot_Langchain/
├── backend/
│   ├── database.py       # DB engine, sessionmaker, and SQLAlchemy Models (Product, Order)
│   └── main.py           # FastAPI App, Pydantic schemas, REST APIs, & LangChain AI Agent
├── fronend/
│   └── index.html        # Self-contained modern Frontend UI (HTML + CSS + JS)
├── .dockerignore         # Docker exclusion rules
├── .gitignore            # Git exclusion rules
├── Dockerfile            # Container definition for Docker & Render deployments
├── render.yaml           # Render Blueprint configuration file
├── requirements.txt      # Production Python dependencies
├── .env                  # Local environment variables
└── README.md             # Project documentation & deployment instructions
```

---

## 🚀 Key Features

- **Single-File Frontend (`index.html`)**:
  - Full HTML, CSS, and JavaScript in a single, responsive dashboard.
  - Zero node_modules or build tool dependencies.
  - **Dashboard**: Real-time KPI summary cards (Total Products, Stock Value, Orders, Low Stock Alerts).
  - **Products Admin**: Real-time filter search, category selector, status badges, modal dialogs for CRUD.
  - **Orders Admin**: Order list, customer search, product selector with dynamic price auto-calculation.
  - **AI Assistant Chatbot**: Integrated LangChain + Gemini conversational database interface with Markdown table rendering and quick prompt suggestions.
- **FastAPI Backend (`main.py`)**:
  - Complete REST APIs for Products, Orders, Stats, and AI Chatbot.
  - Read-only SQL query validator protecting the database against unauthorized mutations.
  - Auto-serves `index.html` at `GET /` and API documentation at `/docs`.
- **Database Layer (`database.py`)**:
  - SQLAlchemy ORM with automatic connection pooling and multi-database support (PostgreSQL, MySQL, SQLite).

---

## ⚡ Local Development Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables (`.env`)
```env
DATABASE_URL="mysql+pymysql://root:@localhost:3306/agentic_ai"
Gemini_Api_Key="your_gemini_api_key_here"
GEMINI_MODEL="gemini-3.6-flash"
PORT=8000
```

### 3. Run the Application
```bash
uvicorn backend.main:app --reload --port 8000
```
Open **`http://localhost:8000/`** in your browser.

---

## 🌐 How to Push to GitHub & Deploy on Render

### Step 1: Push Code to GitHub

1. Initialize Git repository locally:
   ```bash
   git init
   git add .
   git commit -m "Initial commit: Ready for Render deployment"
   ```
2. Create a new repository on [GitHub](https://github.com/new).
3. Link and push your local repository:
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.name.git
   git branch -M main
   git push -u origin main
   ```

---

### Step 2: Deploy on Render

You can deploy using **Option A (Render Web Service - Native Python)** or **Option B (Docker Container)**.

#### Option A: Native Python Deployment (Recommended & Fastest)

1. Log in to [Render Dashboard](https://dashboard.render.com).
2. Click **New +** -> **Web Service**.
3. Connect your GitHub repository.
4. Fill in the deployment details:
   - **Name**: `chatbot-langchain` (or preferred name)
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install --upgrade pip && pip install -r requirements.txt`
   - **Start Command**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
5. Add **Environment Variables** under the **Environment** tab:
   - `Gemini_Api_Key` : `Your_Actual_Gemini_API_Key`
   - `GEMINI_MODEL` : `gemini-3.6-flash`
   - `DATABASE_URL` : Your database URL (e.g. Render PostgreSQL or external MySQL instance).
6. Click **Create Web Service**.

---

#### Option B: Docker Deployment

1. Log in to [Render Dashboard](https://dashboard.render.com).
2. Click **New +** -> **Web Service**.
3. Select your GitHub repository.
4. Render will automatically detect the `Dockerfile`.
5. Under **Environment Variables**, add:
   - `Gemini_Api_Key` : `Your_Actual_Gemini_API_Key`
   - `GEMINI_MODEL` : `gemini-3.6-flash`
   - `DATABASE_URL` : Your database URL.
6. Click **Deploy**.

---

#### Option C: 1-Click Render Blueprint Deployment

1. Push code to GitHub.
2. In Render Dashboard, click **New +** -> **Blueprint**.
3. Select your GitHub repo. Render will automatically read `render.yaml`!
4. Provide values for `Gemini_Api_Key` and `DATABASE_URL` when prompted, then click **Apply**.
