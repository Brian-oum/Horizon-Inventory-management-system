# models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.mail import send_mail


class InventoryItem(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In Stock', 'In Stock'),
        ('Issued', 'Issued'),
        # This can be used if an entire *type* of item is deemed 'returned' for some reason,
        ('Returned', 'Returned'),
        # or if you track individual serial numbers and this field applies to each serial.
        # For aggregate quantities, 'In Stock', 'Low Stock', 'Out of Stock' are more common.
        ('Low Stock', 'Low Stock'),
        ('Out of Stock', 'Out of Stock'),
    ]

    CONDITION_CHOICES = [
        ("Serviceable", "Serviceable"),
        ("Not Serviceable", "Not Serviceable"),
        ("Not working", "Not working"),
        ("Good", "Good"),
        ("Fair", "Fair"),
        ("Poor", "Poor"),
    ]

    name = models.CharField(
        max_length=255, help_text="e.g., Dell Optiplex 7010 (from Asset Description)")
    serial_number = models.CharField(
        max_length=255, unique=True, blank=True, null=True,
        help_text="Unique serial number of the asset (from Serial Number in CSV)"
    )
    category = models.CharField(
        max_length=100, blank=True,
        help_text="e.g., Printer, CPU, Monitor (from Asset Category-Minor)"
    )
    condition = models.CharField(
        max_length=20, choices=CONDITION_CHOICES, default="Serviceable",
        help_text="Current condition of the asset (from Condition in CSV)"
    )

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='In Stock')
    expiration_date = models.DateField(null=True, blank=True)
    quantity_total = models.PositiveIntegerField(default=0)
    quantity_issued = models.PositiveIntegerField(default=0)
    # This field is for *aggregate* returns of this item type.
    quantity_returned = models.PositiveIntegerField(default=0)
    # Actual returns are handled via StockTransaction and ItemRequest.

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='inventory_created_by')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        # If serial_number is truly unique per physical item, then quantity_total etc. would be 1 for each object.
        # If it's a type of item, then serial_number should not be unique and quantity_total would be > 1.
        # Assuming for now it's a type of item with an optional unique serial for individual units if desired.
        # This string representation is better for unique items.
        return f"{self.name} (S/N: {self.serial_number or 'N/A'})"
        # If it's a type, it might be just `self.name`.

    def is_expired(self):
        return self.expiration_date and self.expiration_date < timezone.now().date()

    def quantity_remaining(self):
        """Calculates the quantity currently available for new issues."""
        return self.quantity_total - self.quantity_issued


class ItemRequest(models.Model):
    item = models.ForeignKey('InventoryItem', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    quantity = models.PositiveIntegerField(default=1)  # Quantity requested
    reason = models.TextField(blank=True, null=True)
    application_date = models.DateField(default=timezone.now)
    requestor = models.ForeignKey(User, on_delete=models.CASCADE)

    # UPDATED STATUS CHOICES for ItemRequest
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Issued', 'Issued'),  # Item has been issued (fully or partially)
        ('Rejected', 'Rejected'),
        ('Cancelled', 'Cancelled'),
        # Some but not all issued quantity returned
        ('Partially Returned', 'Partially Returned'),
        # All issued quantity for this request has been returned
        ('Fully Returned', 'Fully Returned'),
    ]
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='Pending')  # Increased max_length

    date_requested = models.DateTimeField(auto_now_add=True)
    # To track when it was actually issued
    date_issued = models.DateTimeField(null=True, blank=True)

    # NEW FIELD: To track how much of this specific request has been returned
    returned_quantity = models.PositiveIntegerField(default=0)

    _original_status = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_status = self.status

    def save(self, *args, **kwargs):
        status_changed = self.pk and self.status != self._original_status
        super().save(*args, **kwargs)

        if status_changed:
            subject = None
            message = None
            user = self.requestor

            if self.status == 'Rejected':
                subject = "Item Request Rejected"
                message = (
                    f"Dear {user.first_name or user.username},\n\n"
                    f"Your request for item \"{self.item.name}\" has been rejected.\n"
                    f"If you believe this is an error, please contact the store clerk.\n\n"
                    f"Thank you,\nInventory Management System"
                )
            elif self.status == 'Approved':
                subject = "Item Request Approved"
                message = (
                    f"Dear {user.first_name or user.username},\n\n"
                    f"Your request for item \"{self.item.name}\" has been approved.\n"
                    f"You will be notified once the item is issued.\n\n"
                    f"Thank you,\nInventory Management System"
                )
            elif self.status == 'Issued':
                subject = "Item Issued"
                message = (
                    f"Dear {user.first_name or user.username},\n\n"
                    f"Your item \"{self.item.name}\" has been issued successfully.\n"
                    f"Kindly pick up you item.\n\n"
                    f"Thank you,\nInventory Management System"
                )
                if not self.date_issued:  # Set date_issued only once
                    self.date_issued = timezone.now()
                    # Save date_issued immediately
                    super().save(update_fields=['date_issued'])
            elif self.status == 'Cancelled':
                subject = "Item Request Cancelled"
                message = (
                    f"Dear {user.first_name or user.username},\n\n"
                    f"Your item request for \"{self.item.name}\" has been cancelled.\n\n"
                    f"Regards,\nInventory Management System"
                )
            elif self.status == 'Partially Returned' or self.status == 'Fully Returned':
                subject = f"Item Return Confirmation - Request for {self.item.name}"
                message = (
                    f"Dear {user.first_name or user.username},\n\n"
                    f"The item \"{self.item.name}\" (Quantity: {self.returned_quantity}/{self.quantity}) from your request "
                    f"has been marked as {self.status.lower()} in the system.\n\n"
                    f"Thank you,\nInventory Management System"
                )

            if subject and message:
                send_mail(
                    subject,
                    message,
                    from_email=None,  # Uses DEFAULT_FROM_EMAIL from settings.py
                    recipient_list=[user.email],
                    fail_silently=False,
                )

            self._original_status = self.status  # Update tracker

    def __str__(self):
        requestor_name = self.requestor.username if self.requestor else "N/A"
        return f"Request for {self.item.name} by {requestor_name}"

    def quantity_to_be_returned(self):
        """Calculates the quantity that was issued and is not yet returned for this request."""
        return self.quantity - self.returned_quantity


class StockTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('Issue', 'Issue'),
        ('Adjustment', 'Adjustment'),
        ('Return', 'Return'),
        ('Receive', 'Receive'),
    ]

    item = models.ForeignKey(
        InventoryItem, on_delete=models.CASCADE, related_name='stock_transactions')
    transaction_type = models.CharField(
        max_length=20, choices=TRANSACTION_TYPES)
    # Use IntegerField as returns will be negative if you track direction,
    quantity = models.IntegerField()
    # but for returns we'll use positive number and type='Return'

    # Associate transaction with a specific ItemRequest if it's an 'Issue' or 'Return'
    item_request = models.ForeignKey(
        ItemRequest, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_transactions',
        help_text="Link to the original item request if applicable (for Issue/Return transactions)"
    )

    issued_to = models.CharField(
        max_length=255, blank=True, null=True, help_text="Recipient for 'Issue' transactions")
    reason = models.TextField(
        blank=True, null=True, help_text="Reason for 'Adjustment' or 'Return' transactions")

    transaction_date = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='recorded_transactions')


def __str__(self):
    action = "added" if self.quantity > 0 else "removed"
    recorded_by_name = self.recorded_by.username if self.recorded_by else "N/A"
    date_str = self.transaction_date.strftime(
        '%Y-%m-%d') if self.transaction_date else "Unknown date"
    # Adjusting the __str__ to be more descriptive for returns
    if self.transaction_type == 'Return':
        return f"{self.item.name} - Returned: {self.quantity} by {recorded_by_name} on {date_str}"
    else:
        return f"{self.item.name} - {self.transaction_type}: {abs(self.quantity)} ({action}) by {recorded_by_name} on {date_str}"


class Meta:
    ordering = ['-transaction_date']
    permissions = [
        ("can_issue_item", "Can issue inventory items"),
        ("can_adjust_stock", "Can adjust inventory stock"),
        ("can_receive_stock", "Can receive new stock into inventory"),
    ]

# --- BEGIN IoT/Client/Supplier Models ---


class Office(models.Model):
    address = models.CharField(max_length=255)

    def __str__(self):
        return self.address


class Supplier(models.Model):
    # Or IntegerField if numbers
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


class Device(models.Model):
    name = models.CharField(max_length=255, blank=True)  # Device name
    total_quantity = models.PositiveIntegerField(
        default=1)  # Total number of this device
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

 # make sure Client is imported


class DeviceRequest(models.Model):
    device = models.ForeignKey(
        "Device",  # 👈 reference by string to avoid circular import
        on_delete=models.CASCADE,
        related_name="requests"
    )
    requestor = models.ForeignKey(
        User,  # still linked to the User model
        on_delete=models.CASCADE,
        related_name="device_requests"
    )
    client = models.ForeignKey(
        "Client",  # 👈 reference by string to avoid circular import
        on_delete=models.CASCADE,
        related_name="client_requests",
        null=True,
        blank=True
    )

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


class Client(models.Model):
    name = models.CharField(max_length=255)
    phone_no = models.CharField(max_length=50)
    email = models.EmailField()
    address = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class IssuanceRecord(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    logistics_manager = models.ForeignKey(User, on_delete=models.CASCADE)
    issued_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.device} issued to {self.client.name} by {self.logistics_manager.username}"


class ReturnRecord(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    returned_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True)

    def __str__(self):
        return f"{self.device} returned by {self.client.name} on {self.returned_at.strftime('%Y-%m-%d')}"
# --- END IoT/Box/Client/Supplier Models ---
