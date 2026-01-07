from django.db import models
from django.db.models import Sum, F # Added Sum, F for future aggregation logic
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.mail import send_mail, EmailMessage
from django.conf import settings
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives


# --- Utility Functions (Keep delivery_note function outside of class definitions) ---
def delivery_note(self):
    """Generate and email the PDF delivery note."""
    # 1️⃣ Generate the PDF using your existing function
    from invent.views import delivery_note  # adjust path to wherever the function is
    pdf_path = delivery_note(self)
    # ... (rest of email logic is omitted for brevity)
    
    # 2️⃣ Prepare email recipients
    recipients = []
    if self.requestor.email:
        recipients.append(self.requestor.email)
    if self.client and getattr(self.client, "email", None):
        recipients.append(self.client.email)
    clerks = User.objects.filter(selecteddevice__request=self).distinct()
    recipients += [c.email for c in clerks if c.email]
    admin_users = User.objects.filter(is_superuser=True)
    recipients += [a.email for a in admin_users if a.email]
    recipients = list(set(recipients))
    if not recipients:
        return

    # 3️⃣ Create email
    subject = f"Delivery Note - Device Request #{self.id}"
    body = (
        f"Hello,\n\n"
        f"Attached is the delivery note for Device Request #{self.id}.\n"
        f"Device: {self.device.name}\n"
        f"Client: {self.client.name if self.client else 'N/A'}\n"
        f"Quantity: {self.quantity}\n\n"
        f"Thanks."
    )

    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=None,
        to=recipients,
    )

    # 4️⃣ Attach the PDF
    with open(pdf_path, "rb") as f:
        email.attach(f"DeliveryNote_{self.id}.pdf", f.read(), "application/pdf")

    # 5️⃣ Send
    email.send(fail_silently=False)


# --- BEGIN Model Definitions ---

class Country(models.Model):
    name = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.name

class Branch(models.Model):
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=255)
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True)
    def __str__(self): return f"{self.name}, {self.country.name if self.country else ''}"

class OEM(models.Model):
    name = models.CharField(max_length=100, unique=True)
    contact_person = models.CharField(max_length=100, blank=True)
    phone_email = models.CharField(max_length=100, blank=True)
    address = models.CharField(max_length=255, blank=True)
    def __str__(self): return self.name

class PurchaseOrder(models.Model):
    oem = models.ForeignKey(OEM, on_delete=models.CASCADE, default=1)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    order_date = models.DateField()
    expected_delivery = models.DateField()
    status = models.CharField(max_length=50)
    document = models.FileField(upload_to='purchase_orders/', null=True, blank=True)
    def __str__(self): return f"PO #{self.id} - {self.oem.name}"

class Client(models.Model):
    name = models.CharField(max_length=255)
    phone_no = models.CharField(max_length=50)
    email = models.EmailField()
    address = models.CharField(max_length=255)
    def __str__(self): return self.name


# --- UNIQUE INSTANCE TRACKER ---
class DeviceIMEI(models.Model):
    """Tracks individual unique physical devices of a product type (Device)."""
    device = models.ForeignKey(
        'Device',
        on_delete=models.CASCADE,
        related_name='imeis'
    )
    # Primary Unique Identifier Field (e.g., IMEI or Serial, used in __str__)
    imei_number = models.CharField(max_length=50, unique=True) 
    
    # Secondary Unique Identifier Fields (to ensure the admin can enter all three)
    serial_no = models.CharField(max_length=50, unique=True, null=True, blank=True)
    mac_address = models.CharField(max_length=50, unique=True, null=True, blank=True)

    is_available = models.BooleanField(default=True)
    added_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-added_on']

    def __str__(self):
        return f"{self.device.name} - {self.imei_number} ({'available' if self.is_available else 'unavailable'})"

    def mark_unavailable(self):
        if self.is_available:
            self.is_available = False
            self.save(update_fields=['is_available'])

    def mark_available(self):
        if not self.is_available:
            self.is_available = True
            self.save(update_fields=['is_available'])


# --- PRODUCT TYPE MODEL ---
class Device(models.Model):
    STATUS_CHOICES = (
        ('available', 'Available'),
        ('issued', 'Issued'),
        ('returned', 'Returned'),
        ('faulty', 'Faulty'),
    )

    name = models.CharField(max_length=255)
    oem = models.ForeignKey(OEM, on_delete=models.SET_NULL, null=True, blank=False, related_name='devices')
    product_id = models.CharField(max_length=30, blank=True)
    
    # CONFLICTING FIELDS REMOVED: total_quantity, quantity_issued, imei_no, serial_no, mac_address
    # These fields are now calculated properties derived from related DeviceIMEI objects
    
    category = models.CharField(max_length=100, blank=True, help_text="e.g. Laptop or Router")
    manufacturer = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')

    class Meta:
        permissions = [
            ("can_issue_item", "Can issue device to client"),
            ("can_return_item", "Can record device returns"),
        ]
        
    @property
    def total_quantity(self):
        """Calculated property: Total number of unique instances (IMEIs) for this product."""
        return self.imeis.count()

    @property
    def quantity_issued(self):
        """Calculated property: Number of instances currently marked as unavailable."""
        return self.imeis.filter(is_available=False).count()

    def quantity_remaining(self):
        """Method: The total available quantity."""
        return self.available_quantity

    @property
    def available_quantity(self):
        """Calculated property: Number of instances currently marked as available."""
        return self.imeis.filter(is_available=True).count()

    def __str__(self):
        return f"{self.name} (Total: {self.total_quantity}, Avail: {self.available_quantity})"


# --- DEVICE REQUEST AND RELATED MODELS ---

