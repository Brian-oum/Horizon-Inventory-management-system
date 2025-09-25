#!/usr/bin/env python
import os
import django
import sys

# Add the project directory to the Python path
sys.path.append('C:/Desktop/Horizon-Inventory-management-system')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Inventory.settings')

# Setup Django
django.setup()

from invent.models import Box

# Get all boxes ordered by id
boxes = Box.objects.all().order_by('id')

# First, assign temporary unique numbers
for box in boxes:
    box.number = box.id + 1000  # temporary
    box.save()

# Then, assign sequential numbers
for i, box in enumerate(boxes, start=1):
    box.number = i
    box.save()

print("Boxes renumbered successfully.")
