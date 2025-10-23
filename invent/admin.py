from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from django.contrib.auth.models import User
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

# Register your other models normally
admin.site.register(Branch)
admin.site.register(OEM)
admin.site.register(PurchaseOrder)
admin.site.register(Device)
admin.site.register(Client)
admin.site.register(IssuanceRecord)
admin.site.register(ReturnRecord)
admin.site.register(DeviceRequest)
admin.site.register(Country)

# Remove the old Profile registration:
# admin.site.register(Profile)  <-- DELETE this line

# Create an inline form for Profile so it appears on the User admin page
class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Profile'

# Extend the default User admin to include Profile inline
class UserAdmin(DefaultUserAdmin):
    inlines = (ProfileInline,)

# Re-register User admin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
