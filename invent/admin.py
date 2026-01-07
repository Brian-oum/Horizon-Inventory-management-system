from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from django.contrib.auth.models import User, Group
from django.db.models import Q
from django.db.models import Count, Q, Sum
from django.utils.html import format_html
from django.shortcuts import redirect
from django import forms
from django.core.exceptions import PermissionDenied
# Import the ImportExportMixin
from import_export.admin import ImportExportModelAdmin
# ⭐ NEW: Import resources for defining import/export fields
from import_export import resources
from django.urls import path
from .models import DeviceSelectionGroup
from django.utils import timezone
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
    DeviceIMEI,
    DeviceRequestSelectedIMEI,
    SelectedDevice, 
    DeviceReports
)
from django.shortcuts import render, redirect

# Removed openpyxl and DeviceUploadForm imports that were part of the old, incorrect bulk upload logic

ASSIGNABLE_GROUPS = getattr(settings, 'BRANCH_ADMIN_ASSIGNABLE_GROUPS', None)


# --- Simple model registrations for small models ---
admin.site.register(Branch)
admin.site.register(OEM)
admin.site.register(Country)
admin.site.register(Client)


# Profile admin (separate)
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'branch', 'country', 'phone_no')
    search_fields = ('user__username', 'user__email')
    list_select_related = ('user', 'branch', 'country')


# Inline profile for user change form only
class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'profile'
    fk_name = 'user'


def _get_user_branch_from_request(request):
    try:
        return getattr(request.user.profile, 'branch', None)
    except Exception:
        return None


class CustomUserAdmin(DefaultUserAdmin):

    inlines = (ProfileInline,)
    list_display = ('username', 'email', 'is_staff', 'is_active', 'get_branch')
    list_select_related = ('profile',)

    def get_branch(self, obj):
        try:
            return obj.profile.branch.name if obj.profile and obj.profile.branch else "-"
        except Exception:
            return "-"
    get_branch.short_description = "Branch"

    def get_inline_instances(self, request, obj=None):
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related('profile')
        if request.user.is_superuser:
            return qs
        user_branch = _get_user_branch_from_request(request)
        if not user_branch:
            return qs.none()
        return qs.filter(profile__branch=user_branch, is_superuser=False)

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return request.user.has_perm('auth.view_user')
        user_branch = _get_user_branch_from_request(request)
        obj_branch = getattr(getattr(obj, 'profile', None), 'branch', None)
        return (user_branch is not None and obj_branch == user_branch) and request.user.has_perm('auth.view_user')

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return request.user.has_perm('auth.change_user')
        user_branch = _get_user_branch_from_request(request)
        obj_branch = getattr(getattr(obj, 'profile', None), 'branch', None)
        if obj == request.user:
            return request.user.has_perm('auth.change_user')
        return (user_branch is not None and obj_branch == user_branch) and request.user.has_perm('auth.change_user')

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return request.user.has_perm('auth.delete_user')
        user_branch = _get_user_branch_from_request(request)
        obj_branch = getattr(getattr(obj, 'profile', None), 'branch', None)
        if obj.is_superuser:
            return False
        return (user_branch is not None and obj_branch == user_branch) and request.user.has_perm('auth.delete_user')

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == 'groups' and not request.user.is_superuser:
            if ASSIGNABLE_GROUPS:
                kwargs['queryset'] = Group.objects.filter(
                    name__in=ASSIGNABLE_GROUPS)
            else:
                kwargs['queryset'] = request.user.groups.all()
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        is_new = not change
        if not request.user.is_superuser:
            selected_groups = form.cleaned_data.get(
                'groups') if form.is_valid() else None
            if selected_groups is not None:
                if ASSIGNABLE_GROUPS:
                    allowed_qs = set(Group.objects.filter(
                        name__in=ASSIGNABLE_GROUPS))
                else:
                    allowed_qs = set(request.user.groups.all())

                selected_list = list(selected_groups)
                forbidden = [g for g in selected_list if g not in allowed_qs]
                if forbidden:
                    allowed_selected = [
                        g for g in selected_list if g in allowed_qs]
                    form.cleaned_data['groups'] = allowed_selected
                    messages.warning(request,
                                     "Some groups you selected were not allowed and have been removed automatically.")
        super().save_model(request, obj, form, change)

        if not request.user.is_superuser:
            post_groups = form.cleaned_data.get(
                'groups') if form.is_valid() else None
            if post_groups is not None:
                obj.groups.set(post_groups)

        if is_new and not request.user.is_superuser:
            try:
                user_branch = _get_user_branch_from_request(request)
                if user_branch:
                    profile, created = Profile.objects.get_or_create(user=obj)
                    if profile.branch != user_branch:
                        profile.branch = user_branch
                        profile.save()
            except Exception:
                pass


