# Generated manually to fix razorpay_order_id constraints

from django.db import migrations, models
import uuid

def fix_empty_razorpay_ids(apps, schema_editor):
    """Fix any existing PaymentOrder records with empty razorpay_order_id"""
    PaymentOrder = apps.get_model('core', 'PaymentOrder')
    
    # Find all PaymentOrder records with empty razorpay_order_id
    empty_orders = PaymentOrder.objects.filter(razorpay_order_id='')
    
    for order in empty_orders:
        # Generate a unique temporary ID
        new_order_id = f"plink_{uuid.uuid4().hex[:16]}"
        
        # Check if this ID already exists
        while PaymentOrder.objects.filter(razorpay_order_id=new_order_id).exists():
            new_order_id = f"plink_{uuid.uuid4().hex[:16]}"
        
        # Update the order
        order.razorpay_order_id = new_order_id
        order.save()

def reverse_fix_empty_razorpay_ids(apps, schema_editor):
    """Reverse operation - not needed"""
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_appleiapproduct_appleiapreceipt_paymentlinkrequest_and_more'),
    ]

    operations = [
        # First fix any existing empty values
        migrations.RunPython(fix_empty_razorpay_ids, reverse_fix_empty_razorpay_ids),
        
        # Note: We're now using proper Razorpay order IDs, so no additional constraints needed
    ] 