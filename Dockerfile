# Use official lightweight Python image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Set working directory inside container
WORKDIR /app

# Install system dependencies (build-essential, libpq-dev for postgres if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install python packages
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy project files into container
COPY . .

# Expose port (Render dynamically sets PORT at runtime)
EXPOSE ${PORT}

# Run FastAPI app using uvicorn
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
