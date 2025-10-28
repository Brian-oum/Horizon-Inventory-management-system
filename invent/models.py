from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
# --- BEGIN IoT/Client/OEM/Branch/Country Models ---

CURRENCY_CHOICES = (
    ('USD', 'US Dollar'),
    ('TZS', 'Tanzanian Shilling'),
    ('KES', 'Kenyan Shilling'),
    # Add more as needed
)

# --- Country Model ---


class Country(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


# --- Updated Branch: relates to Country ---
class Branch(models.Model):
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=255)
    country = models.ForeignKey(
        Country, on_delete=models.SET_NULL, null=True, blank=True
    )

    def __str__(self):
        return f"{self.name}, {self.country.name if self.country else ''}"


class OEM(models.Model):  # Formerly Supplier
    name = models.CharField(max_length=100, unique=True)
    contact_person = models.CharField(max_length=100, blank=True)
    phone_email = models.CharField(max_length=100, blank=True)
    address = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.name


class PurchaseOrder(models.Model):
    oem = models.ForeignKey(OEM, on_delete=models.CASCADE,
                            default=1)  # was supplier
    branch = models.ForeignKey(
        Branch, on_delete=models.SET_NULL, null=True, blank=True
    )
    order_date = models.DateField()
    expected_delivery = models.DateField()
    status = models.CharField(max_length=50)
    document = models.FileField(
        upload_to='purchase_orders/', null=True, blank=True
    )  # Optional

    def __str__(self):
        return f"PO #{self.id} - {self.oem.name}"


class Client(models.Model):
    name = models.CharField(max_length=255)
    phone_no = models.CharField(max_length=50)
    email = models.EmailField()
    address = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class Device(models.Model):
    STATUS_CHOICES = (
        ('available', 'Available'),
        ('issued', 'Issued'),
        ('returned', 'Returned'),
        ('faulty', 'Faulty'),
    )

    name = models.CharField(max_length=255)
    oem = models.ForeignKey(
        OEM,
        on_delete=models.SET_NULL,
        null=True,
        blank=False,
        related_name='devices'
    )
    product_id = models.CharField(max_length=30, blank=True)
    total_quantity = models.PositiveIntegerField(default=1)
    quantity_issued = models.PositiveIntegerField(default=0)
    imei_no = models.CharField(
        max_length=50, unique=True, null=True, blank=True)
    serial_no = models.CharField(
        max_length=50, unique=True, null=True, blank=True)
    mac_address = models.CharField(
        max_length=50, unique=True, null=True, blank=True)
    category = models.CharField(
        max_length=100, blank=True, help_text="e.g. Laptop or Router")
    manufacturer = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    selling_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(
        max_length=10, choices=CURRENCY_CHOICES, default='USD')
    branch = models.ForeignKey(
        Branch, on_delete=models.SET_NULL, null=True, blank=True)
    country = models.ForeignKey(
        Country, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='available')

    class Meta:
        permissions = [
            ("can_issue_item", "Can issue device to client"),
            ("can_return_item", "Can record device returns"),
        ]

    def quantity_remaining(self):
        return self.total_quantity - self.quantity_issued

    @property
    def available_quantity(self):
        from django.db.models import Sum
        requested_sum = self.requests.filter(
            status__in=['Pending', 'Approved', 'Issued']
        ).aggregate(Sum('quantity'))['quantity__sum'] or 0
        return max(self.total_quantity - requested_sum, 0)

    def __str__(self):
        return f"{self.name} ({self.status})"


# NEW: DeviceSelectionGroup - groups devices selected by a clerk for a request

class DeviceSelectionGroup(models.Model):
    STATUS_CHOICES = (
        # created by clerk, waiting admin review
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),          # approved by branch admin
        ('Rejected', 'Rejected'),          # rejected by branch admin
    )

    device_request = models.ForeignKey(
        'DeviceRequest',
        on_delete=models.CASCADE,
        related_name='selection_groups'
    )
    store_clerk = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='device_selection_groups'
    )
    devices = models.ManyToManyField('Device', related_name='selection_groups')
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='device_selection_reviews'
    )

    class Meta:
        ordering = ['-created_at']
        permissions = [
            ("can_approve_selection", "Can approve device selection groups"),
        ]

    def __str__(self):
        return f"Selection for Request {self.device_request.id} by {self.store_clerk}"


class DeviceIMEI(models.Model):
    """
    Tracks individual IMEIs for devices (many IMEIs can map to one Device).
    This is additive and does not replace the existing Device.imei_no field.
    """
    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name='imeis'
    )
    imei_number = models.CharField(max_length=50, unique=True)
    # True => not issued / assignable
    is_available = models.BooleanField(default=True)
    added_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-added_on']

    def __str__(self):
        return f"{self.device.name} - {self.imei_number} ({'available' if self.is_available else 'unavailable'})"

    def mark_unavailable(self):
        """Mark this IMEI as not available (used)."""
        if self.is_available:
            self.is_available = False
            self.save(update_fields=['is_available'])

    def mark_available(self):
        """Mark this IMEI as available again (returned)."""
        if not self.is_available:
            self.is_available = True
            self.save(update_fields=['is_available'])


# --- add these FK fields to existing models (DeviceRequest and IssuanceRecord) ---
# Note: keep your existing DeviceRequest.imei_no CharField intact — we only add a FK.

