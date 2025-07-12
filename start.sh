#!/bin/bash

echo "🚀 Starting AI Prompt Marketplace..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install minimal dependencies if needed
if ! python -c "import fastapi" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install fastapi uvicorn sqlalchemy psycopg2-binary pydantic pydantic-settings python-jose[cryptography] passlib[bcrypt] python-multipart alembic redis
fi

# Check Docker services
if ! docker ps | grep -q "prompt-marketplace-postgres"; then
    echo "Starting database..."
    docker-compose -f docker/docker-compose.yml up -d
fi

# Run the test server first to verify setup
echo ""
echo "Starting test server..."
echo "Visit http://localhost:8000 to verify setup"
echo "Press Ctrl+C to stop"
echo ""

python test_server.py