from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.db.models import Q, F, Count, Sum, Value, IntegerField
from django.db import transaction
from django.core.mail import send_mail
from django.http import HttpResponse
from django.urls import reverse
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from collections import defaultdict
import openpyxl
from openpyxl.utils import get_column_letter
from django.db.models.functions import Coalesce
from .models import PurchaseOrder
from .forms import PurchaseOrderForm
from .models import (
    Device, OEM, DeviceRequest, Client, IssuanceRecord, ReturnRecord, Branch, Profile
)
from .forms import (
    CustomCreationForm, OEMForm, DeviceForm, DeviceRequestForm
)
from django.utils.dateparse import parse_date

# --- Authentication/Registration ---

def register(request):
    if request.method == 'POST':
        form = CustomCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(
                request, "Registration successful. Please log in.")
            return redirect('login')
    else:
        form = CustomCreationForm()
    return render(request, 'invent/register.html', {'form': form})

def custom_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            if user.is_staff:
                return redirect('store_clerk_dashboard')
            else:
                return redirect('requestor_dashboard')
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()
    return render(request, 'invent/login.html', {'form': form})

def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('login')

# --- Dashboard for Requestor ---

@login_required
def requestor_dashboard(request):
    user_requests = DeviceRequest.objects.filter(
        requestor=request.user).order_by('id')
    labeled_requests = []
    total_requests_count = user_requests.count()
    for idx, req in enumerate(user_requests, start=1):
        label = total_requests_count - idx + 1
        req.label_id = label
        labeled_requests.append(req)
    device_summary = (
        user_requests
        .values('device__imei_no')
        .annotate(
            total_requested=Count('id'),
            total_approved=Count('id', filter=Q(status='Approved')),
            total_pending=Count('id', filter=Q(status='Pending')),
            total_issued=Count('id', filter=Q(status='Issued')),
            total_fully_returned=Count(
                'id', filter=Q(status='Fully Returned')),
            total_partially_returned=Count(
                'id', filter=Q(status='Partially Returned')),
        )
        .order_by('device__imei_no')
    )
    context = {
        'requests': labeled_requests,
        'total_requests': user_requests.count(),
        'approved_count': user_requests.filter(status='Approved').count(),
        'pending_count': user_requests.filter(status='Pending').count(),
        'issued_count': user_requests.filter(status='Issued').count(),
        'fully_returned_count': user_requests.filter(status='Fully Returned').count(),
        'partially_returned_count': user_requests.filter(status='Partially Returned').count(),
        'device_summary': device_summary,
    }
    return render(request, 'invent/requestor_dashboard.html', context)

# --- Device Request ---

@login_required
def request_device(request):
    device_id_from_get = request.GET.get('device')
    user = request.user
    # COUNTRY FILTER: Restrict device queryset by user's country
    if user.is_superuser:
        available_device_queryset = Device.objects.filter(status='available').annotate(
            requested_quantity=Coalesce(
                Sum(
                    'requests__quantity',
                    filter=Q(requests_status_in=[
                             'Pending', 'Approved', 'Issued']),
                    output_field=IntegerField()
                ),
                Value(0)
            )
        ).annotate(
            available_quantity=F('total_quantity') - F('requested_quantity')
        ).filter(
            available_quantity__gt=0
        )
    else:
        user_country = getattr(user.profile, "country", None)
        available_device_queryset = Device.objects.filter(
            status='available', country=user_country
        ).annotate(
            requested_quantity=Coalesce(
                Sum(
                    'requests__quantity',
                    filter=Q(requests_status_in=[
                             'Pending', 'Approved', 'Issued']),
                    output_field=IntegerField()
                ),
                Value(0)
            )
        ).annotate(
            available_quantity=F('total_quantity') - F('requested_quantity')
        ).filter(
            available_quantity__gt=0
        )

    grouped_devices = defaultdict(list)
    for device in available_device_queryset:
        grouped_devices[device.name].append(device)

    available_devices = []
    for name, devices in grouped_devices.items():
        available_devices.append({
            "id": devices[0].id,
            "name": name,
            "imei_no": [d.imei_no for d in devices],
            "serial_no": [d.serial_no for d in devices],
            "category": devices[0].category,
            "description": devices[0].description,
            "status": "available",
            "available_count": sum(d.available_quantity for d in devices),
        })

    categories = available_device_queryset.values_list(
        'category', flat=True).distinct()

    if request.method == 'POST':
        form = DeviceRequestForm(request.POST)
        form.fields['device'].queryset = available_device_queryset
        if form.is_valid():
            device_request = form.save(requestor=request.user)
            send_mail(
                subject='Device Request Confirmation',
                message=(
                    f"Dear {request.user.first_name or request.user.username},\n\n"
                    f"Your request for device (IMEI: {device_request.device.imei_no}, "
                    f"Name: {device_request.device.name}, "
                    f"Category: {device_request.device.category}) has been submitted successfully.\n"
                    f"We will notify you once it is reviewed or issued.\n\n"
                    f"Thank you,\nInventory Management Team"
                ),
                from_email=None,
                recipient_list=[request.user.email],
                fail_silently=False,
            )
            messages.success(request, "Device request submitted successfully!")
            return redirect('requestor_dashboard')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        initial_data = {}
        if device_id_from_get and device_id_from_get.isdigit():
            try:
                device = Device.objects.get(id=int(device_id_from_get))
                if device in available_device_queryset:
                    initial_data['device'] = device.id
            except Device.DoesNotExist:
                pass

        form = DeviceRequestForm(initial=initial_data)
        form.fields['device'].queryset = available_device_queryset

    return render(request, 'invent/request_item.html', {
        'form': form,
        'available_devices': available_devices,
        'categories': categories,
        'branches': Branch.objects.all(),
    })

