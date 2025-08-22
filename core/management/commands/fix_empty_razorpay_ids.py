import uuid
from django.core.management.base import BaseCommand
from core.models import PaymentOrder


class Command(BaseCommand):
    help = 'Fix PaymentOrder records with empty razorpay_order_id values'

    def handle(self, *args, **options):
        self.stdout.write('Starting to fix empty razorpay_order_id values...')
        
        # Find all PaymentOrder records with empty razorpay_order_id
        empty_orders = PaymentOrder.objects.filter(
            razorpay_order_id=''
        )
        
        self.stdout.write(f'Found {empty_orders.count()} orders with empty razorpay_order_id')
        
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
            
            self.stdout.write(f'Fixed order {order.id}: {new_order_id}')
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully fixed {fixed_count} PaymentOrder records')
        ) 