# in DeviceRequest (add below the existing imei_no CharField or anywhere in the class):
imei_obj = models.ForeignKey(
    'DeviceIMEI',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
    related_name='device_requests'
)

# in IssuanceRecord (add a nullable FK to store which IMEI was issued)
imei = models.ForeignKey(
    'DeviceIMEI',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
    related_name='issuance_records'
)


class DeviceRequest(models.Model):
    device = models.ForeignKey(
        "Device", on_delete=models.CASCADE, related_name="requests"
    )
    imei_no = models.CharField(
        max_length=50, null=True, blank=True)  # existing — keep it
    imei_obj = models.ForeignKey(
        'DeviceIMEI',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='device_requests'
    )
    requestor = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="device_requests"
    )
    client = models.ForeignKey(
        "Client",
        on_delete=models.CASCADE,
        related_name="client_requests",
        null=True,
        blank=True
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="requests"
    )
    country = models.ForeignKey(
        Country, on_delete=models.SET_NULL, null=True, blank=True
    )

    # specify imei_no if applicable during request
    imei_no = models.CharField(max_length=50, null=True, blank=True)  # ✅ NEW
    quantity = models.PositiveIntegerField(default=1)
    reason = models.TextField(blank=True, null=True)
    application_date = models.DateField(default=timezone.now)

    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Waiting Approval', 'Waiting Admin Approval'),
        ('Issued', 'Issued'),
        ('Rejected', 'Rejected'),
        ('Cancelled', 'Cancelled'),
        ('Partially Returned', 'Partially Returned'),
        ('Fully Returned', 'Fully Returned'),
    ]

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='Pending'
    )
    date_requested = models.DateTimeField(auto_now_add=True)
    date_issued = models.DateTimeField(null=True, blank=True)
    returned_quantity = models.PositiveIntegerField(default=0)

    _original_status = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_status = self.status

    def save(self, *args, **kwargs):
        status_changed = self.pk and self.status != self._original_status
        super().save(*args, **kwargs)

        if status_changed:
            subject, message = None, None
            user = self.requestor

            if self.status == 'Rejected':
                subject = "Device Request Rejected"
                message = f"Dear {user.username}, your request for {self.device} has been rejected."
            elif self.status == 'Approved':
                subject = "Device Request Approved"
                message = f"Dear {user.username}, your request for {self.device} has been approved."
            elif self.status == 'Issued':
                subject = "Device Issued"
                message = f"Dear {user.username}, your device {self.device} has been issued."
                if not self.date_issued:
                    self.date_issued = timezone.now()
                    super().save(update_fields=['date_issued'])
            elif self.status == 'Cancelled':
                subject = "Device Request Cancelled"
                message = f"Dear {user.username}, your request for {self.device} has been cancelled."
            elif self.status in ['Partially Returned', 'Fully Returned']:
                subject = "Device Return Confirmation"
                message = (
                    f"Dear {user.username}, your request for {self.device} has been marked as "
                    f"{self.status.lower()} ({self.returned_quantity}/{self.quantity} returned)."
                )

            if subject and message:
                send_mail(
                    subject,
                    message,
                    from_email=None,
                    recipient_list=[user.email],
                    fail_silently=True,
                )

            self._original_status = self.status

    def __str__(self):
        return f"Request for {self.device} by {self.requestor.username}"
    
class SelectedDevice(models.Model):
    request = models.ForeignKey(DeviceRequest, on_delete=models.CASCADE, related_name='selected_devices')
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    selected_by = models.ForeignKey(User, on_delete=models.CASCADE)
    selected_at = models.DateTimeField(auto_now_add=True)


# --- NEW: DeviceSelection model (placed below DeviceRequest) ---
class DeviceSelection(models.Model):
    device_request = models.ForeignKey(
        'DeviceRequest',
        on_delete=models.CASCADE,
        related_name='selections'
    )
    device = models.ForeignKey(
        'Device',
        on_delete=models.CASCADE,
        related_name='selected_for_requests'
    )
    selected_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='device_selections'
    )
    selected_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.device.name} selected for Request {self.device_request.id}"


class IssuanceRecord(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    imei = models.ForeignKey(
        'DeviceIMEI',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='issuance_records'
    )
    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, null=True, blank=True
    )
    logistics_manager = models.ForeignKey(User, on_delete=models.CASCADE)
    issued_at = models.DateTimeField(auto_now_add=True)
    device_request = models.ForeignKey(
        'DeviceRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='issuances'
    )

    def __str__(self):
        return f"{self.device} issued to {self.client.name if self.client else 'N/A'} by {self.logistics_manager.username}"


class ReturnRecord(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    returned_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True)

    def __str__(self):
        return f"{self.device} returned by {self.client.name} on {self.returned_at.strftime('%Y-%m-%d')}"


# Profile model to extend User with branch and country
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    branch = models.ForeignKey(
        Branch, on_delete=models.SET_NULL, null=True, blank=True
    )
    country = models.ForeignKey(
        Country, on_delete=models.SET_NULL, null=True, blank=True
    )
    address = models.CharField(max_length=255, blank=True)
    phone_no = models.CharField(max_length=50, blank=True)

    def get_info(self):
        return {
            "branch": self.branch.name if self.branch else "",
            "country": self.country.name if self.country else "",
            "email": self.user.email,
            "username": self.user.username,
        }

    def __str__(self):
        return f"{self.user.username}'s profile"


# --- END IoT/Client/OEM/Branch/Country Models ---