# --- Cancel Request ---

@login_required
def cancel_request(request, request_id):
    device_request = get_object_or_404(
        DeviceRequest, id=request_id, requestor=request.user)
    if device_request.status == 'Pending':
        if request.method == 'POST':
            device_request.status = 'Cancelled'
            device_request.save()
            messages.success(
                request, f"Request for '{device_request.device.name}' (ID: {request_id}) has been cancelled.")
            return redirect('requestor_dashboard')
        else:
            context = {
                'device_request': device_request
            }
            return render(request, 'invent/cancel_request_confirm.html', context)
    else:
        messages.error(
            request, f"Request for '{device_request.device.name}' (ID: {request_id}) cannot be cancelled because its status is '{device_request.status}'.")
        return redirect('requestor_dashboard')

# --- Clerk Dashboard ---

@login_required
@permission_required('invent.view_device', raise_exception=True)
def store_clerk_dashboard(request):
    user = request.user
    # COUNTRY FILTER: Restrict by user's country
    if user.is_superuser:
        total_devices = Device.objects.count()
        devices_available = Device.objects.filter(status='available').count()
        devices_issued = Device.objects.filter(status='issued').count()
        devices_returned = Device.objects.filter(status='returned').count()
        recent_issuances = (
            IssuanceRecord.objects
            .select_related('device', 'client')
            .order_by('-issued_at')[:10]
        )
        pending_device_requests = DeviceRequest.objects.filter(
            status="Pending").select_related("requestor", "device", "client")
    else:
        user_country = getattr(user.profile, "country", None)
        total_devices = Device.objects.filter(country=user_country).count()
        devices_available = Device.objects.filter(status='available', country=user_country).count()
        devices_issued = Device.objects.filter(status='issued', country=user_country).count()
        devices_returned = Device.objects.filter(status='returned', country=user_country).count()
        recent_issuances = (
            IssuanceRecord.objects
            .filter(device__country=user_country)
            .select_related('device', 'client')
            .order_by('-issued_at')[:10]
        )
        pending_device_requests = DeviceRequest.objects.filter(
            status="Pending", country=user_country).select_related("requestor", "device", "client")
    seen = set()
    recent_devices = []
    for record in recent_issuances:
        if record.device.id not in seen:
            record.device.current_client = record.client
            record.device.issued_at = record.issued_at
            recent_devices.append(record.device)
            seen.add(record.device.id)
        if len(recent_devices) >= 5:
            break
    context = {
        "total_devices": total_devices,
        "devices_available": devices_available,
        "devices_issued": devices_issued,
        "devices_returned": devices_returned,
        "recent_devices": recent_devices,
        "pending_device_requests": pending_device_requests,
    }
    return render(request, 'invent/store_clerk_dashboard.html', context)

@require_POST
def delete_device(request, device_id=None):
    if device_id:
        device = get_object_or_404(Device, pk=device_id)
        device.delete()
    else:
        device_ids = request.POST.getlist('device_ids')
        Device.objects.filter(id__in=device_ids).delete()
    return redirect(reverse('adjust_stock'))

# --- Device Request Approval/Reject ---

@login_required
@permission_required('invent.change_devicerequest', raise_exception=True)
def approve_request(request, request_id):
    device_request = get_object_or_404(DeviceRequest, id=request_id)
    device_request.status = "Approved"
    device_request.save()
    messages.success(
        request, f"Request {device_request.id} approved successfully.")
    return redirect("store_clerk_dashboard")

@login_required
@permission_required('invent.change_devicerequest', raise_exception=True)
def reject_request(request, request_id):
    device_request = get_object_or_404(DeviceRequest, id=request_id)
    device_request.status = "Rejected"
    device_request.save()
    messages.warning(request, f"Request {device_request.id} rejected.")
    return redirect("store_clerk_dashboard")

