#!/bin/bash

# AI Prompt Marketplace Deployment Script

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
ENVIRONMENTS=("staging" "production")
STAGING_HOST="staging.promptmarketplace.com"
PRODUCTION_HOST="api.promptmarketplace.com"
DEPLOY_USER="deploy"
APP_DIR="/var/www/ai-prompt-marketplace"

# Functions
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

check_environment() {
    local env=$1
    if [[ ! " ${ENVIRONMENTS[@]} " =~ " ${env} " ]]; then
        print_error "Invalid environment: $env"
        print_info "Valid environments: ${ENVIRONMENTS[*]}"
        exit 1
    fi
}

get_host() {
    local env=$1
    if [ "$env" == "staging" ]; then
        echo $STAGING_HOST
    else
        echo $PRODUCTION_HOST
    fi
}

pre_deploy_checks() {
    print_info "Running pre-deployment checks..."
    
    # Check if tests pass
    print_info "Running tests..."
    make test-unit || {
        print_error "Unit tests failed! Aborting deployment."
        exit 1
    }
    
    # Check if linting passes
    print_info "Running linters..."
    make lint || {
        print_error "Linting failed! Fix issues before deploying."
        exit 1
    }
    
    # Check git status
    if [ -n "$(git status --porcelain)" ]; then
        print_warning "You have uncommitted changes!"
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Deployment cancelled."
            exit 1
        fi
    fi
    
    print_info "Pre-deployment checks passed!"
}

build_application() {
    print_info "Building application..."
    
    # Create deployment package
    local build_dir="build_$(date +%Y%m%d_%H%M%S)"
    mkdir -p $build_dir
    
    # Copy application files
    rsync -av --exclude-from='.gitignore' \
        --exclude='.git' \
        --exclude='build_*' \
        --exclude='exports' \
        --exclude='htmlcov' \
        --exclude='.env' \
        . $build_dir/
    
    # Create requirements file for production
    grep -v "pytest\|flake8\|black\|mypy\|ipython" requirements.txt > $build_dir/requirements.prod.txt
    
    # Create deployment archive
    tar -czf deploy.tar.gz -C $build_dir .
    rm -rf $build_dir
    
    print_info "Build completed: deploy.tar.gz"
}

deploy_to_server() {
    local env=$1
    local host=$(get_host $env)
    
    print_info "Deploying to $env ($host)..."
    
    # Upload deployment package
    print_info "Uploading deployment package..."
    scp deploy.tar.gz $DEPLOY_USER@$host:/tmp/
    
    # Execute deployment on remote server
    ssh $DEPLOY_USER@$host << 'ENDSSH'
        set -e
        
        # Backup current deployment
        if [ -d "$APP_DIR" ]; then
            echo "Creating backup of current deployment..."
            sudo cp -r $APP_DIR $APP_DIR.backup.$(date +%Y%m%d_%H%M%S)
        fi
        
        # Extract new deployment
        echo "Extracting new deployment..."
        sudo mkdir -p $APP_DIR.new
        sudo tar -xzf /tmp/deploy.tar.gz -C $APP_DIR.new
        sudo rm /tmp/deploy.tar.gz
        
        # Install/update dependencies
        echo "Installing dependencies..."
        cd $APP_DIR.new
        sudo python3 -m venv venv
        sudo ./venv/bin/pip install --upgrade pip
        sudo ./venv/bin/pip install -r requirements.prod.txt
        
        # Run database migrations
        echo "Running database migrations..."
        sudo ./venv/bin/alembic upgrade head
        
        # Swap deployments
        echo "Swapping deployments..."
        if [ -d "$APP_DIR" ]; then
            sudo mv $APP_DIR $APP_DIR.old
        fi
        sudo mv $APP_DIR.new $APP_DIR
        
        # Update systemd service
        echo "Restarting application..."
        sudo systemctl restart ai-prompt-marketplace
        sudo systemctl status ai-prompt-marketplace
        
        # Clean up old deployment
        if [ -d "$APP_DIR.old" ]; then
            sudo rm -rf $APP_DIR.old
        fi
        
        echo "Deployment completed successfully!"
ENDSSH
    
    # Clean up local build
    rm deploy.tar.gz
    
    print_info "Deployment to $env completed!"
}

post_deploy_checks() {
    local env=$1
    local host=$(get_host $env)
    
    print_info "Running post-deployment checks..."
    
    # Check if API is responding
    print_info "Checking API health..."
    response=$(curl -s -o /dev/null -w "%{http_code}" https://$host/health)
    
    if [ "$response" == "200" ]; then
        print_info "API is healthy!"
    else
        print_error "API health check failed! Response code: $response"
        exit 1
    fi
    
    # Check database connectivity
    ssh $DEPLOY_USER@$host << 'ENDSSH'
        cd $APP_DIR
        ./venv/bin/python -c "
from api.database import engine
from sqlalchemy import text
try:
    with engine.connect() as conn:
        conn.execute(text('SELECT 1'))
    print('Database connection: OK')
except Exception as e:
    print(f'Database connection: FAILED - {e}')
    exit(1)
"
ENDSSH
    
    print_info "Post-deployment checks passed!"
}

rollback() {
    local env=$1
    local host=$(get_host $env)
    
    print_warning "Rolling back deployment on $env..."
    
    ssh $DEPLOY_USER@$host << 'ENDSSH'
        set -e
        
        # Find most recent backup
        BACKUP=$(ls -t $APP_DIR.backup.* 2>/dev/null | head -1)
        
        if [ -z "$BACKUP" ]; then
            echo "No backup found to rollback to!"
            exit 1
        fi
        
        echo "Rolling back to: $BACKUP"
        
        # Swap deployments
        sudo mv $APP_DIR $APP_DIR.failed
        sudo mv $BACKUP $APP_DIR
        
        # Restart service
        sudo systemctl restart ai-prompt-marketplace
        
        # Clean up failed deployment
        sudo rm -rf $APP_DIR.failed
        
        echo "Rollback completed!"
ENDSSH
    
    print_info "Rollback completed!"
}

# Main script
main() {
    local environment=$1
    local action=${2:-deploy}
    
    if [ -z "$environment" ]; then
        print_error "Usage: $0 <environment> [action]"
        print_info "Environments: ${ENVIRONMENTS[*]}"
        print_info "Actions: deploy (default), rollback"
        exit 1
    fi
    
    check_environment $environment
    
    case $action in
        deploy)
            print_info "Starting deployment to $environment..."
            pre_deploy_checks
            build_application
            deploy_to_server $environment
            post_deploy_checks $environment
            print_info "🎉 Deployment to $environment completed successfully!"
            ;;
        rollback)
            rollback $environment
            ;;
        *)
            print_error "Invalid action: $action"
            print_info "Valid actions: deploy, rollback"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"