#!/usr/bin/env python3
"""
Fix payment orders with empty razorpay_order_id values
"""

import os
import sys
import django
from pathlib import Path

# Add the project directory to Python path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'courseapp.settings')

def fix_payment_orders():
    """Fix payment orders with empty razorpay_order_id"""
    print("🔧 Fixing Payment Orders with Empty razorpay_order_id:")
    
    try:
        django.setup()
        from core.models import PaymentOrder
        import uuid
        
        # Find payment orders with empty razorpay_order_id
        empty_orders = PaymentOrder.objects.filter(razorpay_order_id='')
        print(f"Found {empty_orders.count()} payment orders with empty razorpay_order_id")
        
        if empty_orders.count() > 0:
            # Update them with unique IDs
            for order in empty_orders:
                order.razorpay_order_id = f"fixed_{uuid.uuid4().hex[:16]}"
                order.save()
                print(f"Fixed order {order.id}: {order.razorpay_order_id}")
        
        # Also check for null values
        null_orders = PaymentOrder.objects.filter(razorpay_order_id__isnull=True)
        print(f"Found {null_orders.count()} payment orders with null razorpay_order_id")
        
        if null_orders.count() > 0:
            # Update them with unique IDs
            for order in null_orders:
                order.razorpay_order_id = f"fixed_{uuid.uuid4().hex[:16]}"
                order.save()
                print(f"Fixed null order {order.id}: {order.razorpay_order_id}")
        
        print("✅ Payment orders fixed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Failed to fix payment orders: {e}")
        return False

if __name__ == "__main__":
    fix_payment_orders() 