# --- Device Listing/Search ---
@login_required
def inventory_list_view(request):
    query = request.GET.get('q', '')
    status = request.GET.get('status', 'all')
    page = request.GET.get('page', 1)
    per_page = 10  # Set how many devices per page

    user = request.user
    # COUNTRY FILTER: Restrict by user's country
    if user.is_superuser:
        devices = Device.objects.select_related('oem', 'branch').order_by('category', 'oem__name', 'id')
    else:
        user_country = getattr(user.profile, "country", None)
        devices = Device.objects.select_related('oem', 'branch').filter(country=user_country).order_by('category', 'oem__name', 'id')
    
    if status and status != 'all':
        devices = devices.filter(status=status)
    if query:
        devices = devices.filter(
            Q(imei_no__icontains=query) |
            Q(serial_no__icontains=query) |
            Q(category__icontains=query) |
            Q(oem_name_icontains=query) |
            Q(oem_oem_id_icontains=query) |
            Q(issuancerecord_clientname_icontains=query)
        ).distinct()
    
    for device in devices:
        last_issuance = (
            IssuanceRecord.objects
            .filter(device=device)
            .order_by('-issued_at')
            .select_related('client')
            .first()
        )
        device.current_client = last_issuance.client if last_issuance else None
        device.issued_at = last_issuance.issued_at if last_issuance else None

    grouped_devices = defaultdict(lambda: defaultdict(list))
    for device in devices:
        oem_label = f"{device.oem.name or '-'} ({device.oem.oem_id or '-'})" if device.oem else "-"
        grouped_devices[device.category][oem_label].append(device)

    paginated_grouped_devices = {}
    for category, oems in grouped_devices.items():
        paginated_grouped_devices[category] = {}
        for oem_label, device_list in oems.items():
            paginator = Paginator(device_list, per_page)
            try:
                page_obj = paginator.page(page)
            except Exception:
                page_obj = paginator.page(1)
            paginated_grouped_devices[category][oem_label] = page_obj

    context = {
        'grouped_devices': paginated_grouped_devices,
        'query': query,
        'status': status,
        'page': page,
    }
    return render(request, 'invent/list_device_grouped.html', context)

# --- Stock Management ---

@login_required
@permission_required('invent.add_device', raise_exception=True)
def manage_stock(request):
    user = request.user
    form = DeviceForm()
    if request.method == "POST":
        form = DeviceForm(request.POST)
        if form.is_valid():
            device = form.save(commit=False)
            # Only set country for non-superusers (superuser can set any)
            if not user.is_superuser:
                device.country = user.profile.country
            device.save()
            messages.success(request, "Device added successfully.")
            return redirect('manage_stock')
        else:
            messages.error(request, "Please correct the errors below.")
    return render(request, 'invent/manage_stock.html', {'form': form})

@login_required
@permission_required('invent.change_device', raise_exception=True)
def edit_item(request, device_id):
    device = get_object_or_404(Device, id=device_id)
    if request.method == 'POST':
        form = DeviceForm(request.POST, instance=device)
        if form.is_valid():
            form.save()
            messages.success(
                request, f'Device "{device.name}" updated successfully!')
            return redirect('manage_stock')
        else:
            messages.error(
                request, "Error updating device. Please correct the errors below.")
    else:
        form = DeviceForm(instance=device)
    context = {
        'form': form,
        'device': device,
    }
    return render(request, 'invent/edit_item.html', context)

# --- Issue Device (Clerk) ---

