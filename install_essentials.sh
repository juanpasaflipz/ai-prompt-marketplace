#!/bin/bash

# Activate virtual environment
source venv/bin/activate

# Install essentials one by one
echo "Installing FastAPI..."
pip install fastapi

echo "Installing Uvicorn..."
pip install "uvicorn[standard]"

echo "Installing Pydantic..."
pip install pydantic pydantic-settings

echo "Installing database dependencies..."
pip install sqlalchemy alembic psycopg2-binary

echo "Installing auth dependencies..."
pip install "python-jose[cryptography]" "passlib[bcrypt]" python-multipart

echo "Installing other dependencies..."
pip install redis httpx python-dotenv

echo "Done! You can now run: make dev"