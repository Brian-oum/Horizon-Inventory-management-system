from django.contrib import admin
from .models import (
    Office,
    Supplier,
    PurchaseOrder,
    Device,
    Client,
    IssuanceRecord,
    ReturnRecord,
    DeviceRequest,
)

# Register your models so they appear in the Django admin interface.
admin.site.register(Office)
admin.site.register(Supplier)
admin.site.register(PurchaseOrder)
admin.site.register(Device)
admin.site.register(Client)
admin.site.register(IssuanceRecord)
admin.site.register(ReturnRecord)
admin.site.register(DeviceRequest)