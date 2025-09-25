#!/usr/bin/env python
import os
import django
import sys

# Add the project directory to the Python path
sys.path.append('C:/Desktop/Horizon-Inventory-management-system')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Inventory.settings')

# Setup Django
django.setup()

from django.db import connection
from invent.models import Category, InventoryItem, Device

# Get distinct categories from InventoryItem using raw SQL
cursor = connection.cursor()
cursor.execute("SELECT DISTINCT category FROM invent_inventoryitem WHERE category IS NOT NULL AND category != ''")
inv_categories = [row[0] for row in cursor.fetchall()]

cursor.execute("SELECT DISTINCT category FROM invent_device WHERE category IS NOT NULL AND category != ''")
dev_categories = [row[0] for row in cursor.fetchall()]

# Combine and unique
all_categories = set(inv_categories) | set(dev_categories)

# Create Category objects
for cat_name in all_categories:
    Category.objects.get_or_create(name=cat_name)

print(f"Created {len(all_categories)} categories.")

# Now, update InventoryItem.category_id using raw SQL
for cat_name in inv_categories:
    cat = Category.objects.get(name=cat_name)
    cursor.execute("UPDATE invent_inventoryitem SET category_id = %s WHERE category = %s", [cat.id, cat_name])

print("Updated InventoryItem categories.")

# Update Device.category_id
for cat_name in dev_categories:
    cat = Category.objects.get(name=cat_name)
    cursor.execute("UPDATE invent_device SET category_id = %s WHERE category = %s", [cat.id, cat_name])

print("Updated Device categories.")
