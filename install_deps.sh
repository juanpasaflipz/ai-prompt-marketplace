#!/bin/bash

echo "Installing AI Prompt Marketplace dependencies..."

# Ensure we're in virtual environment
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "Please activate virtual environment first:"
    echo "source venv/bin/activate"
    exit 1
fi

# Upgrade pip first
pip install --upgrade pip

# Install core dependencies with compatible versions
echo "Installing core dependencies..."
pip install "fastapi==0.104.1"
pip install "uvicorn[standard]==0.24.0"
pip install "pydantic==2.5.0"
pip install "pydantic-settings==2.1.0"
pip install "sqlalchemy==2.0.23"
pip install "alembic==1.12.1"
pip install "psycopg2-binary==2.9.9" || pip install "psycopg"
pip install "python-jose[cryptography]==3.3.0"
pip install "passlib[bcrypt]==1.7.4"
pip install "python-multipart==0.0.6"
pip install "redis==5.0.1"
pip install "httpx==0.25.2"
pip install "python-dotenv==1.0.0"

# Optional dependencies (non-critical)
echo "Installing optional dependencies..."
pip install "stripe==7.0.0" || echo "Warning: Stripe not installed"
pip install "openai==1.3.0" || echo "Warning: OpenAI not installed"

echo "Installation complete!"
echo "You can now run: make dev"