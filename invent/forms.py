from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db.models import F
from .models import (
    ItemRequest, InventoryItem, StockTransaction, Box,
    Device, DeviceRequest, Requestor, Supplier
)

# ----------------------
# Helper function for sequential box validation
# ----------------------
def validate_sequential_boxes(item):
    """
    Raises ValidationError if the item belongs to a box
    that cannot yet be requested due to unfinished previous boxes.
    """
    if not item or not hasattr(item, 'box') or not item.box:
        return
    try:
        current_box_number = int(item.box.number)
        earlier_unfinished = Box.objects.filter(
            number__lt=current_box_number
        ).exclude(status='completed').exists()
        if earlier_unfinished:
            raise forms.ValidationError(
                f"You cannot request items from Box {item.box.number} until all earlier boxes are completed."
            )
    except ValueError:
        # If box number is not numeric, skip the check
        pass


# ----------------------
# User Registration Form
# ----------------------
class CustomCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']


# ----------------------
# Inventory Item Form
# ----------------------
class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = [
            'name', 'category', 'condition', 'status', 'serial_number',
            'quantity_total', 'quantity_issued', 'quantity_returned'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Item Name'}),
            'serial_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Serial Number'}),
            'category': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Category'}),
            'condition': forms.Select(attrs={'class': 'form-select'}, choices=InventoryItem.CONDITION_CHOICES),
            'status': forms.Select(attrs={'class': 'form-select'}, choices=InventoryItem.STATUS_CHOICES),
            'quantity_total': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'quantity_issued': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'quantity_returned': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
        }

    def clean(self):
        cleaned_data = super().clean()
        quantity_total = cleaned_data.get('quantity_total')
        quantity_issued = cleaned_data.get('quantity_issued')
        quantity_returned = cleaned_data.get('quantity_returned')

        if quantity_issued is not None and quantity_total is not None and quantity_issued > quantity_total:
            self.add_error('quantity_issued', 'Quantity issued cannot be greater than total quantity.')

        if quantity_returned is not None and quantity_issued is not None and quantity_returned > quantity_issued:
            self.add_error('quantity_returned', 'Quantity returned cannot be greater than quantity issued.')

        return cleaned_data


# ----------------------
# Item Request Form
# ----------------------
class ItemRequestForm(forms.ModelForm):
    item = forms.ModelChoiceField(
        queryset=InventoryItem.objects.filter(
            box__status__in=['available', 'in_progress']
        ).order_by('name'),
        label="Select an Item",
        empty_label="-- Select an Item --",
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    class Meta:
        model = ItemRequest
        fields = ['item', 'quantity', 'reason']
        widgets = {
            'reason': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        }

    def clean(self):
        cleaned_data = super().clean()
        item = cleaned_data.get('item')
        quantity = cleaned_data.get('quantity')

        if item:
            # ✅ Use helper to validate box sequence
            validate_sequential_boxes(item)

        if item and quantity:
            available = item.quantity_remaining()
            if quantity > available:
                raise forms.ValidationError(
                    f"You cannot request {quantity} units of '{item.name}' — only {available} available."
                )

        return cleaned_data


# ----------------------
# Issue Item Form
# ----------------------
class IssueItemForm(forms.Form):
    item = forms.ModelChoiceField(
        queryset=InventoryItem.objects.filter(quantity_total__gt=0).order_by('name'),
        empty_label="Select an item",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Quantity to issue'})
    )
    issued_to = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Recipient (e.g., Department, Name)'})
    )

    def clean(self):
        cleaned_data = super().clean()
        item = cleaned_data.get('item')
        quantity = cleaned_data.get('quantity')

        if item and quantity and item.quantity_remaining() < quantity:
            raise forms.ValidationError(
                f"Not enough stock of {item.name} available. Only {item.quantity_remaining()} units currently available."
            )
        return cleaned_data


