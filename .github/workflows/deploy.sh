#!/bin/bash
set -e

# Navigate to project directory
cd /var/www/bhavani

# Activate virtual environment
source /var/www/bhavani/venv/bin/activate

# Install MySQL client development libraries (only needed once)
sudo apt-get update
sudo apt-get install -y python3-dev default-libmysqlclient-dev build-essential

# Install Redis if needed for Celery
sudo apt-get install -y redis-server
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Install/update dependencies
pip install -r requirements.txt
pip install razorpay
pip install mysqlclient  # Explicitly install mysqlclient

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cp .env.example .env
    echo "Please update .env with real values!"
fi

# Create static and media directories if they don't exist
mkdir -p static
mkdir -p media

# Make sure the static and media directories are writable
chmod -R 755 static
chmod -R 755 media

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Fix permissions
find . -type d -exec chmod 755 {} \;
find . -type f -exec chmod 644 {} \;
chmod +x manage.py
chmod +x deploy.sh

# Start/restart services if needed
sudo systemctl restart redis-server  # Restart Redis for Celery

# Restart Supervisor services if configured
if command -v supervisorctl &> /dev/null; then
    echo "Restarting services with supervisor..."
    sudo supervisorctl restart courseapp:* || echo "Supervisor not configured yet"
else
    echo "Supervisor not installed, skipping service restart"
fi

echo "Deployment completed successfully!"