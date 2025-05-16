#!/bin/bash
set -e

# Navigate to project directory
cd /var/www/bhavani

# Function to recreate virtual environment if needed
check_and_recreate_venv() {
    local venv_python="/var/www/bhavani/venv/bin/python"
    local venv_pip="/var/www/bhavani/venv/bin/pip"
    
    # Check if virtual environment exists and is healthy
    if [ ! -f "$venv_python" ] || [ ! -f "$venv_pip" ]; then
        echo "Virtual environment missing, recreating..."
        rm -rf venv
        python3 -m venv venv
        return 0
    fi
    
    # Activate and test virtual environment
    source venv/bin/activate
    
    # Test if pip works and can install/list packages
    if ! pip list > /dev/null 2>&1; then
        echo "Virtual environment corrupted (pip broken), recreating..."
        deactivate
        rm -rf venv
        python3 -m venv venv
        source venv/bin/activate
        return 0
    fi
    
    # Test if Python can import basic modules
    if ! python -c "import sys, os, json" > /dev/null 2>&1; then
        echo "Virtual environment corrupted (Python broken), recreating..."
        deactivate
        rm -rf venv
        python3 -m venv venv
        source venv/bin/activate
        return 0
    fi
    
    echo "Virtual environment is healthy"
    return 1
}

# Check and recreate virtual environment if needed
check_and_recreate_venv
recreated=$?

# Ensure we're in the virtual environment
source venv/bin/activate

# Verify virtual environment
echo "=== Virtual Environment Status ==="
echo "VIRTUAL_ENV: $VIRTUAL_ENV"
echo "Python: $(which python)"
echo "Pip: $(which pip)"

# Install system dependencies
echo "=== Installing system dependencies ==="
sudo apt-get update
sudo apt-get install -y python3-dev default-libmysqlclient-dev build-essential

# Install Redis
sudo apt-get install -y redis-server
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Upgrade pip first
echo "=== Upgrading pip ==="
pip install --upgrade pip

# Install Python dependencies
echo "=== Installing Python dependencies ==="
if [ $recreated -eq 0 ]; then
    # If we recreated venv, install everything fresh
    pip install -r requirements.txt
    pip install razorpay mysqlclient
else
    # If venv was healthy, use force-reinstall for critical packages
    pip install --upgrade -r requirements.txt
    pip install --upgrade razorpay mysqlclient
fi

# Verify critical imports
echo "=== Verifying critical packages ==="
python -c "import boto3; print('✓ boto3 OK')" || (echo "boto3 missing, installing..." && pip install --force-reinstall boto3)
python -c "import MySQLdb; print('✓ MySQLdb OK')" || (echo "MySQLdb missing, installing..." && pip install --force-reinstall mysqlclient)

# Create .env file if needed
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cp .env.example .env
    echo "Please update .env with real values!"
fi

# Create and setup directories
mkdir -p static media logs
chmod -R 755 static media
chmod -R 755 logs 2>/dev/null || true

# Update manage.py shebang to use virtual environment python
if [ -f manage.py ]; then
    # Create backup
    cp manage.py manage.py.backup
    # Update shebang
    sed -i '1s|.*|#!/var/www/bhavani/venv/bin/python|' manage.py
    chmod +x manage.py
fi

# Test Django and handle warnings
echo "=== Testing Django ==="
python manage.py check --fail-level=ERROR || (echo "Django has critical errors!" && exit 1)

# Handle migration conflicts
echo "=== Checking for migration conflicts ==="
migration_output=$(python manage.py showmigrations --plan 2>&1)
if echo "$migration_output" | grep -q "conflicting migrations" || echo "$migration_output" | grep -q "multiple leaf nodes"; then
    echo "Conflicting migrations detected, merging..."
    python manage.py makemigrations --merge --noinput
fi

# Run migrations
echo "=== Running migrations ==="
python manage.py migrate

# Collect static files
echo "=== Collecting static files ==="
python manage.py collectstatic --noinput

# Fix permissions
find . -type d -exec chmod 755 {} \;
find . -type f -exec chmod 644 {} \;
chmod +x manage.py deploy.sh

# Create a deployment log
echo "$(date): Deployment completed successfully" >> logs/deployment.log

# Restart services
sudo systemctl restart redis-server

if command -v supervisorctl &> /dev/null; then
    echo "Restarting services with supervisor..."
    sudo supervisorctl restart courseapp:* || echo "Supervisor not configured yet"
fi

echo "=== Deployment completed successfully! ==="
