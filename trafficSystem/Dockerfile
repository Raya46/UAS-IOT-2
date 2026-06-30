# Stage 1: Build the React frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Build the FastAPI backend and bundle everything
FROM python:3.11-slim AS backend-runner
WORKDIR /app

# Install curl for health checks and API triggering
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    libglib2.0-0 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend application
COPY backend/ ./backend/

# Copy simulator application
COPY simulator/ ./simulator/
# Install simulator dependency in main python environment
RUN pip install --no-cache-dir redis==5.0.4

# Copy compiled frontend from stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Set working directory to backend for executing uvicorn
WORKDIR /app/backend

# Expose port 8000
EXPOSE 8000

# Default command to run backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
