from invent.models import DeviceRequest, Device, DeviceIMEI, OEM
from django.db.models import Q

REQUEST_ID = 7  # change this number if you want to inspect a different request id

def show(q, label=None):
    if label:
        print("----", label, "----")
    print(q)

try:
    req = DeviceRequest.objects.get(id=REQUEST_ID)
except DeviceRequest.DoesNotExist:
    print(f"DeviceRequest with id={REQUEST_ID} not found")
    raise SystemExit(1)

dev = req.device
print("Request id:", req.id)
print("Device referenced by request: id=", getattr(dev, 'id', None), "repr=", repr(dev))
print("  name:", dev.name)
print("  imei_no:", dev.imei_no)
print("  serial_no:", getattr(dev, 'serial_no', None))
print("  status:", dev.status)
print("  oem (FK id):", getattr(dev.oem, 'id', None), "oem.name:", getattr(dev.oem, 'name', None))

# DeviceIMEI rows linked to this exact Device instance
imei_for_exact_device = DeviceIMEI.objects.filter(device=dev)
print("\nDeviceIMEI rows for the exact Device instance (device_id=%s): %d" % (dev.id, imei_for_exact_device.count()))
print(list(imei_for_exact_device.values('id','imei_number','is_available','device_id')[:50]))

# DeviceIMEI rows matching by product attributes (name + OEM)
imei_by_product_exact = DeviceIMEI.objects.filter(
    device__name__iexact=dev.name,
    device__oem=dev.oem,
    is_available=True
)
print("\nDeviceIMEI rows matching by product (name iexact + OEM FK) and is_available=True: %d" % imei_by_product_exact.count())
print(list(imei_by_product_exact.values('id','imei_number','is_available','device_id')[:50]))

# Broader DeviceIMEI matches (icontains name OR OEM name)
imei_by_product_broad = DeviceIMEI.objects.filter(
    is_available=True
).filter(
    Q(device__name__icontains=dev.name) |
    Q(device__imei_no__icontains=(dev.imei_no or "")) |
    Q(device__serial_no__icontains=(dev.serial_no or "")) |
    Q(device__oem__name__icontains=(dev.oem.name or ""))
)
print("\nDeviceIMEI rows matching broader criteria (is_available=True and icontains matches): %d" % imei_by_product_broad.count())
print(list(imei_by_product_broad.values('id','imei_number','is_available','device_id','device__name','device__imei_no')[:50]))

# How many DeviceIMEI exist overall
print("\nTotal DeviceIMEI rows in DB:", DeviceIMEI.objects.count())

# Show some Device rows that match the product (old approach)
dev_rows = Device.objects.filter(name=dev.name, oem=dev.oem, status='available')
print("\nDevice rows with same name/oem and status='available':", dev_rows.count())
print(list(dev_rows.values('id','imei_no','serial_no')[:50]))

# If OEM foreign keys might differ, list all OEMs with the same name
same_oem_name = OEM.objects.filter(name__iexact=dev.oem.name)
print("\nOEM rows with same name (case-insensitive):", list(same_oem_name.values('id','name')[:20]))

# Print the SQL query for the exact product match (for advanced debugging)
try:
    print("\nSample SQL for `imei_by_product_exact` queryset:")
    print(str(imei_by_product_exact.query))
except Exception as e:
    print("Could not print SQL:", e)

print("\nEnd of check.")