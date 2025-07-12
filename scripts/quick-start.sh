#!/bin/bash

# Quick start script for local development

echo "🚀 AI Prompt Marketplace - Quick Start"
echo "======================================"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Install core dependencies only
echo "📥 Installing core dependencies..."
pip install fastapi uvicorn[standard] sqlalchemy psycopg2-binary pydantic pydantic-settings python-jose[cryptography] passlib[bcrypt] python-multipart

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "⚙️  Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please update .env with your API keys!"
fi

# Check Docker services
echo "🐳 Checking Docker services..."
if ! docker ps | grep -q "prompt-marketplace-postgres"; then
    echo "Starting PostgreSQL..."
    docker-compose -f docker/docker-compose.yml up -d postgres
fi

if ! docker ps | grep -q "prompt-marketplace-redis"; then
    echo "Starting Redis..."
    docker-compose -f docker/docker-compose.yml up -d redis
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "To start the development server:"
echo "  source venv/bin/activate"
echo "  uvicorn api.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "API will be available at: http://localhost:8000"
echo "API docs: http://localhost:8000/docs"