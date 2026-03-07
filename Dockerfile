# ==========================================
# Stage 1: Build the React Frontend
# ==========================================
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

# Copy frontend package files and install dependencies
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

# Copy the rest of the frontend source code
COPY frontend/ .

# Build the production React SPA to /app/frontend/dist
RUN npm run build


# ==========================================
# Stage 2: Setup Python Backend & Serve
# ==========================================
FROM python:3.12-slim
WORKDIR /app/backend

# Install system dependencies if required by native python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy python dependencies and install them
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend source code
COPY backend/ .

# Copy the built React assets from Stage 1 into the backend's expected relative path
# (main.py looks for ../frontend/dist)
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Expose the single unified port
EXPOSE 8000

# Set environment variables for production
ENV PYTHONUNBUFFERED=1

# Start the FastAPI server using Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
