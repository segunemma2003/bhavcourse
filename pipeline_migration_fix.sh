#!/bin/bash

# Migration Conflict Fix for CI/CD Pipeline
# Add this to your deployment pipeline before running migrations

set -e  # Exit on any error

echo "🔧 Running migration conflict fix..."

# Check if we're in a Django project
if [ ! -f "manage.py" ]; then
    echo "❌ manage.py not found. Are you in the correct directory?"
    exit 1
fi

# Step 1: Check for migration conflicts
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

# Step 2: Apply migrations
echo "📦 Applying migrations..."
python manage.py migrate || {
    echo "❌ Failed to apply migrations"
    exit 1
}

echo "✅ Migrations applied successfully"

echo "🎉 Migration fix completed successfully!" 