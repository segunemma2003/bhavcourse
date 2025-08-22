#!/usr/bin/env python3
"""
Migration Conflict Fix Script
This script helps fix the migration conflict where tables already exist but Django thinks they don't.
"""

import os
import sys
import django
from pathlib import Path

# Setup Django
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'courseapp.settings')

def check_table_exists(table_name):
    """Check if a table exists in the database"""
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_schema = DATABASE() 
            AND table_name = %s
        """, [table_name])
        return cursor.fetchone()[0] > 0

def fix_migration_conflict():
    """Fix the migration conflict by checking existing tables"""
    django.setup()
    
    from django.db import connection
    from django.db.migrations.recorder import MigrationRecorder
    
    print("🔍 Checking for migration conflicts...")
    
    # Tables that might already exist
    tables_to_check = [
        'core_appleiapproduct',
        'core_appleiapreceipt', 
        'core_paymentlinkrequest',
        'core_paymentorder'
    ]
    
    existing_tables = []
    for table in tables_to_check:
        if check_table_exists(table):
            existing_tables.append(table)
            print(f"✅ Table {table} exists")
        else:
            print(f"❌ Table {table} does not exist")
    
    if not existing_tables:
        print("No existing tables found. Running normal migration...")
        os.system("python manage.py migrate")
        return
    
    print(f"\n📋 Found {len(existing_tables)} existing tables")
    
    # Check current migration state
    recorder = MigrationRecorder(connection)
    applied_migrations = set()
    
    try:
        for migration in recorder.migration_qs.all():
            if migration.app == 'core':
                applied_migrations.add(migration.name)
    except Exception as e:
        print(f"Warning: Could not read migration history: {e}")
    
    print(f"Currently applied core migrations: {applied_migrations}")
    
    # Find the migration that creates these tables
    migration_name = "0017_appleiapproduct_appleiapreceipt_paymentlinkrequest_and_more"
    
    if migration_name not in applied_migrations:
        print(f"\n🔧 Marking migration {migration_name} as applied...")
        
        # Mark the migration as applied
        recorder.record_applied('core', migration_name)
        print(f"✅ Migration {migration_name} marked as applied")
        
        # Try to run remaining migrations
        print("\n🔄 Running remaining migrations...")
        os.system("python manage.py migrate")
    else:
        print(f"Migration {migration_name} is already marked as applied")
        print("Running all migrations to ensure consistency...")
        os.system("python manage.py migrate")

if __name__ == "__main__":
    fix_migration_conflict() 