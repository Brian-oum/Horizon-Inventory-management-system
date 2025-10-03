from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.mail import send_mail

# --- BEGIN IoT/Client/Supplier Models ---


class Office(models.Model):
    address = models.CharField(max_length=255)

    def __str__(self):
        return self.address


class Supplier(models.Model):
    supplier_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    contact_person = models.CharField(max_length=100, blank=True)
    phone_email = models.CharField(max_length=100, blank=True)
    address = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.name} ({self.supplier_id})"


class PurchaseOrder(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    order_date = models.DateField()
    expected_delivery = models.DateField()
    status = models.CharField(max_length=50)

    def __str__(self):
        return f"PO #{self.id} - {self.supplier.name}"


class Client(models.Model):
    name = models.CharField(max_length=255)
    phone_no = models.CharField(max_length=50)
    email = models.EmailField()
    address = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class Device(models.Model):
    name = models.CharField(max_length=255, blank=True)  # Device name
    total_quantity = models.PositiveIntegerField(default=1)
    product_id = models.CharField(max_length=30)
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        to_field='supplier_id',
        related_name='devices'
    )
    imei_no = models.CharField(max_length=50, unique=True)
    serial_no = models.CharField(
        max_length=50, unique=True, null=True, blank=True)
    category = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    selling_price_usd = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True)
    selling_price_ksh = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True)
    selling_price_tsh = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=(
            ('available', 'Available'),
            ('issued', 'Issued'),
            ('returned', 'Returned'),
            ('faulty', 'Faulty'),
        ),
        default='available'
    )

    def __str__(self):
        return f"Device IMEI:{self.imei_no} Status:{self.status}"


class DeviceRequest(models.Model):
    device = models.ForeignKey(
        "Device",
        on_delete=models.CASCADE,
        related_name="requests"
    )
    requestor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="device_requests"
    )
    client = models.ForeignKey(
        "Client",
        on_delete=models.CASCADE,
        related_name="client_requests",
        null=True,
        blank=True
    )
    branch = models.ForeignKey("Branch", on_delete=models.CASCADE, related_name="requests")
    quantity = models.PositiveIntegerField(default=1)
    reason = models.TextField(blank=True, null=True)
    application_date = models.DateField(default=timezone.now)
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
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


class IssuanceRecord(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)

    # CHANGE: Allow null client if the IssuanceRecord is used for internal issues
    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, null=True, blank=True)

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
        return f"{self.device} issued to {self.client.name} by {self.logistics_manager.username}"


class ReturnRecord(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    returned_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True)

    def __str__(self):
        return f"{self.device} returned by {self.client.name} on {self.returned_at.strftime('%Y-%m-%d')}"

class Branch(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

# --- END IoT/Client/Supplier Models ---
