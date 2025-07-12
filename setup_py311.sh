#!/bin/bash

echo "Setting up AI Prompt Marketplace with Python 3.11..."

# Remove old virtual environment
if [ -d "venv" ]; then
    echo "Removing old virtual environment..."
    rm -rf venv
fi

# Create new virtual environment with Python 3.11
echo "Creating virtual environment with Python 3.11..."
python3.11 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
pip install fastapi==0.104.1
pip install "uvicorn[standard]==0.24.0"
pip install pydantic==2.5.0
pip install pydantic-settings==2.1.0
pip install sqlalchemy==2.0.23
pip install alembic==1.12.1
pip install psycopg2-binary==2.9.9
pip install "python-jose[cryptography]==3.3.0"
pip install "passlib[bcrypt]==1.7.4"
pip install python-multipart==0.0.6
pip install redis==5.0.1
pip install httpx==0.25.2
pip install python-dotenv==1.0.0

# Optional dependencies
pip install stripe==7.0.0 || echo "Warning: Stripe not installed"
pip install openai==1.3.0 || echo "Warning: OpenAI not installed"

echo ""
echo "✅ Setup complete!"
echo ""
echo "To activate the virtual environment, run:"
echo "  source venv/bin/activate"
echo ""
echo "Then you can run:"
echo "  make dev"
echo ""
echo "Or directly:"
echo "  uvicorn api.main:app --reload --host 0.0.0.0 --port 8000"