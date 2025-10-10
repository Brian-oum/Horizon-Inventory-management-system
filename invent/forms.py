from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Profile
from .models import Profile, Country
from django.db.models import F  # Import F expression for queryset filtering
from .models import Device, OEM, PurchaseOrder
from .models import DeviceRequest, Client, Branch


class CustomCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    country = forms.ModelChoiceField(
        queryset=Country.objects.all(),
        required=True,
        label='Country'
    )
    branch = forms.ModelChoiceField(
        queryset=Branch.objects.all(),
        required=True,
        label='Branch'
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password1',
                  'password2', 'country', 'branch']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            # Update the auto-created profile
            profile = user.profile
            profile.country = self.cleaned_data['country']
            profile.branch = self.cleaned_data['branch']
            profile.save()
        return user
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
            'oem',
            'category',   # ✅ Added category here
            'imei_no',
            'serial_no',
            'mac_address',
            'status',
            'branch',
            'country'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Device Name'}),
            'oem': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Laptop or Router'  # ✅ Added examples
            }),
            'imei_no': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'IMEI Number'}),
            'serial_no': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Serial Number'}),
            'mac_address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 00:1A:2B:3C:4D:5E'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'country': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Required fields
        self.fields['name'].required = True
        self.fields['oem'].required = True
        self.fields['status'].required = True

        # Optional fields
        self.fields['imei_no'].required = False
        self.fields['serial_no'].required = False
        self.fields['mac_address'].required = False
        self.fields['category'].required = True  # ✅ You can set to False if you want optional

        # Hide branch and country for non-superusers
        if user and not user.is_superuser:
            branch = getattr(user.profile, 'branch', None)
            country = getattr(user.profile, 'country', None)
            if branch:
                self.fields['branch'].initial = branch
                self.fields['branch'].widget = forms.HiddenInput()
            if country:
                self.fields['country'].initial = country
                self.fields['country'].widget = forms.HiddenInput()

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

        device_request.branch = self.cleaned_data['branch']
        if device_request.branch and device_request.branch.country:
            device_request.country = device_request.branch.country

        if commit:
            device_request.save()
        return device_request

   # Purchase order with document upload


class PurchaseOrderForm(forms.ModelForm):
    oem = forms.ModelChoiceField(
        queryset=OEM.objects.all(),
        required=True,
        label='OEM (Supplier)',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    branch = forms.ModelChoiceField(
        queryset=Branch.objects.all(),
        required=True,
        label='Branch',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    order_date = forms.DateField(
        widget=forms.DateInput(
            attrs={'type': 'date', 'class': 'form-control'}),
        required=True,
        label='Order Date'
    )
    expected_delivery = forms.DateField(
        widget=forms.DateInput(
            attrs={'type': 'date', 'class': 'form-control'}),
        required=True,
        label='Expected Delivery'
    )
    status = forms.ChoiceField(
        choices=[
            ('Pending', 'Pending'),
            ('Completed', 'Completed'),
            ('Delivered', 'Delivered'),
            ('Cancelled', 'Cancelled'),
        ],
        required=True,
        label='Status',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    document = forms.FileField(
        required=False,
        label='Purchase Order Document',
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = PurchaseOrder
        fields = ['oem', 'branch', 'order_date',
                  'expected_delivery', 'status', 'document']
