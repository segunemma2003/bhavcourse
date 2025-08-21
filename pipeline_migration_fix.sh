#!/bin/bash

# Migration Conflict Fix for CI/CD Pipeline
# Add this to your deployment pipeline before running migrations

set -e  # Exit on any error

echo "🔧 Running migration conflict fix..."

# Function to handle errors
handle_error() {
    echo "❌ Error occurred: $1"
    exit 1
}

# Check if we're in a Django project
if [ ! -f "manage.py" ]; then
    handle_error "manage.py not found. Are you in the correct directory?"
fi

# Step 1: Verify MySQL client is working
echo "🔍 Verifying MySQL client..."
if ! python -c "import MySQLdb; print('✅ MySQL client working')" 2>/dev/null; then
    echo "❌ MySQL client not working. Installing..."
    pip install mysqlclient
    if ! python -c "import MySQLdb; print('✅ MySQL client working after install')" 2>/dev/null; then
        handle_error "Failed to install MySQL client"
    fi
fi

# Step 2: Check database connection
echo "🔍 Testing database connection..."
python manage.py check --database default || {
    echo "❌ Database connection failed"
    exit 1
}

# Step 3: Check for migration conflicts
echo "📋 Checking for migration conflicts..."
MIGRATION_OUTPUT=$(python manage.py showmigrations core 2>&1 || true)

if echo "$MIGRATION_OUTPUT" | grep -q "Conflicting migrations detected"; then
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

# Step 4: Apply migrations
echo "📦 Applying migrations..."
python manage.py migrate || {
    echo "❌ Failed to apply migrations"
    exit 1
}

echo "✅ Migrations applied successfully"

# Step 5: Quick payment link test
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
    
    # Test basic functionality
    from core.models import User, Course
    print('✅ Models imported successfully')
    
except Exception as e:
    print(f'❌ Payment link service test failed: {e}')
    exit(1)
" || {
    echo "❌ Payment link service test failed"
    exit 1
}

echo "✅ Payment link functionality verified"

echo "🎉 Migration fix completed successfully!" 