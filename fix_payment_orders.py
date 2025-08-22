#!/usr/bin/env python3
"""
Script to fix PaymentOrder records with empty razorpay_order_id values.
This should be run on the server where the database is accessible.
"""

import os
import sys
import django
import uuid

# Add the project directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'courseapp.settings')
django.setup()

from core.models import PaymentOrder

def fix_empty_razorpay_ids():
    """Fix PaymentOrder records with empty razorpay_order_id values"""
    print("Starting to fix empty razorpay_order_id values...")
    
    # Find all PaymentOrder records with empty razorpay_order_id
    empty_orders = PaymentOrder.objects.filter(
        razorpay_order_id=''
    )
    
    print(f"Found {empty_orders.count()} orders with empty razorpay_order_id")
    
    if empty_orders.count() == 0:
        print("No empty razorpay_order_id values found. Nothing to fix.")
        return
    
    fixed_count = 0
    for order in empty_orders:
        # Generate a unique temporary ID
        new_order_id = f"plink_{uuid.uuid4().hex[:16]}"
        
        # Check if this ID already exists
        while PaymentOrder.objects.filter(razorpay_order_id=new_order_id).exists():
            new_order_id = f"plink_{uuid.uuid4().hex[:16]}"
        
        # Update the order
        order.razorpay_order_id = new_order_id
        order.save()
        fixed_count += 1
        
        print(f'Fixed order {order.id}: {new_order_id}')
    
    print(f"Successfully fixed {fixed_count} PaymentOrder records")

def check_duplicate_razorpay_ids():
    """Check for any duplicate razorpay_order_id values"""
    print("\nChecking for duplicate razorpay_order_id values...")
    
    from django.db.models import Count
    
    duplicates = PaymentOrder.objects.values('razorpay_order_id').annotate(
        count=Count('razorpay_order_id')
    ).filter(count__gt=1)
    
    if duplicates.exists():
        print(f"Found {duplicates.count()} duplicate razorpay_order_id values:")
        for dup in duplicates:
            print(f"  - {dup['razorpay_order_id']}: {dup['count']} occurrences")
    else:
        print("No duplicate razorpay_order_id values found.")

if __name__ == "__main__":
    try:
        fix_empty_razorpay_ids()
        check_duplicate_razorpay_ids()
        print("\n✅ Database fix completed successfully!")
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        sys.exit(1) 