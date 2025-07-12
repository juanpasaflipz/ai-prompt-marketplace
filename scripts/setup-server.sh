#!/bin/bash

# Server setup script for AI Prompt Marketplace
# Run this on a fresh Ubuntu 22.04 server

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Update system
print_info "Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Install dependencies
print_info "Installing system dependencies..."
sudo apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    postgresql \
    postgresql-contrib \
    redis-server \
    nginx \
    certbot \
    python3-certbot-nginx \
    git \
    curl \
    supervisor \
    ufw

# Setup firewall
print_info "Configuring firewall..."
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

# Setup PostgreSQL
print_info "Setting up PostgreSQL..."
sudo -u postgres psql << EOF
CREATE DATABASE prompt_marketplace;
CREATE USER marketplace_user WITH ENCRYPTED PASSWORD 'CHANGE_THIS_PASSWORD';
GRANT ALL PRIVILEGES ON DATABASE prompt_marketplace TO marketplace_user;
EOF

# Configure PostgreSQL for better performance
sudo tee -a /etc/postgresql/14/main/postgresql.conf << EOF

# Performance Tuning
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
effective_io_concurrency = 200
work_mem = 4MB
min_wal_size = 1GB
max_wal_size = 4GB
EOF

sudo systemctl restart postgresql

# Setup Redis
print_info "Configuring Redis..."
sudo tee -a /etc/redis/redis.conf << EOF

# Enable persistence
appendonly yes
appendfsync everysec

# Set memory policy
maxmemory 256mb
maxmemory-policy allkeys-lru
EOF

sudo systemctl restart redis-server
sudo systemctl enable redis-server

# Create application user
print_info "Creating application user..."
sudo useradd -m -s /bin/bash deploy
sudo usermod -aG www-data deploy

# Create application directories
print_info "Creating application directories..."
sudo mkdir -p /var/www/ai-prompt-marketplace
sudo mkdir -p /var/log/ai-prompt-marketplace
sudo chown -R deploy:www-data /var/www/ai-prompt-marketplace
sudo chown -R deploy:www-data /var/log/ai-prompt-marketplace
sudo chmod -R 755 /var/www/ai-prompt-marketplace

# Setup Python environment
print_info "Setting up Python environment..."
cd /var/www/ai-prompt-marketplace
sudo -u deploy python3.11 -m venv venv

# Create supervisor configuration
print_info "Setting up Supervisor..."
sudo tee /etc/supervisor/conf.d/ai-prompt-marketplace.conf << EOF
[program:ai-prompt-marketplace]
command=/var/www/ai-prompt-marketplace/venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000 --workers 4
directory=/var/www/ai-prompt-marketplace
user=deploy
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/ai-prompt-marketplace/api.log
environment=PATH="/var/www/ai-prompt-marketplace/venv/bin",HOME="/home/deploy",USER="deploy"
EOF

sudo supervisorctl reread
sudo supervisorctl update

# Setup Nginx
print_info "Setting up Nginx..."
sudo rm -f /etc/nginx/sites-enabled/default
sudo cp scripts/nginx.conf /etc/nginx/sites-available/ai-prompt-marketplace
sudo ln -s /etc/nginx/sites-available/ai-prompt-marketplace /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Setup SSL with Let's Encrypt
print_info "Setting up SSL..."
print_warning "Make sure your domain is pointing to this server before continuing!"
read -p "Enter your domain (e.g., api.promptmarketplace.com): " DOMAIN
read -p "Enter your email for SSL notifications: " EMAIL

sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email $EMAIL

# Setup log rotation
print_info "Setting up log rotation..."
sudo tee /etc/logrotate.d/ai-prompt-marketplace << EOF
/var/log/ai-prompt-marketplace/*.log {
    daily
    missingok
    rotate 14
    compress
    notifempty
    create 0640 deploy www-data
    sharedscripts
    postrotate
        supervisorctl restart ai-prompt-marketplace
    endscript
}
EOF

# Create systemd service for analytics worker
print_info "Setting up analytics worker..."
sudo tee /etc/systemd/system/ai-prompt-analytics.service << EOF
[Unit]
Description=AI Prompt Marketplace Analytics Worker
After=network.target

[Service]
Type=simple
User=deploy
WorkingDirectory=/var/www/ai-prompt-marketplace
Environment="PATH=/var/www/ai-prompt-marketplace/venv/bin"
ExecStart=/var/www/ai-prompt-marketplace/venv/bin/python -m api.workers.analytics
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ai-prompt-analytics

# Setup monitoring
print_info "Setting up monitoring..."
sudo apt-get install -y prometheus-node-exporter
sudo systemctl enable prometheus-node-exporter
sudo systemctl start prometheus-node-exporter

# Create deployment script
print_info "Creating deployment helper..."
sudo tee /usr/local/bin/deploy-marketplace << 'EOF'
#!/bin/bash
cd /var/www/ai-prompt-marketplace
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
sudo supervisorctl restart ai-prompt-marketplace
sudo systemctl restart ai-prompt-analytics
echo "Deployment completed!"
EOF

sudo chmod +x /usr/local/bin/deploy-marketplace

print_info "Server setup completed!"
print_info "Next steps:"
print_info "1. Update /var/www/ai-prompt-marketplace/.env with your configuration"
print_info "2. Deploy your application code to /var/www/ai-prompt-marketplace"
print_info "3. Run database migrations: cd /var/www/ai-prompt-marketplace && venv/bin/alembic upgrade head"
print_info "4. Start the application: sudo supervisorctl start ai-prompt-marketplace"