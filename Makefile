.PHONY: help install dev test deploy clean migrate seed lint format docker-up docker-down

help:
	@echo "Available commands:"
	@echo "  make install   - Install dependencies"
	@echo "  make dev       - Start development server"
	@echo "  make test      - Run all tests"
	@echo "  make lint      - Run code linters"
	@echo "  make format    - Format code"
	@echo "  make migrate   - Run database migrations"
	@echo "  make seed      - Seed database"
	@echo "  make docker-up - Start Docker services"
	@echo "  make clean     - Clean up temporary files"

install:
	@echo "📦 Installing dependencies..."
	python -m pip install --upgrade pip
	pip install -r requirements.txt
	@echo "✅ Dependencies installed"

dev: docker-up
	@echo "🚀 Starting development server..."
	uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

test:
	@echo "🧪 Running tests..."
	pytest tests/ -v --cov=api --cov-report=html --cov-report=term

test-unit:
	@echo "🧩 Running unit tests..."
	pytest tests/unit/ -v

test-integration:
	@echo "🔗 Running integration tests..."
	pytest tests/integration/ -v

lint:
	@echo "🔍 Linting code..."
	flake8 api/ --max-line-length=100 --exclude=__pycache__
	mypy api/ --ignore-missing-imports

format:
	@echo "✨ Formatting code..."
	black api/ tests/
	isort api/ tests/ --profile black

migrate:
	@echo "🔄 Running database migrations..."
	alembic upgrade head

migrate-create:
	@echo "📝 Creating new migration..."
	@read -p "Enter migration name: " name; \
	alembic revision --autogenerate -m "$$name"

seed:
	@echo "🌱 Seeding database..."
	python cli/manage.py db seed

docker-up:
	@echo "🐳 Starting Docker services..."
	docker-compose -f docker/docker-compose.yml up -d

docker-down:
	@echo "🛑 Stopping Docker services..."
	docker-compose -f docker/docker-compose.yml down

docker-logs:
	@echo "📋 Showing Docker logs..."
	docker-compose -f docker/docker-compose.yml logs -f

clean:
	@echo "🧹 Cleaning up..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov .mypy_cache

setup: install docker-up migrate seed
	@echo "✅ Project setup complete!"
	@echo "Run 'make dev' to start the development server"

deploy-staging:
	@echo "🚀 Deploying to staging..."
	./scripts/deploy.sh staging

deploy-production:
	@echo "🚀 Deploying to production..."
	@read -p "Are you sure you want to deploy to production? [y/N] " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		./scripts/deploy.sh production; \
	else \
		echo "Deployment cancelled"; \
	fi

shell:
	@echo "🐚 Opening Python shell..."
	ipython

db-shell:
	@echo "🗄️ Opening database shell..."
	docker exec -it prompt-marketplace-postgres psql -U postgres -d prompt_marketplace

# CLI Commands
cli-users:
	@echo "👥 Managing users..."
	python cli/manage.py user list

cli-prompts:
	@echo "📝 Managing prompts..."
	python cli/manage.py prompt list

cli-stats:
	@echo "📊 Showing statistics..."
	python cli/manage.py prompt stats

cli-health:
	@echo "🏥 Checking system health..."
	python cli/manage.py health

cli-monitor:
	@echo "📈 Starting performance monitor..."
	python cli/monitor.py dashboard

cli-report:
	@echo "📋 Generating performance report..."
	python cli/monitor.py report

cli-export:
	@echo "💾 Exporting data..."
	@mkdir -p exports
	python cli/export.py full-backup -o exports