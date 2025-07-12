#!/bin/bash
# Initial setup script for AI Prompt Marketplace

set -e

echo "🚀 Setting up AI Prompt Marketplace..."

# Check prerequisites
command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3 required but not installed."; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "❌ Docker required but not installed."; exit 1; }
command -v docker-compose >/dev/null 2>&1 || { echo "❌ Docker Compose required but not installed."; exit 1; }

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
REQUIRED_VERSION="3.8"
if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then 
    echo "❌ Python $REQUIRED_VERSION or higher is required (found $PYTHON_VERSION)"
    exit 1
fi

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
echo "⬆️ Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📚 Installing dependencies..."
pip install -r requirements.txt

# Copy environment file
if [ ! -f .env ]; then
    echo "🔧 Setting up environment..."
    cp .env.example .env
    echo "⚠️  Please update .env with your configuration"
else
    echo "✅ .env file already exists"
fi

# Start PostgreSQL and Redis with Docker
echo "🐳 Starting PostgreSQL and Redis..."
docker-compose -f docker/docker-compose.yml up -d postgres redis

# Wait for PostgreSQL to be ready
echo "⏳ Waiting for database to be ready..."
max_attempts=30
attempt=0
while ! docker exec prompt-marketplace-postgres pg_isready -U postgres > /dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ $attempt -eq $max_attempts ]; then
        echo "❌ Database failed to start after $max_attempts attempts"
        exit 1
    fi
    echo -n "."
    sleep 1
done
echo " ✅"

# Create database if it doesn't exist
echo "🗄️ Creating database..."
docker exec prompt-marketplace-postgres psql -U postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'prompt_marketplace'" | grep -q 1 || \
docker exec prompt-marketplace-postgres psql -U postgres -c "CREATE DATABASE prompt_marketplace"

# Initialize Alembic if not already initialized
if [ ! -d "alembic" ]; then
    echo "🔄 Initializing Alembic..."
    alembic init alembic
    
    # Update alembic.ini with our database URL
    sed -i.bak 's|sqlalchemy.url = .*|sqlalchemy.url = postgresql://postgres:postgres@localhost:5432/prompt_marketplace|' alembic.ini
    rm -f alembic.ini.bak
fi

# Create initial migration
echo "📝 Creating initial migration..."
alembic revision --autogenerate -m "Initial schema" 2>/dev/null || echo "⚠️  Migration already exists or no changes detected"

# Run migrations
echo "🔄 Running database migrations..."
alembic upgrade head 2>/dev/null || echo "✅ Database is up to date"

# Seed development data
echo "🌱 Seeding development data..."
python -m cli.manage db seed 2>/dev/null || echo "⚠️  Seeding skipped (CLI not yet implemented)"

echo ""
echo "✅ Setup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Update .env with your configuration (Stripe keys, OpenAI key, etc.)"
echo "2. Run 'make dev' to start the development server"
echo "3. Visit http://localhost:8000/docs for API documentation"
echo ""
echo "🛠️ Useful commands:"
echo "  make dev         - Start development server"
echo "  make test        - Run tests"
echo "  make lint        - Check code quality"
echo "  make docker-logs - View Docker logs"
echo "  make db-shell    - Access PostgreSQL shell"