@login_required
@permission_required('invent.can_issue_item', raise_exception=True)
def issue_device(request):
    user = request.user
    # COUNTRY FILTER: Restrict by user's country
    if user.is_superuser:
        available_devices = Device.objects.filter(status='available')
        clients = Client.objects.all()
        pending_requests = DeviceRequest.objects.filter(
            status='Pending'
        ).select_related("requestor", "device", "client")
        all_requests = DeviceRequest.objects.select_related(
            "requestor", "device", "client").all()
    else:
        user_country = getattr(user.profile, "country", None)
        available_devices = Device.objects.filter(status='available', country=user_country)
        clients = Client.objects.all()
        pending_requests = DeviceRequest.objects.filter(
            status='Pending', country=user_country
        ).select_related("requestor", "device", "client")
        all_requests = DeviceRequest.objects.select_related(
            "requestor", "device", "client").filter(country=user_country)

    pending_requests_count = pending_requests.count()

    if request.method == 'POST':
        action = request.POST.get('action')
        device_request_id = request.POST.get('device_request_id')

        if action in ['approve', 'reject', 'issue'] and device_request_id:
            device_request = get_object_or_404(
                DeviceRequest, id=device_request_id)
            device = device_request.device
            client = device_request.client

            if action == 'approve' and device_request.status == 'Pending':
                device_request.status = 'Approved'
                device_request.save()
                messages.success(
                    request, f"Request {device_request.id} for device {device.imei_no} has been *Approved*. Now, please finalize the issuance.")
                return redirect('issue_device')

            elif action == 'issue' and device_request.status == 'Approved':
                if client is None:
                    messages.error(
                        request,
                        f"Cannot issue Request {device_request.id}: *No client is linked* to this approved device request. Update the request first."
                    )
                    return redirect('issue_device')

                if device.status == 'available':
                    with transaction.atomic():
                        device.status = 'issued'
                        device.save()
                        IssuanceRecord.objects.create(
                            device=device,
                            client=client,
                            logistics_manager=request.user,
                            device_request=device_request
                        )
                        device_request.status = 'Issued'
                        device_request.save()
                        messages.success(
                            request,
                            f"Device {device.imei_no} successfully *Issued* to {client.name} (Request {device_request.id})."
                        )
                else:
                    messages.error(
                        request, f"Device {device.imei_no} is no longer available to be issued.")

                return redirect('issue_device')

            elif action == 'reject' and device_request.status in ['Pending', 'Approved']:
                device_request.status = 'Rejected'
                device_request.save()
                messages.success(
                    request, f"Request {device_request.id} *rejected*. Transaction ended.")
                return redirect('issue_device')

            else:
                messages.warning(
                    request, "Invalid action or status for this request.")
                return redirect('issue_device')

        device_id = request.POST.get('device_id')
        client_id = request.POST.get('client_id')
        if device_id and client_id:
            try:
                device = get_object_or_404(
                    Device, id=device_id, status='available')
                client = get_object_or_404(Client, id=client_id)
                with transaction.atomic():
                    device.status = 'issued'
                    device.save()
                    IssuanceRecord.objects.create(
                        device=device,
                        client=client,
                        logistics_manager=request.user
                    )
                    messages.success(
                        request,
                        f"Device {device.imei_no} issued to {client.name} (Direct Issuance)."
                    )
                return redirect('issue_device')
            except Exception as e:
                messages.error(request, f"Error during direct issuance: {e}")
                return redirect('issue_device')

        messages.error(
            request, "Please provide valid inputs for issuance or request action.")
        return redirect('issue_device')

    approved_requests = DeviceRequest.objects.filter(
        status='Approved'
    ).select_related("requestor", "device", "client")

    return render(request, 'invent/issue_device.html', {
        'available_devices': available_devices,
        'clients': clients,
        'pending_requests': pending_requests,
        'approved_requests': approved_requests,
        'pending_requests_count': pending_requests_count,
        'all_requests': all_requests,
    })

# --- Return Device (Clerk) ---

@login_required
@permission_required('invent.can_issue_item', raise_exception=True)
def return_device(request):
    user = request.user
    # COUNTRY FILTER: Restrict by user's country
    if user.is_superuser:
        issued_devices = Device.objects.filter(status='issued')
    else:
        user_country = getattr(user.profile, "country", None)
        issued_devices = Device.objects.filter(status='issued', country=user_country)
    clients = Client.objects.all()
    if request.method == 'POST':
        device_id = request.POST.get('device_id')
        client_id = request.POST.get('client_id')
        reason = request.POST.get('reason', '')
        device = get_object_or_404(Device, id=device_id, status='issued')
        client = get_object_or_404(Client, id=client_id)
        with transaction.atomic():
            device.status = 'returned'
            device.save()
            ReturnRecord.objects.create(
                device=device, client=client, reason=reason)
            messages.success(
                request, f"Device {device.imei_no} returned by {client.name}.")
        return redirect('return_device')
    return render(request, 'invent/return_device.html', {
        'issued_devices': issued_devices,
        'clients': clients
    })

# --- Request Summary for Requestor ---

@login_required
def request_summary(request):
    user_requests = DeviceRequest.objects.filter(requestor=request.user)
    total_requests = user_requests.count()
    pending_requests = user_requests.filter(status='Pending').count()
    approved_requests = user_requests.filter(status='Approved').count()
    issued_requests = user_requests.filter(status='Issued').count()
    rejected_requests = user_requests.filter(status='Rejected').count()
    partially_returned_requests = user_requests.filter(
        status='Partially Returned').count()
    fully_returned_requests = user_requests.filter(
        status='Fully Returned').count()
    total_returned_quantity_by_user = user_requests.aggregate(
        total_returned=Sum('quantity')
    )['total_returned'] or 0
    requests_by_status = user_requests.values(
        'status').annotate(count=Count('id')).order_by('status')
    requests_by_device = user_requests.values('device__name').annotate(
        total_requested=Sum('quantity')
    ).order_by('-total_requested')[:10]
    requests_by_requestor = user_requests.values(
        'requestor__username').annotate(count=Count('id'))
    context = {
        'total_requests': total_requests,
        'pending_requests': pending_requests,
        'approved_requests': approved_requests,
        'issued_requests': issued_requests,
        'rejected_requests': rejected_requests,
        'partially_returned_requests': partially_returned_requests,
        'fully_returned_requests': fully_returned_requests,
        'total_returned_quantity_by_user': total_returned_quantity_by_user,
        'requests_by_status': requests_by_status,
        'requests_by_device': requests_by_device,
        'requests_by_requestor': requests_by_requestor,
    }
    return render(request, 'invent/request_summary.html', context)

