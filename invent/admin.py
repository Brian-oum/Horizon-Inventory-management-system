from django.contrib import admin
from .models import Profile
from .models import (
    Branch,
    OEM,
    PurchaseOrder,
    Device,
    Client,
    IssuanceRecord,
    ReturnRecord,
    DeviceRequest,
    Profile,
    Country,
)

# Register your models so they appear in the Django admin interface.
admin.site.register(Branch)
admin.site.register(OEM)
admin.site.register(PurchaseOrder)
admin.site.register(Device)
admin.site.register(Client)
admin.site.register(IssuanceRecord)
admin.site.register(ReturnRecord)
admin.site.register(DeviceRequest)
admin.site.register(Profile)
admin.site.register(Country)