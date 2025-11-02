from django.db import transaction
from invent.models import Device, DeviceIMEI

def main():
    created = 0
    skipped = 0
    updated = 0

    # Find Device rows that have a non-empty imei_no
    devices_with_imei = Device.objects.exclude(imei_no__isnull=True).exclude(imei_no__exact='')

    with transaction.atomic():
        for d in devices_with_imei:
            imei_val = (d.imei_no or "").strip()
            if not imei_val:
                skipped += 1
                continue

            # Create a DeviceIMEI for this imei if it doesn't already exist.
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
                # If the existing DeviceIMEI points to a different device, skip to avoid overwriting.
                if obj.device_id != d.id:
                    skipped += 1

    print(f"Done. Created: {created}, Skipped (existing or blank or linked to other device): {skipped}, Updated: {updated}")

if __name__ == "__main__":
    main()