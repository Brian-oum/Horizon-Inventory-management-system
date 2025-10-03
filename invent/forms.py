from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db.models import F  # Import F expression for queryset filtering
from .models import Device, OEM
from .models import DeviceRequest, Client, Branch


class CustomCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']



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


# --- NEW FORMS FOR RETURN LOGIC ---

class OEMForm(forms.ModelForm):
    class Meta:
        model = OEM
        fields = ['oem_id', 'name',
                  'contact_person', 'phone_email', 'address']
        widgets = {
            'oem_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'OEM ID'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'OEM Name'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contact Person'}),
            'phone_email': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone or Email'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Address'}),
        }


class DeviceForm(forms.ModelForm):
    class Meta:
        model = Device
        fields = [
            'name',
            'total_quantity',
            'product_id',
            'oem',
            'imei_no',
            'serial_no',
            'category',
            'description',
            'selling_price',
            'currency',
            'status',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Name'}),
            'total_quantity': forms.NumberInput(attrs={'min': 1}),
            'product_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Product ID'}),
            'oem': forms.Select(attrs={'class': 'form-select'}),
            'imei_no': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'IMEI Number'}),
            'serial_no': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Serial Number'}),
            'category': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Category'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Description', 'rows': 2}),
            'selling_price': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Selling Price'}),
            'currency': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }


class DeviceRequestForm(forms.ModelForm):
    client_name = forms.CharField(
        max_length=255, required=True, label="Client Name")
    client_phone = forms.CharField(
        max_length=50, required=True, label="Client Phone")
    client_email = forms.EmailField(required=True, label="Client Email")
    client_address = forms.CharField(
        max_length=255, required=True, label="Client Address")
    branch = forms.ModelChoiceField(
        queryset=Branch.objects.all(),
        required=True,
        label="Branch",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    class Meta:
        model = DeviceRequest
        fields = ['device', 'quantity', 'reason']  # client fields are extra

    def save(self, commit=True, requestor=None):
        # ✅ Create the client first
        client = Client.objects.create(
            name=self.cleaned_data['client_name'],
            phone_no=self.cleaned_data['client_phone'],
            email=self.cleaned_data['client_email'],
            address=self.cleaned_data['client_address'],
        )

        # ✅ Link client + requestor to the request
        device_request = super().save(commit=False)
        if requestor:
            device_request.requestor = requestor
        device_request.client = client

        if commit:
            device_request.save()
        return device_request