# ----------------------
# Adjust Stock Form
# ----------------------
class AdjustStockForm(forms.Form):
    item = forms.ModelChoiceField(
        queryset=InventoryItem.objects.all().order_by('name'),
        empty_label="Select an item",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    adjustment_quantity = forms.IntegerField(
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Quantity to add/remove'}),
        help_text="Enter a positive number to add stock, or a negative number to remove stock."
    )
    reason = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Reason for adjustment'})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Optional notes'})
    )

    def clean(self):
        cleaned_data = super().clean()
        item = cleaned_data.get('item')
        adjustment_quantity = cleaned_data.get('adjustment_quantity')

        if item and adjustment_quantity is not None and (item.quantity_total + adjustment_quantity) < 0:
            self.add_error(
                'adjustment_quantity',
                f"Adjustment would result in negative total stock. Current total: {item.quantity_total}."
            )
        return cleaned_data


# ----------------------
# Return Item Form
# ----------------------
class ReturnItemForm(forms.Form):
    returned_quantity = forms.IntegerField(
        min_value=1,
        label="Quantity to Return",
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        required=False,
        label="Reason for Return"
    )

    def __init__(self, *args, **kwargs):
        self.item_request = kwargs.pop('item_request', None)
        super().__init__(*args, **kwargs)

        if self.item_request:
            max_return_quantity = self.item_request.quantity_to_be_returned()
            self.fields['returned_quantity'].max_value = max_return_quantity
            self.fields['returned_quantity'].help_text = f"Max: {max_return_quantity}"
            if max_return_quantity <= 0:
                self.fields['returned_quantity'].widget.attrs['readonly'] = True
                self.fields['returned_quantity'].initial = 0
                self.fields['returned_quantity'].help_text = "No more items to return for this request."

    def clean_returned_quantity(self):
        returned_quantity = self.cleaned_data['returned_quantity']
        if self.item_request and returned_quantity > self.item_request.quantity_to_be_returned():
            raise forms.ValidationError(
                f"You cannot return more than the remaining issued quantity ({self.item_request.quantity_to_be_returned()})."
            )
        return returned_quantity


# ----------------------
# Select Request for Return Form
# ----------------------
class SelectRequestForReturnForm(forms.Form):
    item_request = forms.ModelChoiceField(
        queryset=ItemRequest.objects.filter(status='Issued').exclude(
            quantity__lte=F('returned_quantity')
        ).order_by('date_issued'),
        label="Select Issued Request",
        empty_label="--- Select an Issued Request ---",
        widget=forms.Select(attrs={'class': 'form-control'})
    )


# ----------------------
# Device Request Form
# ----------------------
class DeviceRequestForm(forms.ModelForm):
    class Meta:
        model = DeviceRequest
        fields = ['device', 'message']
        widgets = {
            'device': forms.Select(attrs={'class': 'form-control'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean_device(self):
        device = self.cleaned_data['device']
        if device.status != 'available':
            raise forms.ValidationError("Device is not available for request.")
        return device


# ----------------------
# Supplier Form
# ----------------------
class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['supplier_id', 'name', 'contact_person', 'phone_email', 'address']
        widgets = {
            'supplier_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Supplier ID'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Supplier Name'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contact Person'}),
            'phone_email': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone/Email'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Address'}),
        }


# ----------------------
# Box Form
# ----------------------
class BoxForm(forms.ModelForm):
    class Meta:
        model = Box
        fields = ['number', 'status']
        widgets = {
            'number': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Box Number'}),
            'status': forms.Select(attrs={'class': 'form-select'}, choices=Box._meta.get_field('status').choices),
        }


# ----------------------
# Device Form
# ----------------------
class DeviceForm(forms.ModelForm):
    class Meta:
        model = Device
        fields = ['box', 'product_id', 'supplier', 'imei_no', 'serial_no', 'category', 'description', 'selling_price_usd', 'selling_price_ksh', 'selling_price_tsh', 'status']
        widgets = {
            'box': forms.Select(attrs={'class': 'form-control'}),
            'product_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Product ID'}),
            'supplier': forms.Select(attrs={'class': 'form-control'}),
            'imei_no': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'IMEI Number'}),
            'serial_no': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Serial Number'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Description'}),
            'selling_price_usd': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Selling Price USD'}),
            'selling_price_ksh': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Selling Price KSH'}),
            'selling_price_tsh': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Selling Price TSH'}),
            'status': forms.Select(attrs={'class': 'form-select'}, choices=Device._meta.get_field('status').choices),
        }
