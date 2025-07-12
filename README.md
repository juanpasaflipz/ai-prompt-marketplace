# AI Prompt Marketplace

A B2B marketplace for buying and selling optimized AI prompts, built with FastAPI and focused on enterprise users.

## Features

- 🔐 Enterprise-grade authentication with JWT
- 💳 Stripe integration for secure payments
- 📊 Advanced analytics and tracking
- 🚀 High-performance API with FastAPI
- 🎯 GPT-4o optimized prompts
- 📈 Data-driven insights and ROI tracking

## Quick Start

### Prerequisites

- Python 3.8+
- Docker and Docker Compose
- PostgreSQL (via Docker)
- Redis (via Docker)

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd ai-prompt-marketplace
```

2. Run the setup script:
```bash
./scripts/setup.sh
```

3. Update `.env` with your configuration:
```bash
# Edit .env file with your Stripe and OpenAI keys
vim .env
```

4. Start the development server:
```bash
make dev
```

5. Visit http://localhost:8000/docs for API documentation

## Development

### Common Commands

```bash
make help          # Show all available commands
make dev           # Start development server
make test          # Run test suite
make lint          # Check code quality
make format        # Format code
make migrate       # Run database migrations
make seed          # Seed development data
make docker-up     # Start Docker services
make docker-down   # Stop Docker services
```

### Project Structure

```
ai-prompt-marketplace/
├── api/                 # FastAPI application
│   ├── models/         # SQLAlchemy models
│   ├── routes/         # API endpoints
│   ├── services/       # Business logic
│   └── middleware/     # Custom middleware
├── db/                 # Database related files
│   ├── migrations/     # Alembic migrations
│   └── seeds/          # Seed data
├── cli/                # CLI management tools
├── integrations/       # External service integrations
│   ├── stripe/         # Stripe payment processing
│   └── openai/         # OpenAI GPT-4o integration
├── tests/              # Test suite
└── scripts/            # Automation scripts
```

## API Documentation

Once the server is running, visit:
- http://localhost:8000/docs - Swagger UI documentation
- http://localhost:8000/redoc - ReDoc documentation

## Testing

Run the full test suite:
```bash
make test
```

Run specific test types:
```bash
make test-unit        # Unit tests only
make test-integration # Integration tests only
```

## Deployment

### Staging
```bash
make deploy-staging
```

### Production
```bash
make deploy-production
```

## Security

- JWT-based authentication with refresh tokens
- Rate limiting on all endpoints
- SQL injection protection via SQLAlchemy ORM
- CORS configuration for allowed origins
- Environment-based configuration
- Stripe webhook signature verification

## License

Proprietary - All rights reserved