# --- Client List ---

@login_required
def client_list(request):
    user = request.user
    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    client_filter = request.GET.get('client', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    # COUNTRY FILTER: Restrict by user's country
    if user.is_superuser:
        requests_qs = DeviceRequest.objects.select_related(
            'client', 'device').order_by('-date_requested')
    else:
        user_country = getattr(user.profile, "country", None)
        requests_qs = DeviceRequest.objects.select_related(
            'client', 'device').filter(country=user_country).order_by('-date_requested')

    if query:
        requests_qs = requests_qs.filter(
            Q(client_name_icontains=query) |
            Q(client_email_icontains=query) |
            Q(client_phone_no_icontains=query) |
            Q(device_name_icontains=query)
        )

    if status_filter:
        requests_qs = requests_qs.filter(status=status_filter)

    if client_filter:
        requests_qs = requests_qs.filter(client_name_icontains=client_filter)

    if date_from:
        requests_qs = requests_qs.filter(
            date_requested_date_gte=parse_date(date_from))
    if date_to:
        requests_qs = requests_qs.filter(
            date_requested_date_lte=parse_date(date_to))

    paginator = Paginator(requests_qs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'query': query,
        'status_filter': status_filter,
        'client_filter': client_filter,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'invent/client_list.html', context)

# --- Stock Adjustment/Search ---

@login_required
@permission_required('invent.change_device', raise_exception=True)
def adjust_stock(request):
    query = request.GET.get('q', '')
    user = request.user
    # COUNTRY FILTER: Restrict by user's country
    if user.is_superuser:
        devices = Device.objects.all().order_by('id')
    else:
        user_country = getattr(user.profile, "country", None)
        devices = Device.objects.filter(country=user_country).order_by('id')
    if query:
        devices = devices.filter(
            Q(imei_no__icontains=query) |
            Q(serial_no__icontains=query) |
            Q(name__icontains=query) |
            Q(category__icontains=query) |
            Q(issuancerecord_clientname_icontains=query)
        ).distinct()
    for device in devices:
        last_issuance = (
            IssuanceRecord.objects
            .filter(device=device)
            .order_by('-issued_at')
            .select_related('client')
            .first()
        )
        device.current_client = last_issuance.client if last_issuance else None
        device.issued_at = last_issuance.issued_at if last_issuance else None
    context = {
        'devices': devices,
        'query': query,
    }
    return render(request, 'invent/adjust_stock.html', context)

# --- OEM Management ---

def add_oem(request):
    edit_mode = False
    oem_to_edit = None

    # Handle OEM deletion
    if request.method == "POST" and "delete_oem_id" in request.POST:
        oem = get_object_or_404(OEM, id=request.POST.get("delete_oem_id"))
        oem.delete()
        messages.success(request, "OEM deleted successfully!")
        return redirect('add_oem')

    # Handle OEM edit (save changes)
    if request.method == "POST" and "edit_oem_id" in request.POST:
        oem_to_edit = get_object_or_404(OEM, id=request.POST.get("edit_oem_id"))
        form = OEMForm(request.POST, instance=oem_to_edit)
        edit_mode = True
        if form.is_valid():
            form.save()
            messages.success(request, "OEM updated successfully!")
            return redirect('add_oem')
        else:
            messages.error(request, "Please correct the errors below.")

    # Start editing (GET ?edit=id)
    elif "edit" in request.GET:
        oem_to_edit = get_object_or_404(OEM, id=request.GET.get("edit"))
        form = OEMForm(instance=oem_to_edit)
        edit_mode = True

    # Handle OEM addition
    elif request.method == 'POST':
        form = OEMForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "OEM added successfully!")
            return redirect('add_oem')
        else:
            messages.error(request, "Please correct the errors below.")

    else:
        form = OEMForm()

    oems = OEM.objects.all().order_by('-id')
    return render(request, 'invent/add_oem.html', {
        'form': form,
        'oems': oems,
        'edit_mode': edit_mode,
        'oem_to_edit': oem_to_edit,
    })

# --- Reports and Export ---

