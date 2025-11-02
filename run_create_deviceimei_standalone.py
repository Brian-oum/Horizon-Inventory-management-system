import os
import sys

# Ensure project root (where this file lives) is on sys.path
proj_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, proj_root)

# Use the correct settings module for your project:
# your settings file header says "Django settings for Inventory project."
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Inventory.settings")

import django
django.setup()

from django.db import transaction
from invent.models import Device, DeviceIMEI

def main():
    created = 0
    skipped = 0
    updated = 0

    devices_with_imei = Device.objects.exclude(imei_no__isnull=True).exclude(imei_no__exact='')

    with transaction.atomic():
        for d in devices_with_imei:
            imei_val = (d.imei_no or "").strip()
            if not imei_val:
                skipped += 1
                continue

            obj, created_flag = DeviceIMEI.objects.get_or_create(
                imei_number=imei_val,
                defaults={
                    "device": d,
                    "is_available": True if getattr(d, "status", "") == "available" else False
                }
            )

            if created_flag:
                created += 1
            else:
                if obj.device_id != d.id:
                    skipped += 1

    print(f"Done. Created: {created}, Skipped (existing or blank or linked to other device): {skipped}, Updated: {updated}")

if __name__ == "__main__":
    main()