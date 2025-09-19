import csv
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from invent.models import InventoryItem

class Command(BaseCommand):
    help = 'Imports ICT assets from a CSV file into the InventoryItem model.'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='The path to the CSV file')
        parser.add_argument('--created_by_username', type=str, default='admin',
                            help='Username of the user who created these inventory items (default: admin)')

    def handle(self, *args, **options):
        csv_file_path = options['csv_file']
        created_by_username = options['created_by_username']

        try:
            created_by_user = User.objects.get(username=created_by_username)
        except User.DoesNotExist:
            raise CommandError(f"User '{created_by_username}' does not exist. Please create the user or provide an existing one.")

        self.stdout.write(self.style.SUCCESS(f"Starting import from {csv_file_path}..."))

        imported_count = 0
        skipped_count = 0

        try:
            with open(csv_file_path, newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row_num, row in enumerate(reader, 2): # Start from 2 for row number in CSV
                    asset_description = row.get('Asset Description')
                    serial_number = row.get('Serial Number')
                    asset_category_minor = row.get('Asset Category-Minor')
                    condition = row.get('Condition')

                    if not asset_description or not serial_number:
                        self.stdout.write(self.style.WARNING(
                            f"Row {row_num}: Skipping due to missing 'Asset Description' or 'Serial Number': {row}"
                        ))
                        skipped_count += 1
                        continue

                    # Basic data cleaning/mapping if needed
                    # Ensure condition matches your CONDITION_CHOICES if strict
                    if condition not in [c[0] for c in InventoryItem.CONDITION_CHOICES]:
                        condition = "Serviceable" # Default if CSV value doesn't match choices

                    try:
                        # Use get_or_create to prevent duplicates based on serial_number
                        item, created = InventoryItem.objects.get_or_create(
                            serial_number=serial_number,
                            defaults={
                                'name': asset_description,
                                'category': asset_category_minor,
                                'condition': condition,
                                'quantity_total': 1, # Each unique serial number is one item
                                'created_by': created_by_user,
                                'status': 'In Stock',
                            }
                        )

                        if created:
                            imported_count += 1
                            self.stdout.write(self.style.SUCCESS(
                                f"Row {row_num}: Created '{item.name}' (S/N: {item.serial_number})"
                            ))
                        else:
                            skipped_count += 1
                            self.stdout.write(self.style.WARNING(
                                f"Row {row_num}: Skipped. Item with S/N '{serial_number}' already exists. ('{item.name}')"
                            ))

                    except Exception as e:
                        self.stdout.write(self.style.ERROR(
                            f"Row {row_num}: Error importing '{serial_number}': {e}"
                        ))
                        skipped_count += 1
        except FileNotFoundError:
            raise CommandError(f"CSV file not found at '{csv_file_path}'")
        except Exception as e:
            raise CommandError(f"An error occurred during CSV processing: {e}")

        self.stdout.write(self.style.SUCCESS(
            f"Import complete. Imported {imported_count} items. Skipped {skipped_count} items."
        ))