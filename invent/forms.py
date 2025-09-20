from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db.models import F  # Import F expression for queryset filtering
from .models import ItemRequest, InventoryItem, StockTransaction
from .models import Device, Supplier, Box


class CustomCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']


class ItemRequestForm(forms.ModelForm):
    item = forms.ModelChoiceField(
        queryset=InventoryItem.objects.all().order_by('name'),
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

        if item and quantity:
            available = item.quantity_remaining()
            if quantity > available:
                raise forms.ValidationError(
                    f"You cannot request {quantity} units of '{item.name}' — only {available} in stock."
                )

        return cleaned_data


class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItem
        # UPDATED FIELDS HERE: Added 'serial_number' and 'condition'
        fields = ['name', 'category', 'condition', 'status', 'serial_number',
                  'quantity_total', 'quantity_issued', 'quantity_returned']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Item Name'}),
            # Added widget for serial_number
            'serial_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Serial Number'}),
            'category': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Category'}),
            # Added widget for condition
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
            self.add_error(
                'quantity_issued', 'Quantity issued cannot be greater than total quantity.')

        if quantity_returned is not None and quantity_issued is not None and quantity_returned > quantity_issued:
            self.add_error(
                'quantity_returned', 'Quantity returned cannot be greater than quantity issued.')

        return cleaned_data


class IssueItemForm(forms.Form):
    item = forms.ModelChoiceField(
        queryset=InventoryItem.objects.filter(
            quantity_total__gt=0).order_by('name'),
        empty_label="Select an item",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(
            attrs={'class': 'form-control', 'placeholder': 'Quantity to issue'})
    )
    issued_to = forms.CharField(
        max_length=255,
        widget=forms.TextInput(
            attrs={'class': 'form-control', 'placeholder': 'Recipient (e.g., Department, Name)'})
    )

    def clean(self):
        cleaned_data = super().clean()
        item = cleaned_data.get('item')
        quantity = cleaned_data.get('quantity')

        if item and quantity:
            if item.quantity_remaining() < quantity:
                raise forms.ValidationError(
                    f"Not enough stock of {item.name} available. Only {item.quantity_remaining()} units currently available for issue."
                )
        return cleaned_data


class AdjustStockForm(forms.Form):
    item = forms.ModelChoiceField(
        queryset=InventoryItem.objects.all().order_by('name'),
        empty_label="Select an item",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    adjustment_quantity = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 'placeholder': 'Quantity to add/remove (e.g., 5 or -3)'}),
        help_text="Enter a positive number to add stock, or a negative number to remove stock."
    )
    reason = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': 'Reason for adjustment (e.g., Damage, Audit, New Stock Arrival)'})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Optional notes'})
    )

    def clean(self):
        cleaned_data = super().clean()
        item = cleaned_data.get('item')
        adjustment_quantity = cleaned_data.get('adjustment_quantity')

        if item and adjustment_quantity is not None:
            if (item.quantity_total + adjustment_quantity) < 0:
                self.add_error(
                    'adjustment_quantity',  # Attach error to specific field
                    f"Adjustment would result in negative total stock. Current total: {item.quantity_total}."
                )
        return cleaned_data


# --- NEW FORMS FOR RETURN LOGIC ---

class ReturnItemForm(forms.Form):
    """
    Form for processing the return of items for a specific ItemRequest.
    The item_request instance is passed during initialization to set max_value.
    """
    returned_quantity = forms.IntegerField(
        min_value=1,
        label="Quantity to Return",
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text="Enter the number of items being returned for this request."
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        required=False,
        label="Reason for Return",
        help_text="Optional: Why are these items being returned? (e.g., Damaged, No longer needed)"
    )

    def __init__(self, *args, **kwargs):
        # Pop the item_request instance from kwargs before calling super()
        self.item_request = kwargs.pop('item_request', None)
        super().__init__(*args, **kwargs)

        if self.item_request:
            max_return_quantity = self.item_request.quantity_to_be_returned()
            self.fields['returned_quantity'].max_value = max_return_quantity
            self.fields['returned_quantity'].help_text += f" (Max: {max_return_quantity})"
            if max_return_quantity <= 0:
                self.fields['returned_quantity'].widget.attrs['readonly'] = True
                self.fields['returned_quantity'].help_text = "No more items to return for this request."
                # Set initial to 0 if no more to return
                self.fields['returned_quantity'].initial = 0

    def clean_returned_quantity(self):
        returned_quantity = self.cleaned_data['returned_quantity']
        if self.item_request:
            max_return_quantity = self.item_request.quantity_to_be_returned()
            if returned_quantity > max_return_quantity:
                raise forms.ValidationError(
                    f"You cannot return more than the remaining issued quantity ({max_return_quantity})."
                )
        return returned_quantity


class SelectRequestForReturnForm(forms.Form):
    """
    Form to select an ItemRequest that has been issued and is eligible for return.
    """
    item_request = forms.ModelChoiceField(
        # Filter for requests that are 'Issued' and have a quantity_to_be_returned > 0
        queryset=ItemRequest.objects.filter(
            status='Issued'
        ).exclude(
            # Exclude if original quantity <= returned quantity
            quantity__lte=F('returned_quantity')
        ).order_by('date_issued'),  # Order by issue date or request date
        label="Select Issued Request",
        empty_label="--- Select an Issued Request ---",
        widget=forms.Select(attrs={'class': 'form-control'})
    )

class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['supplier_id','name', 'contact_person', 'phone_email', 'address']
        widgets = {
            'supplier_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Supplier ID'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Supplier Name'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contact Person'}),
            'phone_email': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone or Email'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Address'}),
        }

class BoxForm(forms.ModelForm):
    class Meta:
        model = Box
        fields = ['number', 'status']
        widgets = {
            'number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Box Number'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
        }

class DeviceForm(forms.ModelForm):
    class Meta:
        model = Device
        fields = [
            'box',
            'product_id',
            'supplier',
            'imei_no',
            'serial_no',
            'category',
            'description',
            'selling_price_usd',
            'selling_price_ksh',
            'selling_price_tsh',
            'status',
        ]
        widgets = {
            'box': forms.Select(attrs={'class': 'form-select'}),
            'product_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Product ID'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'imei_no': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'IMEI Number'}),
            'serial_no': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Serial Number'}),
            'category': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Category'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Description', 'rows': 2}),
            'selling_price_usd': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Price in USD'}),
            'selling_price_ksh': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Price in KSH'}),
            'selling_price_tsh': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Price in TSH'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }