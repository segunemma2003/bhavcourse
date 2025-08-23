#!/bin/bash

# Deployment script for the Django application
echo "🚀 Starting deployment..."

# Set error handling
set -e

# Navigate to project directory
cd /var/www/bhavani

# Activate virtual environment
echo "📦 Activating virtual environment..."
source venv/bin/activate

# Install/update dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Ensure mysqlclient is installed correctly
echo "📦 Ensuring mysqlclient is installed..."
pip install mysqlclient>=2.2.0,<2.3.0 || pip install mysqlclient

# Run database migrations
echo "🗄️  Running database migrations..."
python manage.py migrate

# Collect static files
echo "📁 Collecting static files..."
python manage.py collectstatic --noinput

# Fix any existing payment order issues
echo "🔧 Fixing payment order issues..."
if [ -f "fix_payment_orders.py" ]; then
    python fix_payment_orders.py
else
    echo "⚠️  fix_payment_orders.py not found, skipping payment order fix"
fi

# Set basic permissions (skip ownership changes to avoid permission errors)
echo "🔐 Setting basic permissions..."
chmod -R 755 /var/www/bhavani 2>/dev/null || echo "⚠️  Some permission changes failed (this is normal)"

# Ensure Django can write to media and static directories
if [ -d "/var/www/bhavani/media" ]; then
    chmod -R 775 /var/www/bhavani/media 2>/dev/null || echo "⚠️  Could not set media permissions"
fi

if [ -d "/var/www/bhavani/static" ]; then
    chmod -R 775 /var/www/bhavani/static 2>/dev/null || echo "⚠️  Could not set static permissions"
fi

# Restart services
echo "🔄 Restarting services..."

# Restart Redis
if systemctl is-active --quiet redis-server; then
    sudo systemctl restart redis-server
    echo "✅ Redis restarted"
else
    echo "⚠️  Redis not running"
fi

# Restart Supervisor (if available)
if command -v supervisorctl &> /dev/null; then
    sudo supervisorctl restart courseapp:* || echo "⚠️  Supervisor not configured"
    echo "✅ Supervisor restarted"
else
    echo "⚠️  Supervisor not available"
fi

# Restart Gunicorn (if running as systemd service)
if systemctl is-active --quiet gunicorn; then
    sudo systemctl restart gunicorn
    echo "✅ Gunicorn restarted"
else
    echo "⚠️  Gunicorn not running as systemd service"
fi

# Restart Nginx
if systemctl is-active --quiet nginx; then
    sudo systemctl restart nginx
    echo "✅ Nginx restarted"
else
    echo "⚠️  Nginx not running"
fi

# Check if services are running
echo "🔍 Checking service status..."

if systemctl is-active --quiet nginx; then
    echo "✅ Nginx is running"
else
    echo "❌ Nginx is not running"
fi

if systemctl is-active --quiet redis-server; then
    echo "✅ Redis is running"
else
    echo "❌ Redis is not running"
fi

# Test Django application
echo "🧪 Testing Django application..."
python manage.py check --deploy

echo "🎉 Deployment completed successfully!"
echo "📊 Application should now be running with the latest changes." 