@login_required
@permission_required('invent.view_device', raise_exception=True)
def reports_view(request):
    user = request.user
    # COUNTRY FILTER: Restrict by user's country
    if user.is_superuser:
        total_items = Device.objects.aggregate(total=Sum('total_quantity'))['total'] or 0
        total_requests = DeviceRequest.objects.count()
        pending_count = DeviceRequest.objects.filter(status='Pending').count()
        approved_count = DeviceRequest.objects.filter(status='Approved').count()
        issued_count = DeviceRequest.objects.filter(status='Issued').count()
        rejected_count = DeviceRequest.objects.filter(status='Rejected').count()
        fully_returned_count = DeviceRequest.objects.filter(status='Fully Returned').count()
        partially_returned_count = DeviceRequest.objects.filter(status='Partially Returned').count()
        total_returned_quantity_all_items = DeviceRequest.objects.aggregate(
            total_returned=Sum('returned_quantity')
        )['total_returned'] or 0
        top_requested_items = (
            DeviceRequest.objects.values('device__name')
            .annotate(request_count=Count('id'))
            .order_by('-request_count')[:2]
        )
    else:
        user_country = getattr(user.profile, "country", None)
        total_items = Device.objects.filter(country=user_country).aggregate(total=Sum('total_quantity'))['total'] or 0
        total_requests = DeviceRequest.objects.filter(country=user_country).count()
        pending_count = DeviceRequest.objects.filter(status='Pending', country=user_country).count()
        approved_count = DeviceRequest.objects.filter(status='Approved', country=user_country).count()
        issued_count = DeviceRequest.objects.filter(status='Issued', country=user_country).count()
        rejected_count = DeviceRequest.objects.filter(status='Rejected', country=user_country).count()
        fully_returned_count = DeviceRequest.objects.filter(status='Fully Returned', country=user_country).count()
        partially_returned_count = DeviceRequest.objects.filter(status='Partially Returned', country=user_country).count()
        total_returned_quantity_all_items = DeviceRequest.objects.filter(country=user_country).aggregate(
            total_returned=Sum('returned_quantity')
        )['total_returned'] or 0
        top_requested_items = (
            DeviceRequest.objects.filter(country=user_country).values('device__name')
            .annotate(request_count=Count('id'))
            .order_by('-request_count')[:2]
        )
    context = {
        'total_items': total_items,
        'total_requests': total_requests,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'issued_count': issued_count,
        'rejected_count': rejected_count,
        'fully_returned_count': fully_returned_count,
        'partially_returned_count': partially_returned_count,
        'total_returned_quantity_all_items': total_returned_quantity_all_items,
        'top_requested_items': top_requested_items,
    }
    return render(request, 'invent/reports.html', context)

@login_required
@permission_required('invent.add_device', raise_exception=True)
def upload_inventory(request):
    if request.method == 'POST' and request.FILES.get('excel_file'):
        excel_file = request.FILES['excel_file']
        try:
            wb = openpyxl.load_workbook(excel_file)
            sheet = wb.active
        except Exception:
            messages.error(
                request, "Invalid Excel file. Please upload a valid .xlsx file.")
            return redirect("upload_inventory")
        header = [str(cell.value).strip() for cell in sheet[1]]
        header_lower = [h.lower() for h in header]

        # Support both new and old formats
        supports_new = "selling price" in header_lower and "currency" in header_lower
        supports_old = (
            "selling price (usd)" in header_lower
            or "selling price (ksh)" in header_lower
            or "selling price (tsh)" in header_lower
        )

        if not (supports_new or supports_old):
            messages.error(request, "Missing required columns for price and currency.")
            return redirect("upload_inventory")

        required_columns = [
            "OEM ID", "Product ID", "IMEI No", "Serial No", "Category",
            "Description", "Name", "Quantity", "Status"
        ]
        for col in required_columns:
            if col.lower() not in header_lower:
                messages.error(request, f"Missing required column: {col}")
                return redirect("upload_inventory")

        header_index_map = {h.lower(): i for i, h in enumerate(header)}

        for row in sheet.iter_rows(min_row=2, values_only=True):
            row_data = {h.lower(): row[i] for h, i in header_index_map.items()}
            oem_id = row_data.get("oem id")
            product_id = row_data.get("product id")
            imei_field = str(row_data.get("imei no") or "").strip()
            serial_no = row_data.get("serial no")
            category_value = row_data.get("category")
            description = row_data.get("description")
            name = row_data.get("name")
            qty_field = row_data.get("quantity")
            status = (str(row_data.get("status") or "available")).lower()
            if status not in ["available", "issued", "returned", "faulty"]:
                messages.warning(
                    request, f"Invalid status '{status}' for product {product_id}. Skipped.")
                continue
            oem = OEM.objects.filter(oem_id=oem_id).first()
            if not oem:
                messages.warning(
                    request, f"OEM ID {oem_id} not found. Skipped product {product_id}.")
                continue
            imeis = [i.strip() for i in imei_field.split(",") if i.strip()]
            try:
                total_qty = int(qty_field)
            except (TypeError, ValueError):
                total_qty = len(imeis)
            if total_qty != len(imeis):
                messages.warning(
                    request,
                    f"Product '{product_id}' has Quantity={total_qty} "
                    f"but {len(imeis)} IMEIs provided. Using IMEI count."
                )
                total_qty = len(imeis)

            # --- Unified price/currency logic ---
            if "selling price" in row_data and "currency" in row_data:
                selling_price = row_data.get("selling price") or 0
                currency = str(row_data.get("currency") or "USD").upper()
                if not selling_price:
                    selling_price = 0
                if currency not in ["USD", "KSH", "TSH"]:
                    currency = "USD"
            else:
                price_usd = row_data.get("selling price (usd)") or 0
                price_ksh = row_data.get("selling price (ksh)") or 0
                price_tsh = row_data.get("selling price (tsh)") or 0
                if price_usd and float(price_usd) > 0:
                    selling_price = price_usd
                    currency = "USD"
                elif price_ksh and float(price_ksh) > 0:
                    selling_price = price_ksh
                    currency = "KSH"
                elif price_tsh and float(price_tsh) > 0:
                    selling_price = price_tsh
                    currency = "TSH"
                else:
                    selling_price = 0
                    currency = "USD"

            for imei in imeis:
                if Device.objects.filter(imei_no=imei).exists():
                    messages.warning(
                        request, f"IMEI {imei} already exists. Skipped.")
                    continue
                if Device.objects.filter(serial_no=serial_no).exists():
                    messages.warning(
                        request, f"Serial No {serial_no} already exists. Skipped.")
                    continue

                device_kwargs = dict(
                    oem=oem,
                    product_id=product_id,
                    imei_no=imei,
                    serial_no=serial_no,
                    category=category_value,
                    description=description,
                    name=name,
                    total_quantity=total_qty,
                    selling_price=selling_price,
                    currency=currency,
                    status=status,
                )
                # COUNTRY FILTER: Set country based on user profile for non-superusers
                if not request.user.is_superuser:
                    device_kwargs["country"] = request.user.profile.country
                else:
                    # For superusers, optionally, let them pick a country or leave blank
                    device_kwargs["country"] = None
                Device.objects.create(**device_kwargs)
        messages.success(request, "Inventory uploaded successfully.")
        return redirect("inventory_list")
    return render(request, "invent/upload_inventory.html")

