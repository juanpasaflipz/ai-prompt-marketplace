# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a B2B AI Prompt Marketplace built with FastAPI, designed for enterprise users to buy and sell optimized AI prompts. The project emphasizes rapid development, data-driven analytics, and scalable architecture.

## Quick Start

If you're having issues with dependencies, use the quick start script:

```bash
# Quick start with minimal setup
./start.sh

# Or use the full setup
./scripts/setup.sh
```

## Key Development Commands

```bash
# Initial setup (run once)
./scripts/setup.sh

# Start development server (auto-starts Docker services)
make dev

# Alternative: Run with virtual environment
source venv/bin/activate
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Database operations
make migrate              # Apply database migrations
make migrate-create       # Create new migration (prompts for name)
make seed                # Seed development data
make db-shell            # Access PostgreSQL shell

# Testing
make test                # Run all tests with coverage
make test-unit           # Run unit tests only
make test-integration    # Run integration tests only
pytest tests/unit/test_auth.py::test_login -v  # Run single test

# Code quality
make lint                # Run flake8 and mypy
make format              # Auto-format with black and isort

# Docker services
make docker-up           # Start PostgreSQL and Redis
make docker-down         # Stop services
make docker-logs         # View Docker logs

# Deployment
make deploy-staging      # Deploy to staging
make deploy-production   # Deploy to production (with confirmation)

# Utilities
make shell               # Open IPython shell
make clean               # Remove __pycache__, .pyc, test artifacts
```

## Architecture Overview

### Core Stack
- **FastAPI** - Async Python web framework
- **PostgreSQL** - Primary database with JSONB support
- **Redis** - Caching and session management
- **SQLAlchemy** - ORM with Alembic for migrations
- **Pydantic** - Data validation and settings management

### External Integrations
- **Stripe** - Payment processing (customer creation, payment intents, subscriptions)
- **OpenAI** - GPT-4o integration for prompt validation/testing
- **Sentry** - Error tracking (optional)

### Authentication Flow
- JWT-based with access tokens (30min) and refresh tokens (7 days)
- Tokens contain user ID, email, and role
- Role-based access control: buyer, seller, admin
- Middleware at `api/middleware/auth.py` handles token validation

### Database Design
- **Users** - Company-based accounts with Stripe customer IDs
- **Prompts** - Template-based with variables, pricing, and performance metrics
- **Transactions** - Full payment history with Stripe integration
- **Analytics Events** - Comprehensive tracking with JSONB metadata

Key design decisions:
- JSONB fields for flexible metadata storage
- Database triggers for updated_at timestamps
- Automatic prompt statistics updates on transaction completion

### Analytics System
- Event-driven architecture with batched writes
- Tracks: views, clicks, purchases, searches, category browsing
- Analytics middleware automatically tracks API usage
- Background task flushes events every 60 seconds or 100 events

### API Structure
All APIs follow RESTful conventions under `/api/v1/`:
- `/auth/*` - Authentication endpoints
- `/prompts/*` - Prompt CRUD operations
- `/marketplace/*` - Browse, search, purchase
- `/analytics/*` - Dashboard and metrics

### Configuration Management
Settings loaded from environment via Pydantic:
- `.env` file for local development
- Required: DATABASE_URL, JWT_SECRET_KEY, STRIPE_SECRET_KEY, OPENAI_API_KEY
- Settings cached with @lru_cache for performance

### Development Workflow
1. Docker services must be running (PostgreSQL, Redis)
2. Alembic manages all database schema changes
3. Analytics events are tracked automatically via middleware
4. All models include to_dict() methods for serialization
5. Stripe customers created automatically on user registration

### Testing Strategy
- Unit tests mock external services (Stripe, OpenAI)
- Integration tests use test database
- Fixtures in tests/conftest.py
- Coverage target: 80%

### Security Considerations
- All passwords hashed with bcrypt
- SQL injection prevention via SQLAlchemy
- Rate limiting configured per endpoint
- CORS configured for allowed origins only
- Stripe webhook signature verification required

### Error Handling
- Custom HTTPException for API errors
- Structured logging with context
- Analytics tracking continues even if errors occur
- Database rollback on transaction failures

### Performance Optimizations
- Database connection pooling (10 connections, 20 overflow)
- Redis caching for frequently accessed data
- Batch analytics writes
- Indexed database columns for common queries
- PostgreSQL trigram indexes for text search

## CLI Management Tools

The project includes comprehensive CLI tools for management:

### Database Management
```bash
python cli/manage.py db init          # Initialize database
python cli/manage.py db reset         # Reset database (WARNING: deletes all data)
python cli/manage.py db seed          # Seed with sample data
```

### User Management
```bash
python cli/manage.py user list        # List all users
python cli/manage.py user create      # Create new user interactively
```

### Monitoring
```bash
python cli/monitor.py dashboard       # Live performance dashboard
python cli/monitor.py report          # Generate performance report
python cli/monitor.py alerts          # Check for performance alerts
```

### Data Export
```bash
python cli/export.py users --format json -o users.json
python cli/export.py prompts --format csv -o prompts.csv
python cli/export.py full-backup -o backups/
```

## Deployment

### Local Development
```bash
make dev                              # Starts Docker services and development server
```

### Production Deployment
```bash
./scripts/deploy.sh production        # Deploy to production
./scripts/deploy.sh staging           # Deploy to staging
./scripts/deploy.sh production rollback  # Rollback production
```

### Docker Production
```bash
docker-compose -f docker-compose.prod.yml up -d
```

### Server Setup
For new server setup (Ubuntu 22.04):
```bash
./scripts/setup-server.sh             # Run on fresh server
```

### Health Monitoring
```bash
./scripts/health-check.sh             # Run health checks
```

### CI/CD
GitHub Actions workflow automatically:
- Runs tests on all PRs
- Builds Docker images on push to main/develop
- Deploys to staging on push to develop
- Deploys to production on push to main (with approval)