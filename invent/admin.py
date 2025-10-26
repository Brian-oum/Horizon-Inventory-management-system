from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from django.contrib.auth.models import User, Group
from django.db.models import Q
from django.core.exceptions import PermissionDenied

from .models import DeviceSelectionGroup
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
)

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
        # Hide inline on the add user page to avoid duplicate-profile creation.
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)

    def get_queryset(self, request):

        qs = super().get_queryset(request).select_related('profile')
        if request.user.is_superuser:
            return qs
        user_branch = _get_user_branch_from_request(request)
        if not user_branch:
            # If the acting user has no branch, return empty queryset
            return qs.none()
        # restrict to users in the same branch and exclude superusers
        return qs.filter(profile__branch=user_branch, is_superuser=False)

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        # allow viewing the changelist only if they have model view permission
        if obj is None:
            return request.user.has_perm('auth.view_user')
        # object-level: allow if same branch
        user_branch = _get_user_branch_from_request(request)
        obj_branch = getattr(getattr(obj, 'profile', None), 'branch', None)
        return (user_branch is not None and obj_branch == user_branch) and request.user.has_perm('auth.view_user')

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        # list page (obj is None) allowed if user has change permission
        if obj is None:
            return request.user.has_perm('auth.change_user')
        user_branch = _get_user_branch_from_request(request)
        obj_branch = getattr(getattr(obj, 'profile', None), 'branch', None)
        # allow owners (so a user can edit their own account) OR same-branch edits
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
        # Prevent deleting superusers via branch-admin
        if obj.is_superuser:
            return False
        return (user_branch is not None and obj_branch == user_branch) and request.user.has_perm('auth.delete_user')

    # Restrict which groups a non-superuser may choose in the admin form
    def formfield_for_manytomany(self, db_field, request, **kwargs):

        if db_field.name == 'groups' and not request.user.is_superuser:
            if ASSIGNABLE_GROUPS:
                kwargs['queryset'] = Group.objects.filter(
                    name__in=ASSIGNABLE_GROUPS)
            else:
                # fallback: allow assigning only groups the acting user is already in
                kwargs['queryset'] = request.user.groups.all()
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):

        is_new = not change

        # Defensive: ensure groups to be assigned are within allowed set
        if not request.user.is_superuser:
            selected_groups = form.cleaned_data.get(
                'groups') if form.is_valid() else None
            if selected_groups is not None:
                if ASSIGNABLE_GROUPS:
                    allowed_qs = set(Group.objects.filter(
                        name__in=ASSIGNABLE_GROUPS))
                else:
                    allowed_qs = set(request.user.groups.all())

                # selected_groups can be a QuerySet or list - normalize to list
                selected_list = list(selected_groups)
                forbidden = [g for g in selected_list if g not in allowed_qs]
                if forbidden:
                    # remove forbidden groups from selection and warn
                    allowed_selected = [
                        g for g in selected_list if g in allowed_qs]
                    # temporarily set the groups on the form instance so that super().save_model doesn't save forbidden ones
                    # We'll set the allowed groups explicitly after saving the User object.
                    form.cleaned_data['groups'] = allowed_selected
                    messages.warning(request,
                                     "Some groups you selected were not allowed and have been removed automatically.")
        # Save the user (this saves auth user fields)
        super().save_model(request, obj, form, change)

        # After saving the User, ensure the final groups match allowed selection (defensive)
        if not request.user.is_superuser:
            post_groups = form.cleaned_data.get(
                'groups') if form.is_valid() else None
            if post_groups is not None:
                obj.groups.set(post_groups)

        # If it's a new user and the acting user is not superuser, set the profile.branch
        if is_new and not request.user.is_superuser:
            try:
                user_branch = _get_user_branch_from_request(request)
                if user_branch:
                    profile, created = Profile.objects.get_or_create(user=obj)
                    # Only set branch if not already set
                    if profile.branch != user_branch:
                        profile.branch = user_branch
                        profile.save()
            except Exception:
                # Do not block user creation on profile assignment errors; log if needed.
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
            # ensure field exists on model
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
        # When a Branch Admin creates a new object, ensure it is assigned to their branch
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
    fields = ('imei_number', 'is_available')
    readonly_fields = ()
# Device admin


@admin.register(Device)
class DeviceAdmin(BranchScopedAdmin):
    list_display = ('name', 'oem', 'product_id', 'imei_no',
                    'serial_no', 'branch', 'status')
    search_fields = ('name', 'imei_no', 'serial_no', 'oem__name', 'product_id')
    list_filter = ('status', 'category', 'branch', 'oem')
    branch_field = 'branch'
    inlines = [DeviceIMEIInline]
# DeviceRequest admin


@admin.register(DeviceRequest)
class DeviceRequestAdmin(BranchScopedAdmin):
    list_display = ('id', 'device', 'requestor', 'client',
                    'branch', 'status', 'date_requested')
    search_fields = ('device__imei_no', 'device__serial_no',
                     'requestor__username', 'client__name')
    list_filter = ('status', 'branch')
    branch_field = 'branch'
# PurchaseOrder admin


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(BranchScopedAdmin):
    list_display = ('id', 'oem', 'branch', 'order_date',
                    'expected_delivery', 'status')
    search_fields = ('oem__name',)
    list_filter = ('status', 'branch')
    branch_field = 'branch'
# IssuanceRecord admin (fallback to device.branch)


@admin.register(IssuanceRecord)
class IssuanceRecordAdmin(BranchScopedAdmin):
    list_display = ('device', 'client', 'logistics_manager', 'issued_at')
    search_fields = ('device__imei_no', 'device__serial_no',
                     'client__name', 'logistics_manager__username')
    branch_field = None
# ReturnRecord admin


@admin.register(ReturnRecord)
class ReturnRecordAdmin(BranchScopedAdmin):
    list_display = ('device', 'client', 'returned_at', 'reason')
    search_fields = ('device__imei_no', 'device__serial_no', 'client__name')
    branch_field = None


@admin.register(DeviceIMEI)
class DeviceIMEIAdmin(BranchScopedAdmin):
    list_display = ('imei_number', 'device', 'is_available')
    search_fields = ('imei_number', 'device__name', 'device__product_id')
    list_filter = ('is_available',)
    branch_field = None  # It will inherit via device.branch


@admin.register(DeviceSelectionGroup)
class DeviceSelectionGroupAdmin(admin.ModelAdmin):
    list_display = ('id', 'device_request', 'store_clerk',
                    'status', 'created_at', 'reviewed_at', 'reviewed_by')
    list_filter = ('status', 'created_at')
    search_fields = ('device_request__id', 'store_clerk__username',
                     'devices__imei_no', 'devices__serial_no')