# --- Total Requests Table/Export (Reports) ---

@login_required
def total_requests(request):
    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    user = request.user
    # COUNTRY FILTER: Restrict by user's country
    if user.is_superuser:
        queryset = DeviceRequest.objects.select_related(
            "device", "client", "requestor").order_by('-date_requested')
    else:
        user_country = getattr(user.profile, "country", None)
        queryset = DeviceRequest.objects.select_related(
            "device", "client", "requestor").filter(country=user_country).order_by('-date_requested')
    if query:
        queryset = queryset.filter(
            Q(device_imei_no_icontains=query) |
            Q(device_serial_no_icontains=query) |
            Q(device_category_icontains=query) |
            Q(client_name_icontains=query)
        )
    if status_filter and status_filter.lower() != 'all':
        queryset = queryset.filter(status=status_filter)
    paginator = Paginator(queryset, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {
        'page_obj': page_obj,
        'status_filter': status_filter,
    }
    return render(request, 'invent/total_requests.html', context)

@login_required
def export_total_requests(request):
    status_filter = request.GET.get('status')
    user = request.user
    # COUNTRY FILTER: Restrict by user's country
    if user.is_superuser:
        queryset = DeviceRequest.objects.select_related(
            "device", "client", "requestor")
    else:
        user_country = getattr(user.profile, "country", None)
        queryset = DeviceRequest.objects.select_related(
            "device", "client", "requestor").filter(country=user_country)
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Device Requests"
    headers = [
        "Category", "IMEI", "Serial", "Status", "Client", "Issued At"
    ]
    ws.append(headers)
    for req in queryset:
        device = req.device
        ws.append([
            device.category or "-", device.imei_no or "-", device.serial_no or "-",
            req.status, req.client.name if req.client else "-",
            req.date_issued.strftime(
                "%Y-%m-%d %H:%M") if req.date_issued else "-"
        ])
    for i, col in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(i)].width = 20
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename=total_requests.xlsx'
    wb.save(response)
    return response

@login_required
def export_inventory_items(request):
    status_filter = request.GET.get('status')
    user = request.user
    # COUNTRY FILTER: Restrict by user's country
    if user.is_superuser:
        queryset = Device.objects.all()
    else:
        user_country = getattr(user.profile, "country", None)
        queryset = Device.objects.filter(country=user_country)
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Inventory Items"
    headers = ['Category', 'IMEI', 'Serial', 'Status', 'Client', 'Issued At']
    ws.append(headers)
    for device in queryset:
        issuance = IssuanceRecord.objects.filter(
            device=device
        ).order_by('-issued_at').first()
        ws.append([
            device.category,
            device.imei_no,
            device.serial_no or "-",
            device.status,
            issuance.client.name if issuance else "-",
            issuance.issued_at.strftime('%Y-%m-%d %H:%M') if issuance else "-"
        ])
    for i, col in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(i)].width = 20
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename=inventory_items.xlsx'
    wb.save(response)
    return response

# --- Return Logic: List of issued requests for return and process return ---

