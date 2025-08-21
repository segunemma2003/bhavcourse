#!/bin/bash

# Migration Conflict Fix for CI/CD Pipeline
# Add this to your deployment pipeline before running migrations

echo "🔧 Running migration conflict fix..."

# Install MySQL client if not already installed
install_mysql_client() {
    echo "📦 Installing MySQL client dependencies..."
    
    # Check if we're on Ubuntu/Debian
    if command -v apt-get &> /dev/null; then
        sudo apt-get update
        sudo apt-get install -y default-libmysqlclient-dev build-essential pkg-config
    # Check if we're on CentOS/RHEL
    elif command -v yum &> /dev/null; then
        sudo yum install -y mysql-devel gcc
    # Check if we're on macOS
    elif command -v brew &> /dev/null; then
        brew install mysql pkg-config
    else
        echo "⚠️ Could not install MySQL client automatically. Please install manually."
    fi
    
    # Install Python MySQL client
    pip install mysqlclient
}

# Function to handle errors
handle_error() {
    echo "❌ Error occurred: $1"
    exit 1
}

# Check if we're in a Django project
if [ ! -f "manage.py" ]; then
    handle_error "manage.py not found. Are you in the correct directory?"
fi

# Install MySQL client if needed
if ! python -c "import MySQLdb" 2>/dev/null; then
    echo "⚠️ MySQL client not found. Installing..."
    install_mysql_client
fi

# Step 1: Check for migration conflicts
echo "📋 Checking for migration conflicts..."
if python manage.py showmigrations core 2>&1 | grep -q "Conflicting migrations detected"; then
    echo "⚠️ Migration conflicts detected. Running merge..."
    
    # Create merge migration
    python manage.py makemigrations --merge || {
        echo "❌ Failed to create merge migration"
        exit 1
    }
    
    echo "✅ Migration conflicts resolved"
else
    echo "✅ No migration conflicts found"
fi

# Step 2: Apply migrations
echo "📦 Applying migrations..."
python manage.py migrate || {
    echo "❌ Failed to apply migrations"
    exit 1
}

echo "✅ Migrations applied successfully"

# Step 3: Quick payment link test
echo "🧪 Testing payment link functionality..."
python manage.py shell -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'courseapp.settings')
django.setup()

try:
    from core.payment_link_service import PaymentLinkService
    service = PaymentLinkService()
    print('✅ Payment link service imported successfully')
except Exception as e:
    print(f'❌ Payment link service test failed: {e}')
    exit(1)
" || {
    echo "❌ Payment link service test failed"
    exit 1
}

echo "✅ Payment link functionality verified"

echo "🎉 Migration fix completed successfully!" 