# Unregister default User admin and register our custom one
try:
    admin.site.unregister(User)
except Exception:
    pass
admin.site.register(User, CustomUserAdmin)


def get_user_branch(request):
    try:
        return getattr(request.user.profile, 'branch', None)
    except Exception:
        return None


class BranchScopedAdmin(admin.ModelAdmin):
    branch_field = 'branch'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        branch = get_user_branch(request)
        if not branch:
            return qs.none()
        if self.branch_field:
            if any(f.name == self.branch_field for f in self.model._meta.get_fields()):
                return qs.filter(**{self.branch_field: branch})
        # fallback: try filter via device__branch
        return qs.filter(device__branch=branch)

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return request.user.has_perm(f"{self.model._meta.app_label}.change_{self.model._meta.model_name}")
        branch = get_user_branch(request)
        if not branch:
            return False
        obj_branch = getattr(obj, self.branch_field,
                             None) if self.branch_field else None
        if obj_branch is None and hasattr(obj, 'device'):
            obj_branch = getattr(obj.device, 'branch', None)
        return obj_branch == branch and request.user.has_perm(f"{self.model._meta.app_label}.change_{self.model._meta.model_name}")

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return request.user.has_perm(f"{self.model._meta.app_label}.delete_{self.model._meta.model_name}")
        branch = get_user_branch(request)
        if not branch:
            return False
        obj_branch = getattr(obj, self.branch_field,
                             None) if self.branch_field else None
        if obj_branch is None and hasattr(obj, 'device'):
            obj_branch = getattr(obj.device, 'branch', None)
        return obj_branch == branch and request.user.has_perm(f"{self.model._meta.app_label}.delete_{self.model._meta.model_name}")

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            branch = get_user_branch(request)
            if branch:
                if self.branch_field and hasattr(obj, self.branch_field) and getattr(obj, self.branch_field, None) is None:
                    setattr(obj, self.branch_field, branch)
        super().save_model(request, obj, form, change)

# DeviceIMEI inline for Device admin

class DeviceIMEIInline(admin.TabularInline):
    model = DeviceIMEI
    extra = 1
    # FIX: Added serial_no and mac_address back to the inline
    fields = ('imei_number', 'serial_no', 'mac_address', 'is_available')
    readonly_fields = ()


# ⭐ FIX: DeviceResource fields are adjusted to only represent the Product (Device)
class DeviceResource(resources.ModelResource):
    """
    Defines the fields available for import/export for the Device model,
    excluding unique asset identifiers, product_id, manufacturer, and description.
    """
    class Meta:
        model = Device
        # Define the exact fields allowed for import/export
        fields = (
            'name',
            'oem',
            'category',
            'status', # Status of the device type (e.g., Active/Obsolete)
        )
        # Exclude all other fields
        exclude = (
            'id',
            'imei_no',
            'serial_no',
            'mac_address',
            'product_id',       # <-- REMOVED as requested
            'manufacturer',     # <-- REMOVED as requested
            'description',      # <-- REMOVED as requested
            'total_quantity',
            'quantity_issued',
            'selling_price',
            'currency',
            'branch',
            'country'
        )