@login_required
@permission_required('invent.can_issue_item', raise_exception=True)
def list_issued_requests_for_return(request):
    user = request.user
    # COUNTRY FILTER: Restrict by user's country
    if user.is_superuser:
        issued_requests = DeviceRequest.objects.filter(
            status='Issued'
        ).select_related('device', 'client', 'requestor').order_by('-date_issued')
    else:
        user_country = getattr(user.profile, "country", None)
        issued_requests = DeviceRequest.objects.filter(
            status='Issued', country=user_country
        ).select_related('device', 'client', 'requestor').order_by('-date_issued')
    context = {
        'issued_requests': issued_requests,
        'title': 'Issued Devices for Return'
    }
    return render(request, 'invent/list_issued_requests_for_return.html', context)

@login_required
@permission_required('invent.can_issue_item', raise_exception=True)
def process_return_for_request(request, request_id):
    device_request = get_object_or_404(
        DeviceRequest, id=request_id, status='Issued'
    )
    if request.method == 'POST':
        returned_quantity = int(request.POST.get('returned_quantity', 1))
        reason = request.POST.get('reason', '')
        if returned_quantity > (device_request.quantity - device_request.returned_quantity):
            messages.error(request, "Cannot return more than what was issued.")
            return redirect('list_issued_requests_for_return')
        with transaction.atomic():
            device_request.returned_quantity += returned_quantity
            if device_request.returned_quantity >= device_request.quantity:
                device_request.status = 'Fully Returned'
            else:
                device_request.status = 'Partially Returned'
            device_request.save()
            device = device_request.device
            device.status = 'returned'
            device.save()
            ReturnRecord.objects.create(
                device=device,
                client=device_request.client,
                reason=reason
            )
            messages.success(
                request, f"{returned_quantity} device(s) marked as returned.")
        return redirect('list_issued_requests_for_return')
    return render(request, 'invent/process_return_for_request.html', {
        'device_request': device_request
    })

@login_required
def request_list(request, status):
    user_requests = DeviceRequest.objects.filter(requestor=request.user)
    if status == "all":
        requests = user_requests
    else:
        requests = user_requests.filter(status__iexact=status)
    return render(request, 'invent/request_list.html', {
        'status': status,
        'requests': requests
    })

@login_required
@permission_required('invent.add_purchaseorder', raise_exception=True)
def purchase_orders(request):
    user = request.user

    # Determine country for filtering (assuming via user profile)
    if user.is_superuser:
        country = None  # Superuser can see all
    else:
        country = getattr(user.profile, 'country', None)
        if not country:
            messages.error(request, "No country assigned to your profile. Contact admin.")
            return redirect("store_clerk_dashboard")

    # Handle Add/Edit mode
    edit_mode = False
    po_to_edit = None

    # --- Handle Edit Mode ---
    edit_id = request.GET.get('edit')
    if edit_id:
        po_to_edit = get_object_or_404(PurchaseOrder, id=edit_id)
        # Only allow editing if PO is in user's country
        if not user.is_superuser and po_to_edit.oem.country != country:
            messages.error(request, "You do not have permission to edit this purchase order.")
            return redirect('purchase_orders')
        edit_mode = True

    # --- Handle Delete ---
    if request.method == "POST" and 'delete_po_id' in request.POST:
        po_id = request.POST.get("delete_po_id")
        po = get_object_or_404(PurchaseOrder, id=po_id)
        if user.is_superuser or (po.oem.country == country):
            po.delete()
            messages.success(request, "Purchase Order deleted.")
            return redirect('purchase_orders')
        else:
            messages.error(request, "You do not have permission to delete this purchase order.")
            return redirect('purchase_orders')

    # --- Handle Form Submission (Add or Edit) ---
    if request.method == "POST" and 'delete_po_id' not in request.POST:
        if edit_mode:
            form = PurchaseOrderForm(request.POST, request.FILES, instance=po_to_edit)
        else:
            form = PurchaseOrderForm(request.POST, request.FILES)
        # Restrict OEM choices by country for non-superusers
        if not user.is_superuser:
            form.fields['oem'].queryset = OEM.objects.filter(country=country)
        if form.is_valid():
            po = form.save(commit=False)
            # (Optional) Set country if your PurchaseOrder model has a country field
            # if hasattr(po, 'country'):
            #     po.country = country
            po.save()
            messages.success(request, f"Purchase Order {'updated' if edit_mode else 'created'} successfully!")
            return redirect('purchase_orders')
    else:
        if edit_mode:
            form = PurchaseOrderForm(instance=po_to_edit)
        else:
            form = PurchaseOrderForm()
        if not user.is_superuser:
            form.fields['oem'].queryset = OEM.objects.filter(country=country)

    # --- List POs for current country ---
    if user.is_superuser:
        purchase_orders = PurchaseOrder.objects.all().order_by('-order_date')
    else:
        purchase_orders = PurchaseOrder.objects.filter(oem__country=country).order_by('-order_date')

    return render(request, 'invent/purchase_orders.html', {
        'form': form,
        'purchase_orders': purchase_orders,
        'edit_mode': edit_mode,
        'po_to_edit': po_to_edit,
    })