class DeviceSelectionGroup(models.Model):
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    )
    device_request = models.ForeignKey('DeviceRequest', on_delete=models.CASCADE, related_name='selection_groups')
    store_clerk = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='device_selection_groups')
    devices = models.ManyToManyField('Device', related_name='selection_groups')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='device_selection_reviews')

    class Meta:
        ordering = ['-created_at']
        permissions = [("can_approve_selection", "Can approve device selection groups")]

    def __str__(self): return f"Selection for Request {self.device_request.id} by {self.store_clerk}"



class DeviceRequest(models.Model):
    device = models.ForeignKey("Device", on_delete=models.CASCADE, related_name="requests")
    requestor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="device_requests")
    client = models.ForeignKey("Client", on_delete=models.CASCADE, related_name="client_requests", null=True, blank=True)
    branch = models.ForeignKey("Branch", on_delete=models.SET_NULL, null=True, blank=True, related_name="requests")
    country = models.ForeignKey("Country", on_delete=models.SET_NULL, null=True, blank=True)
    imei_obj = models.ForeignKey('DeviceIMEI', null=True, blank=True, on_delete=models.SET_NULL, related_name='device_requests')
    quantity = models.PositiveIntegerField(default=1)
    reason = models.TextField(blank=True, null=True)
    application_date = models.DateField(default=timezone.now)
    payment_proof = models.FileField(upload_to="payment_proofs/", null=True, blank=True)

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
            # Mark IMEI unavailable if issued
            if self.status == 'Issued' and self.imei_obj:
                self.imei_obj.mark_unavailable()

            # Set issued date
            if self.status == 'Issued' and not self.date_issued:
                self.date_issued = timezone.now()
                super().save(update_fields=['date_issued'])

            # Optional: send simple notifications
            user = self.requestor
            subject, message = None, None

            if self.status == 'Rejected':
                subject = f"Device Request #{self.id} Rejected"
                message = f"Hello,\n\nYour request for {self.device} has been rejected."
            elif self.status == 'Approved':
                subject = f"Device Request #{self.id} Approved"
                message = f"Hello,\n\nYour request for {self.device} has been approved."
            elif self.status == 'Issued':
                subject = f"Device Request #{self.id} Issued"
                message = f"Hello,\n\nThe device {self.device} has been issued to you."
            elif self.status == 'Cancelled':
                subject = f"Device Request #{self.id} Cancelled"
                message = f"Hello,\n\nYour request for {self.device} has been cancelled."

            if subject and message:
                send_mail(
                    subject,
                    message,
                    from_email=None,
                    recipient_list=[user.email],
                    fail_silently=False
                )

            self._original_status = self.status


class DeviceRequestSelectedIMEI(models.Model):
    device_request = models.ForeignKey(DeviceRequest, on_delete=models.CASCADE, related_name='selected_imeis')
    imei = models.ForeignKey('DeviceIMEI', on_delete=models.CASCADE)
    approved = models.BooleanField(default=False)
    rejected = models.BooleanField(default=False)
    date_selected = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        # NOTE: Updated to use the correct field name imei_number from DeviceIMEI
        return f"Request #{self.device_request.id} - {self.imei.imei_number}" 


class SelectedDevice(models.Model):
    request = models.ForeignKey(DeviceRequest, on_delete=models.CASCADE, related_name='selected_devices')
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    selected_by = models.ForeignKey(User, on_delete=models.CASCADE)
    selected_at = models.DateTimeField(auto_now_add=True)
    imei = models.ForeignKey(DeviceIMEI, on_delete=models.PROTECT, null=True, blank=True)
    approved = models.BooleanField(default=False)
    rejected = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.imei.imei_number} selected for {self.request}"

class DeviceSelection(models.Model):
    device_request = models.ForeignKey('DeviceRequest', on_delete=models.CASCADE, related_name='selections')
    device = models.ForeignKey('Device', on_delete=models.CASCADE, related_name='selected_for_requests')
    selected_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='device_selections')
    selected_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"{self.device.name} selected for Request {self.device_request.id}"


class IssuanceRecord(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    # FK ADDED: Links the issuance record to the specific physical item (DeviceIMEI)
    imei = models.ForeignKey(
        'DeviceIMEI',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='issuance_records'
    )
    client = models.ForeignKey(Client, on_delete=models.CASCADE, null=True, blank=True)
    logistics_manager = models.ForeignKey(User, on_delete=models.CASCADE)
    issued_at = models.DateTimeField(auto_now_add=True)
    imei_obj = models.ForeignKey('DeviceIMEI', null=True, blank=True, on_delete=models.SET_NULL)
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


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True)
    address = models.CharField(max_length=255, blank=True)
    phone_no = models.CharField(max_length=50, blank=True)

    def get_info(self):
        return {
            "branch": self.branch.name if self.branch else "",
            "country": self.country.name if self.country else "",
            "email": self.user.email,
            "username": self.user.username,
        }

    def __str__(self): return f"{self.user.username}'s profile"

class DeviceReports(models.Model):
    branch = models.OneToOneField('Branch', on_delete=models.CASCADE)

    total_requests = models.IntegerField(default=0)
    pending_requests = models.IntegerField(default=0)
    approved_requests = models.IntegerField(default=0)
    issued_requests = models.IntegerField(default=0)
    rejected_requests = models.IntegerField(default=0)
    fully_returned_requests = models.IntegerField(default=0)
    partially_returned_requests = models.IntegerField(default=0)
    total_returned_quantity = models.IntegerField(default=0)

    class Meta:
        verbose_name = "Device Request Report"
        verbose_name_plural = "Device Request Reports"

    def __str__(self):
        return self.branch.name