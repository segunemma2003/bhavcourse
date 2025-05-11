from django.core.management.base import BaseCommand
from core.models import ContentPage
from core.admin_views import ContentPageMixin

class Command(BaseCommand, ContentPageMixin):
    help = 'Creates or resets the default content pages (Privacy Policy, Terms & Conditions)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Reset existing content pages to default content',
        )
        parser.add_argument(
            '--page-type',
            type=str,
            help='Specify a page type to create/reset (PRIVACY or TERMS). If not specified, both will be processed.',
        )
    
    def handle(self, *args, **options):
        reset = options['reset']
        page_type = options['page_type']
        
        page_types = ['PRIVACY', 'TERMS']
        if page_type:
            if page_type not in page_types:
                self.stderr.write(self.style.ERROR(f"Invalid page type: {page_type}. Use PRIVACY or TERMS."))
                return
            page_types = [page_type]
        
        for pt in page_types:
            if reset:
                # Delete existing content page if it exists and create a new one
                ContentPage.objects.filter(page_type=pt).delete()
                content_page = ContentPage.objects.create(
                    page_type=pt,
                    content=self.get_default_content(pt)
                )
                self.stdout.write(self.style.SUCCESS(f"Reset {pt} content page to default."))
            else:
                # Create content page if it doesn't exist
                content_page, created = self.get_or_create_content_page(pt)
                if created:
                    self.stdout.write(self.style.SUCCESS(f"Created new {pt} content page with default content."))
                else:
                    self.stdout.write(self.style.SUCCESS(f"{pt} content page already exists."))
                    
                    
# python manage.py setup_content_pages --reset

# # Create/reset only a specific page type
# python manage.py setup_content_pages --page-type=PRIVACY