# Device admin
@admin.register(Device)
class DeviceAdmin(ImportExportModelAdmin, BranchScopedAdmin): # Use ImportExportModelAdmin
    # form = DeviceUploadForm # REMOVED: Reverted to default ModelForm, bulk logic is gone.
    
    # FIXED list_display: Removed imei_no/serial_no/etc. Kept calculated quantities.
    list_display = (
        'category', 
        'name', 
        'oem', 
        'status',
        # Assuming total_quantity and available_quantity are methods/properties on the Device model
        'total_quantity', 
        'available_quantity', 
    )
    list_filter = ('category', 'oem', 'status')
    
    # FIXED search_fields: Removed unique IDs. Search only on product-level fields.
    search_fields = ('name',) 
    
    ordering = ('category', 'name')
    list_display_links = ('name',)
    
    # FIX: Custom fieldsets to remove product_id, manufacturer, and description
    fieldsets = (
        (None, {
            'fields': (
                'category', 
                'name', 
                'oem',
                'status',
            )
        }),
        ('Location (Optional)', {
            'classes': ('collapse',),
            'fields': ('branch', 'country',),
        }),
    )
    
    inlines = [DeviceIMEIInline]
    
    # Removed get_form method since the custom form with broken upload logic is removed.
    
# Issuance/Request/Return Inlines and Admins

# --- Admin Inline for SelectedDevice ---
class SelectedDeviceInline(admin.TabularInline):
    model = SelectedDevice
    extra = 0
    readonly_fields = ('get_imei_number', 'get_selected_by', 'selected_at')
    fields = ('get_imei_number', 'get_selected_by', 'selected_at', 'approved', 'rejected')

    # Display the IMEI number instead of the object
    def get_imei_number(self, obj):
        return obj.imei.imei_number if obj.imei else "-"
    get_imei_number.short_description = 'IMEI/ID'

    # Display who selected the IMEI
    def get_selected_by(self, obj):
        return obj.selected_by.username if obj.selected_by else "-"
    get_selected_by.short_description = 'Store Clerk'

    # Only select related fields that exist on SelectedDevice
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('imei', 'request')  # Removed 'selected_by' to avoid FieldError

    # Allow editing approved/rejected flags in admin
    def has_change_permission(self, request, obj=None):
        return True  # Admin can approve/reject

    def has_add_permission(self, request, obj=None):
        return False  # Only allow admin to edit existing selections
 
# DeviceRequest admin

@admin.register(DeviceRequest)
class DeviceRequestAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'device',
        'requestor',
        'client',
        'branch',
        'status',
        'date_requested'
    )

    list_filter = ('status', 'branch')

    search_fields = (
        'device__name',
        'requestor__username',
        'client__name',
        # FIX: Correctly traverse to the IMEI number
        'selected_imeis__imei__imei_number',
        'selected_imeis__imei__serial_no'
    )

    inlines = [SelectedDeviceInline]

    actions = ['approve_requests', 'reject_requests']

    @admin.action(description="✅ Approve selected IMEIs")
    def approve_requests(self, request, queryset):
        approved_count = 0

        for device_request in queryset:
            if device_request.status != 'Waiting Approval':
                continue

            # NOTE: Use the correct related name 'selected_imeis'
            selections = device_request.selected_imeis.filter(approved=False, rejected=False)
            
            # Quantity enforcement
            if selections.count() != device_request.quantity:
                self.message_user(
                    request,
                    f"Request #{device_request.id}: selected IMEIs "
                    f"({selections.count()}) do not match quantity ({device_request.quantity})",
                    level=messages.ERROR
                )
                continue

            can_approve = True
            imeis_to_issue = []
            for selection in selections:
                imei = selection.imei
                if not imei.is_available:
                    self.message_user(
                        request,
                        f"IMEI {imei.imei_number} is no longer available.",
                        level=messages.ERROR
                    )
                    can_approve = False
                    break
                imeis_to_issue.append(imei)
            
            if not can_approve:
                continue

            for imei in imeis_to_issue:
                # Lock IMEI (Assuming mark_unavailable() is a method on DeviceIMEI)
                imei.is_available = False # Direct update if mark_unavailable doesn't exist
                imei.save(update_fields=['is_available'])
                
                # Create issuance record
                IssuanceRecord.objects.create(
                    device=imei.device,
                    imei=imei, # Pass the DeviceIMEI object
                    client=device_request.client,
                    logistics_manager=request.user,
                    device_request=device_request
                )

            # Mark all selections for this request as approved
            selections.update(approved=True)
            
            device_request.status = 'Approved'
            device_request.date_issued = timezone.now()
            device_request.save(update_fields=['status', 'date_issued'])

            approved_count += 1

        self.message_user(
            request,
            f"{approved_count} request(s) approved successfully.",
            level=messages.SUCCESS
        )

    @admin.action(description="❌ Reject selected requests")
    def reject_requests(self, request, queryset):
        rejected = 0

        for device_request in queryset:
            if device_request.status == 'Pending':
                device_request.status = 'Rejected'
                device_request.save(update_fields=['status'])
                rejected += 1
                
                # Release any selected IMEIs that were not approved/rejected yet (safety)
                device_request.selected_imeis.filter(approved=False, rejected=False).update(rejected=True)

        self.message_user(
            request,
            f"{rejected} request(s) rejected.",
            level=messages.ERROR
        )

