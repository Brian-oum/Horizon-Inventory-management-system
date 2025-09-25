from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.mail import send_mail
from django.core.exceptions import ValidationError

# --- Category Model ---
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    def __str__(self):
        return self.name

# --- Inventory Item ---
class InventoryItem(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In Stock', 'In Stock'),
        ('Issued', 'Issued'),
        ('Returned', 'Returned'),
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

    name = models.CharField(max_length=255)
    serial_number = models.CharField(max_length=255, unique=True, blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, blank=True, null=True, related_name='inventory_items')
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default="Serviceable")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='In Stock')
    expiration_date = models.DateField(null=True, blank=True)
    quantity_total = models.PositiveIntegerField(default=0)
    quantity_issued = models.PositiveIntegerField(default=0)
    quantity_returned = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='inventory_created_by')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    box = models.ForeignKey("Box", on_delete=models.SET_NULL, null=True, blank=True, related_name='inventory_items')  # << Added: enforce box selection order
    
    
    def quantity_remaining(self):
        return self.quantity_total - self.quantity_issued
    
    def __str__(self):
        return f"{self.name} (S/N: {self.serial_number or 'N/A'})"
    

    def is_expired(self):
        return self.expiration_date and self.expiration_date < timezone.now().date()

    def quantity_remaining(self):
        return self.quantity_total - self.quantity_issued

# --- Item Request ---
class ItemRequest(models.Model):
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    quantity = models.PositiveIntegerField(default=1)
    reason = models.TextField(blank=True, null=True)
    application_date = models.DateField(default=timezone.now)
    requestor = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=[('Pending','Pending'),('Approved','Approved'),('Issued','Issued'),('Rejected','Rejected')], default='Pending')

    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Issued', 'Issued'),
        ('Rejected', 'Rejected'),
        ('Cancelled', 'Cancelled'),
        ('Partially Returned', 'Partially Returned'),
        ('Fully Returned', 'Fully Returned'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
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
            subject = None
            message = None
            user = self.requestor

            if self.status == 'Rejected':
                subject = "Item Request Rejected"
                message = f"Dear {user.first_name or user.username},\n\nYour request for item \"{self.item.name}\" has been rejected."
            elif self.status == 'Approved':
                subject = "Item Request Approved"
                message = f"Dear {user.first_name or user.username},\n\nYour request for item \"{self.item.name}\" has been approved."
            elif self.status == 'Issued':
                subject = "Item Issued"
                message = f"Dear {user.first_name or user.username},\n\nYour item \"{self.item.name}\" has been issued."
                if not self.date_issued:
                    self.date_issued = timezone.now()
                    super().save(update_fields=['date_issued'])
            elif self.status == 'Cancelled':
                subject = "Item Request Cancelled"
                message = f"Dear {user.first_name or user.username},\n\nYour item request for \"{self.item.name}\" has been cancelled."
            elif self.status in ['Partially Returned', 'Fully Returned']:
                subject = f"Item Return Confirmation - {self.item.name}"
                message = f"Dear {user.first_name or user.username},\n\nThe item \"{self.item.name}\" (Quantity: {self.returned_quantity}/{self.quantity}) has been marked as {self.status.lower()}."

            if subject and message:
                send_mail(subject, message, from_email=None, recipient_list=[user.email], fail_silently=False)

            self._original_status = self.status

    def __str__(self):
        return f"Request for {self.item.name} by {self.requestor.username}"

    def quantity_to_be_returned(self):
        return self.quantity - self.returned_quantity
    
    def clean(self):
        # Prevent over-requesting
        if self.quantity > self.item.quantity_remaining():
            raise ValidationError(f"Only {self.item.quantity_remaining()} units of {self.item.name} are available.")

        # Check sequential box selection
        if self.item.box and not self.item.box.is_selectable():
            raise ValidationError(f"Cannot request items from Box {self.item.box.number} until all earlier boxes are completed.")

# --- Stock Transaction ---
class StockTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('Issue', 'Issue'),
        ('Adjustment', 'Adjustment'),
        ('Return', 'Return'),
        ('Receive', 'Receive'),
    ]

    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='stock_transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    quantity = models.IntegerField()
    item_request = models.ForeignKey(ItemRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_transactions')
    issued_to = models.CharField(max_length=255, blank=True, null=True)
    reason = models.TextField(blank=True, null=True)
    transaction_date = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='recorded_transactions')

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.transaction_type == 'Issue':
            self.item.quantity_issued += self.quantity
        elif self.transaction_type == 'Return':
            self.item.quantity_returned += self.quantity
            self.item.quantity_issued -= self.quantity
        elif self.transaction_type in ['Receive', 'Adjustment']:
            self.item.quantity_total += self.quantity
        self.item.save(update_fields=['quantity_total', 'quantity_issued', 'quantity_returned'])

    def __str__(self):
        action = "added" if self.quantity > 0 else "removed"
        recorded_by_name = self.recorded_by.username if self.recorded_by else "N/A"
        return f"{self.item.name} - {self.transaction_type}: {abs(self.quantity)} ({action}) by {recorded_by_name} on {self.transaction_date.strftime('%Y-%m-%d')}"

    class Meta:
        ordering = ['-transaction_date']
        permissions = [
            ("can_issue_item", "Can issue inventory items"),
            ("can_adjust_stock", "Can adjust inventory stock"),
            ("can_receive_stock", "Can receive new stock into inventory"),
        ]