# PurchaseOrder admin
@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(ImportExportModelAdmin, BranchScopedAdmin):
    list_display = ('id', 'oem', 'branch', 'order_date',
                    'expected_delivery', 'status')
    search_fields = ('oem__name',)
    list_filter = ('status', 'branch')
    branch_field = 'branch'
# IssuanceRecord admin (fallback to device.branch)


@admin.register(IssuanceRecord)
class IssuanceRecordAdmin(BranchScopedAdmin):
    # FIX: Added imei back to display
    list_display = ('device', 'imei', 'client', 'logistics_manager', 'issued_at') 
    # FIX: Search on imei fields, not old device fields
    search_fields = (
        'imei__imei_number', 
        'imei__serial_no',
        'client__name', 
        'logistics_manager__username'
    )
    branch_field = None
# ReturnRecord admin


@admin.register(ReturnRecord)
class ReturnRecordAdmin(BranchScopedAdmin):
    list_display = ('device', 'client', 'returned_at', 'reason')
    # FIX: Search fields adjusted since unique IDs are not on Device
    search_fields = ('device__name', 'client__name')
    branch_field = None


@admin.register(DeviceIMEI)
class DeviceIMEIAdmin(BranchScopedAdmin):
    # FIX: Added serial_no/mac_address for better visibility
    list_display = ('imei_number', 'serial_no', 'mac_address', 'device', 'is_available') 
    # FIX: Search fields adjusted
    search_fields = ('imei_number', 'serial_no', 'mac_address', 'device__name', 'device__category')
    list_filter = ('is_available',)
    branch_field = None


@admin.register(DeviceSelectionGroup)
class DeviceSelectionGroupAdmin(admin.ModelAdmin):
    list_display = ('id', 'device_request', 'store_clerk',
                    'status', 'created_at', 'reviewed_at', 'reviewed_by')
    list_filter = ('status', 'created_at')
    # FIX: Search fields adjusted to the new structure
    search_fields = (
        'device_request__id', 
        'store_clerk__username',
        'devices__name',
    )

# admin.py

from django.contrib import admin
from django.db.models import Count, Sum, Q, Value
from django.db.models.functions import Coalesce

@admin.register(DeviceReports)
class DeviceReportsAdmin(admin.ModelAdmin):

    list_display = (
        'branch',
        'total_requests',
        'pending_requests',
        'approved_requests',
        'issued_requests',
        'rejected_requests',
        'fully_returned_requests',
        'partially_returned_requests',
        'total_returned_quantity',
    )

    readonly_fields = list_display

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request): return False