# --- Offices, Suppliers, Boxes, Devices, Clients ---
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

from django.db import models
from django.core.exceptions import ValidationError

class Box(models.Model):
    number = models.PositiveIntegerField(unique=True, help_text="Sequential number of the box")
    status = models.CharField(
        max_length=20,
        choices=[
            ('available', 'Available'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
        ],
        default='available'
    )

    def is_selectable(self):
        """
        A box is selectable only if all lower-numbered boxes are completed.
        Returns True if this box can be selected.
        """
        previous_boxes = Box.objects.filter(number__lt=self.number)
        return not previous_boxes.exclude(status='completed').exists()

    def clean(self):
        """
        Prevent starting this box ('in_progress') if earlier boxes are not completed.
        """
        if self.status == 'in_progress':
            previous_unfinished = Box.objects.filter(number__lt=self.number).exclude(status='completed').exists()
            if previous_unfinished:
                raise ValidationError("Complete earlier boxes first.")

    def save(self, *args, **kwargs):
        # Enforce validation before saving
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Box {self.number} ({self.status})"

class Device(models.Model):
    box = models.ForeignKey(Box, on_delete=models.CASCADE, related_name='devices')
    product_id = models.CharField(max_length=30, unique=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, to_field='supplier_id', related_name='devices')
    imei_no = models.CharField(max_length=50, unique=True)
    serial_no = models.CharField(max_length=50, unique=True, null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, blank=True, null=True, related_name='devices')
    description = models.TextField(blank=True)
    selling_price_usd = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    selling_price_ksh = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    selling_price_tsh = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=[('available','Available'),('issued','Issued'),('returned','Returned'),('faulty','Faulty')], default='available')
    def __str__(self):
        return f"Device IMEI:{self.imei_no} Box:{self.box.number} Status:{self.status}"

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

# --- Requestor/Profile and Device Requests ---
class Requestor(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="requestor_profile")
    department = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    def __str__(self):
        return self.user.username

class DeviceRequest(models.Model):
    STATUS_CHOICES = [('pending','Pending'),('approved','Approved'),('rejected','Rejected')]
    requestor = models.ForeignKey(Requestor, on_delete=models.CASCADE)
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    requested_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    message = models.TextField(blank=True)

    def clean(self):
        if self.device.status != 'available':
            raise ValidationError("Device is not available for request.")

    def approve(self):
        if self.device.status == 'available':
            self.status = 'approved'
            self.device.status = 'issued'
            self.device.save()
            self.message = "Request approved. Device issued."
            self.save()
        else:
            self.status = 'rejected'
            self.message = "Device not available."
            self.save()

    def reject(self, reason="Device not available."):
        self.status = 'rejected'
        self.message = reason
        self.save()

    def __str__(self):
        return f"Request by {self.requestor} for {self.device} ({self.status})"
