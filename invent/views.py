from .models import DeviceRequest
from django.db.models import Q
from django.core.mail import send_mail
from django.shortcuts import render, redirect, get_object_or_404
# Removed UserCreationForm, assuming CustomCreationForm is used
from django.contrib.auth.forms import AuthenticationForm
from .forms import CustomCreationForm
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.db.models import Sum, F, Count, Q
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
import json
from django.utils.safestring import mark_safe

# Correct Model and Form Imports
from .models import ItemRequest, InventoryItem, StockTransaction
from .forms import ItemRequestForm
from .forms import InventoryItemForm
from .forms import IssueItemForm
from .forms import AdjustStockForm
from .forms import SupplierForm, BoxForm
from .forms import DeviceForm
from .forms import DeviceRequestForm
# Import the new forms for return logic
from .forms import ReturnItemForm, SelectRequestForReturnForm  # NEW

import openpyxl
from openpyxl import Workbook
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.contrib.auth.models import Group
from django.contrib import messages
from django.core.paginator import Paginator
import re

from .models import Box, Device, IssuanceRecord, ReturnRecord, Client
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages


def get_next_available_box():
    """Return the next box available for issuance (FIFO)."""
    return Box.objects.filter(status='available').order_by('id').first()


@login_required
def box_list_view(request):
    """
    Shows all shipment boxes with their statuses and device counts.
    """
    boxes = Box.objects.prefetch_related('devices').all().order_by('id')
    return render(request, 'invent/list_boxes.html', {'boxes': boxes})


@login_required
def box_detail_view(request, box_id):
    """
    Shows details of a single box and the devices inside it.
    """
    box = get_object_or_404(Box, id=box_id)
    devices = box.devices.all()
    return render(request, 'invent/box_detail.html', {'box': box, 'devices': devices})


def register(request):
    if request.method == 'POST':
        # Ensure you use CustomCreationForm if that's what you intend
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


@login_required
def requestor_dashboard(request):
    # Fetch all device requests for the logged-in user, ascending order
    user_requests = DeviceRequest.objects.filter(
        requestor=request.user
    ).order_by('id')  # ascending order

    # Reverse enumerate to label the latest request as 1
    labeled_requests = []
    total_requests_count = user_requests.count()
    for idx, req in enumerate(user_requests, start=1):
        # Latest request gets label 1
        label = total_requests_count - idx + 1
        req.label_id = label
        labeled_requests.append(req)

    # Compute device summary
    device_summary = (
        user_requests
        .values('device__imei_no')  # use the actual field name
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

    # Totals for cards
    total_requests = user_requests.count()
    approved_count = user_requests.filter(status='Approved').count()
    pending_count = user_requests.filter(status='Pending').count()
    issued_count = user_requests.filter(status='Issued').count()
    fully_returned_count = user_requests.filter(
        status='Fully Returned').count()
    partially_returned_count = user_requests.filter(
        status='Partially Returned').count()

    return render(request, 'invent/requestor_dashboard.html', {
        'requests': labeled_requests,
        'total_requests': total_requests,
        'approved_count': approved_count,
        'pending_count': pending_count,
        'issued_count': issued_count,
        'fully_returned_count': fully_returned_count,
        'partially_returned_count': partially_returned_count,
        'device_summary': device_summary,
    })


@login_required
def request_device(request):
    device_id_from_get = request.GET.get('device')

    # ✅ Exclude devices that are already requested and pending approval
    requested_device_ids = DeviceRequest.objects.filter(
        status='Pending'
    ).values_list('device_id', flat=True)

    # Only truly available devices
    available_device_queryset = Device.objects.filter(
        status='available'
    ).exclude(id__in=requested_device_ids).order_by('imei_no')

    available_device_list = list(available_device_queryset)

    # JSON for frontend
    available_device_json = mark_safe(json.dumps([
        {
            "id": device.id,
            "name": device.name,
            "imei_no": device.imei_no,
            "serial_no": device.serial_no,
            "category": device.category,
            "description": device.description,
            "status": device.status,
        }
        for device in available_device_list
    ]))

    # Distinct categories for dropdown
    categories = available_device_queryset.values_list(
        'category', flat=True).distinct()

    if request.method == 'POST':
        form = DeviceRequestForm(request.POST)
        form.fields['device'].queryset = available_device_queryset

        if form.is_valid():
            device_request = form.save(requestor=request.user)

            # Email notification
            send_mail(
                subject='Device Request Confirmation',
                message=(
                    f"Dear {request.user.first_name or request.user.username},\n\n"
                    f"Your request for device (IMEI: {device_request.device.imei_no}, "
                    f"Model: {device_request.device.category}) has been submitted successfully.\n"
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
                if device in available_device_list:
                    initial_data['device'] = device.id
            except Device.DoesNotExist:
                pass

        form = DeviceRequestForm(initial=initial_data)
        form.fields['device'].queryset = available_device_queryset

    return render(request, 'invent/request_item.html', {
        'form': form,
        'available_devices': available_device_list,
        'available_device_json': available_device_json,
        'categories': categories,
    })


@login_required
def cancel_request(request, request_id):
    item_request = get_object_or_404(
        ItemRequest, id=request_id, requestor=request.user)

    # Allow cancellation for Pending, Approved, and even Issued if you decide to revert stock on cancellation
    # For now, keeping your original logic to only allow Pending cancellation
    if item_request.status == 'Pending':
        if request.method == 'POST':
            item_request.status = 'Cancelled'
            # item_request.processed_by = request.user # This field doesn't exist on ItemRequest in your models.py
            # item_request.processed_at = timezone.now() # This field doesn't exist on ItemRequest in your models.py
            item_request.save()  # The save method will handle email notification for 'Cancelled' status
            messages.success(
                request, f"Request for '{item_request.item.name}' (ID: {request_id}) has been cancelled.")
            return redirect('requestor_dashboard')
        else:
            context = {
                'item_request': item_request
            }
            return render(request, 'invent/cancel_request_confirm.html', context)
    else:
        messages.error(
            request, f"Request for '{item_request.item.name}' (ID: {request_id}) cannot be cancelled because its status is '{item_request.status}'.")
        return redirect('requestor_dashboard')


# --- Store Clerk Functionality ---


@login_required
@permission_required('invent.view_inventoryitem', raise_exception=True)
def store_clerk_dashboard(request):
    inventory_items = InventoryItem.objects.all()

    total_inventory_items = inventory_items.aggregate(
        total_sum=Sum('quantity_total'))['total_sum'] or 0
    items_issued = inventory_items.aggregate(
        total_issued=Sum('quantity_issued'))['total_issued'] or 0
    items_returned = inventory_items.aggregate(
        total_returned=Sum('quantity_returned'))['total_returned'] or 0

    items_for_dashboard = inventory_items.order_by('-created_at')[:5]

    pending_requests_count = ItemRequest.objects.filter(
        status='Pending').count()

    issued_but_not_fully_returned_count = ItemRequest.objects.filter(
        status='Issued'
    ).exclude(
        quantity__lte=F('returned_quantity')
    ).count()

    # IoT Device & Box Stats
    total_devices = Device.objects.count()
    devices_available = Device.objects.filter(status='available').count()
    devices_issued = Device.objects.filter(status='issued').count()
    devices_returned = Device.objects.filter(status='returned').count()

    total_boxes = Box.objects.count()
    boxes_in_progress = Box.objects.filter(status='in_progress').count()
    boxes_completed = Box.objects.filter(status='completed').count()

    # Recent Device Activity
    from .models import IssuanceRecord
    recent_issuances = (
        IssuanceRecord.objects
        .select_related('device', 'device__box', 'client')
        .order_by('-issued_at')[:10]
    )
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

    # ✅ Add Device Requests here
    pending_device_requests = DeviceRequest.objects.filter(
        status="Pending").select_related("requestor", "device", "client")

    context = {
        'total_items': total_inventory_items,
        'items_issued': items_issued,
        'items_returned': items_returned,
        'items': items_for_dashboard,
        'pending_requests_count': pending_requests_count,
        'issued_but_not_fully_returned_count': issued_but_not_fully_returned_count,

        # IoT stats
        "total_devices": total_devices,
        "devices_available": devices_available,
        "devices_issued": devices_issued,
        "devices_returned": devices_returned,
        "total_boxes": total_boxes,
        "boxes_in_progress": boxes_in_progress,
        "boxes_completed": boxes_completed,

        # Tables
        "recent_devices": recent_devices,
        "pending_device_requests": pending_device_requests,  # ✅ pass to template
    }
    return render(request, 'invent/store_clerk_dashboard.html', context)

# invent/views.py


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


@login_required
@permission_required('invent/list_device.html', raise_exception=True)
def inventory_list_view(request):
    """
    Displays a list of all IoT devices with search, box linkage, and pagination.
    """
    query = request.GET.get('q', '')

    # Devices are the atomic unit of issuance
    devices = Device.objects.select_related(
        'box').all().order_by('box__id', 'id')

    # Search functionality (IMEI, Serial, Category, Client, Box)
    if query:
        devices = devices.filter(
            Q(imei__icontains=query) |
            Q(serial_number__icontains=query) |
            Q(category__icontains=query) |
            Q(box__box_number__icontains=query) |
            Q(current_client__name__icontains=query)
        )

 # Attach latest IssuanceRecord to each device for template access to client and issued_at
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

    # Pagination (50 per page)
    paginator = Paginator(devices, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'query': query,
    }
    return render(request, 'invent/list_device.html', context)


@login_required
@permission_required('invent.add_device', raise_exception=True)
def manage_stock(request):
    form = DeviceForm()
    if request.method == "POST":
        form = DeviceForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Device added successfully.")
            return redirect('manage_stock')
        else:
            messages.error(request, "Please correct the errors below.")
    return render(request, 'invent/manage_stock.html', {'form': form})


@login_required
@permission_required('invent.change_inventoryitem', raise_exception=True)
def edit_item(request, item_id):
    item = get_object_or_404(InventoryItem, id=item_id)
    if request.method == 'POST':
        form = InventoryItemForm(request.POST, instance=item)
        if form.is_valid():
            if not item.created_by:
                item.created_by = request.user
            form.save()
            messages.success(
                request, f'Inventory Item "{item.name}" updated successfully!')
            return redirect('manage_stock')
        else:
            messages.error(
                request, "Error updating item. Please correct the errors below.")
    else:
        form = InventoryItemForm(instance=item)

    context = {
        'form': form,
        'item': item,
    }
    return render(request, 'invent/edit_item.html', context)


@login_required
@permission_required('invent.can_issue_item', raise_exception=True)
def issue_item(request):
    # Fetch all requests for display in the "All Requests" tab
    all_requests = ItemRequest.objects.all().order_by('-date_requested')

    # Filter for requests that are Pending or Approved to show in the primary tab
    pending_and_approved_requests = all_requests.filter(
        status__in=['Pending', 'Approved'])

    # Initialize the direct issue form (for cases not coming from a request)
    form = IssueItemForm()  # This is the direct issue form

    if request.method == 'POST':
        action = request.POST.get('action')
        request_id = request.POST.get('request_id')

        # This block handles actions (approve, reject, issue) on existing requests
        if action and request_id:
            item_request = get_object_or_404(ItemRequest, id=request_id)
            try:
                with transaction.atomic():
                    if action == 'approve':
                        if item_request.status == 'Pending':  # Ensure only pending requests can be approved
                            item_request.status = 'Approved'
                            # item_request.processed_by = request.user # Add these fields to ItemRequest model if you need them
                            # item_request.processed_at = timezone.now()
                            item_request.save()
                            messages.success(
                                request, f"Request ID {request_id} ({item_request.item.name}) approved.")
                        else:
                            messages.warning(
                                request, f"Request ID {request_id} is '{item_request.status}' and cannot be approved.")

                    elif action == 'reject':
                        # Allow rejecting from Pending or Approved states
                        if item_request.status in ['Pending', 'Approved']:
                            item_request.status = 'Rejected'
                            # item_request.processed_by = request.user
                            # item_request.processed_at = timezone.now()
                            item_request.save()
                            messages.warning(
                                request, f"Request ID {request_id} ({item_request.item.name}) rejected.")
                        else:
                            messages.warning(
                                request, f"Request ID {request_id} is '{item_request.status}' and cannot be rejected.")

                    elif action == 'issue_from_request':
                        # *** CRITICAL CHANGE HERE: Ensure status is 'Approved' to issue ***
                        if item_request.status != 'Approved':
                            messages.error(
                                request, f"Cannot issue for request ID {request_id}. It must be 'Approved'. Current status: '{item_request.status}'.")
                            return redirect('issue_item')

                        item_to_issue_obj = item_request.item

                        if item_to_issue_obj.quantity_remaining() < item_request.quantity:
                            messages.error(
                                request, f"Insufficient stock for '{item_to_issue_obj.name}'. Requested: {item_request.quantity}, Available: {item_to_issue_obj.quantity_remaining()}.")
                            return redirect('issue_item')

                        # Deduct quantity_available and update quantity_issued
                        item_to_issue_obj.quantity_issued = F(
                            'quantity_issued') + item_request.quantity
                        item_to_issue_obj.save(
                            update_fields=['quantity_issued'])

                        StockTransaction.objects.create(
                            item=item_to_issue_obj,
                            transaction_type='Issue',
                            # Store positive quantity for Issue transactions for consistency in StockTransaction
                            quantity=item_request.quantity,
                            # and reflect change in InventoryItem quantities by F() expressions.
                            item_request=item_request,  # LINK THE TRANSACTION TO THE REQUEST
                            issued_to=item_request.requestor.username,
                            reason=f"Issued for request ID: {item_request.id} ({item_request.item.name})",
                            recorded_by=request.user
                        )
                        item_request.status = 'Issued'
                        # item_request.processed_by = request.user
                        # item_request.processed_at = timezone.now()
                        item_request.save()  # This save will now set date_issued and send email
                        messages.success(
                            request, f'Request ID {item_request.id} ({item_request.item.name}) issued and marked as Issued.')
                    else:
                        messages.error(request, "Invalid request action.")

            except Exception as e:
                messages.error(request, f"Error processing request: {e}")

            return redirect('issue_item')

        # This block handles the direct issue form submission (not tied to a request)
        # Re-initialize the form with POST data for direct issue
        form = IssueItemForm(request.POST)
        if form.is_valid():
            item_to_issue = form.cleaned_data['item']
            quantity = form.cleaned_data['quantity']
            issued_to = form.cleaned_data['issued_to']

            try:
                with transaction.atomic():
                    if item_to_issue.quantity_remaining() < quantity:
                        messages.error(
                            request, f"Not enough stock for {item_to_issue.name}. Available: {item_to_issue.quantity_remaining()}.")
                        # No redirect here, so form errors can be displayed
                        # This means you need to pass the context again
                        context = {
                            'form': form,  # Pass the form with errors back
                            'all_requests': all_requests,
                            'pending_and_approved_requests': pending_and_approved_requests,
                            'approved_requests': all_requests.filter(status='Approved'),
                            'issued_requests': all_requests.filter(status='Issued'),
                            'rejected_requests': all_requests.filter(status='Rejected'),
                            'pending_requests': all_requests.filter(status='Pending'),
                        }
                        return render(request, 'invent/issue_item.html', context)

                    item_to_issue.quantity_issued = F(
                        'quantity_issued') + quantity
                    item_to_issue.save(update_fields=['quantity_issued'])

                    StockTransaction.objects.create(
                        item=item_to_issue,
                        transaction_type='Issue',
                        quantity=quantity,  # Store positive quantity for Issue transactions
                        issued_to=issued_to,
                        reason=f"Direct issue to {issued_to}. ",
                        recorded_by=request.user
                    )
                messages.success(
                    request, f'{quantity} x {item_to_issue.name} successfully issued to {issued_to}.')
                return redirect('issue_item')
            except Exception as e:
                messages.error(request, f"Error issuing item: {e}")
        else:
            messages.error(
                request, "Please correct the errors in the direct issue form.")
            # Important: If the form is invalid, you must render the template
            # and pass the form back so its errors can be displayed.
            context = {
                'form': form,  # Pass the form with errors back
                'all_requests': all_requests,
                'pending_and_approved_requests': pending_and_approved_requests,
                'approved_requests': all_requests.filter(status='Approved'),
                'issued_requests': all_requests.filter(status='Issued'),
                'rejected_requests': all_requests.filter(status='Rejected'),
                'pending_requests': all_requests.filter(status='Pending'),
            }
            return render(request, 'invent/issue_item.html', context)

    # GET request: Render the page with the initial data
    context = {
        'form': form,  # Ensure the form is passed for GET requests as well
        'all_requests': all_requests,
        'pending_and_approved_requests': pending_and_approved_requests,
        'approved_requests': all_requests.filter(status='Approved'),
        'issued_requests': all_requests.filter(status='Issued'),
        'rejected_requests': all_requests.filter(status='Rejected'),
        'pending_requests': all_requests.filter(status='Pending'),
    }
    return render(request, 'invent/issue_item.html', context)

 # IoT Device Issuance/Return Views


@login_required
@permission_required('invent.can_issue_item', raise_exception=True)
def issue_device(request):
    box = Box.objects.filter(status='available').order_by('id').first()
    if not box:
        messages.error(request, "No device boxes available for issuance.")
        return redirect('store_clerk_dashboard')
    available_devices = box.devices.filter(status='available')
    clients = Client.objects.all()

    if request.method == 'POST':
        device_id = request.POST.get('device_id')
        client_id = request.POST.get('client_id')
        if not device_id or not client_id:
            messages.error(request, "Please select a device and client.")
            return redirect('issue_device')

        device = get_object_or_404(
            Device, id=device_id, box=box, status='available')
        client = get_object_or_404(Client, id=client_id)

        with transaction.atomic():
            device.status = 'issued'
            device.save()
            IssuanceRecord.objects.create(
                device=device, client=client, logistics_manager=request.user)
            # Check if box is now completed
            if not box.devices.filter(status='available').exists():
                box.status = 'completed'
                box.save()
                # Unlock next box if needed (optional logic, up to you)
                next_box = Box.objects.filter(
                    status='in_progress').order_by('id').first()
                if next_box:
                    next_box.status = 'available'
                    next_box.save()
            messages.success(
                request, f"Device {device.imei_no} issued to {client.name}.")

        return redirect('issue_device')

    return render(request, 'invent/issue_device.html', {
        'box': box,
        'available_devices': available_devices,
        'clients': clients,
    })


@login_required
@permission_required('invent.can_issue_item', raise_exception=True)
def return_device(request):
    issued_devices = Device.objects.filter(status='issued')
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


@login_required
def request_summary(request):
    # Filter all device requests made by the logged-in requestor
    user_requests = DeviceRequest.objects.filter(requestor=request.user)

    # Total counts by status
    total_requests = user_requests.count()
    pending_requests = user_requests.filter(status='Pending').count()
    approved_requests = user_requests.filter(status='Approved').count()
    issued_requests = user_requests.filter(status='Issued').count()
    rejected_requests = user_requests.filter(
        status='Denied').count()  # renamed to match device request
    partially_returned_requests = user_requests.filter(
        status='Partially Returned').count()
    fully_returned_requests = user_requests.filter(
        status='Fully Returned').count()

    # Total returned quantity (if your DeviceRequest model has a 'quantity' or 'returned_quantity' field)
    total_returned_quantity_by_user = user_requests.aggregate(
        # adjust if you have a specific returned field
        total_returned=Sum('quantity')
    )['total_returned'] or 0

    # Requests grouped by status
    requests_by_status = user_requests.values(
        'status').annotate(count=Count('id')).order_by('status')

    # Requests grouped by device (top 10 requested devices)
    requests_by_device = user_requests.values('device__imei_no').annotate(
        total_requested=Sum('quantity')
    ).order_by('-total_requested')[:10]

    # Requests grouped by the user (for the current requestor this is mostly themselves)
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


@login_required
@permission_required('invent.change_inventoryitem', raise_exception=True)
def adjust_stock(request):
    if request.method == 'POST':
        form = AdjustStockForm(request.POST)
        if form.is_valid():
            item = form.cleaned_data['item']
            adjustment_quantity = form.cleaned_data['adjustment_quantity']
            reason = form.cleaned_data['reason']

            try:
                with transaction.atomic():
                    item.quantity_total = F(
                        'quantity_total') + adjustment_quantity
                    item.save(update_fields=['quantity_total'])

                    # Adjusted transaction_type for clarity. 'Adjustment' is better.
                    # quantity will be positive for adding, negative for removing.
                    transaction_type = 'Adjustment'

                    StockTransaction.objects.create(
                        item=item,
                        transaction_type=transaction_type,
                        quantity=adjustment_quantity,  # Store actual adjustment value
                        reason=reason,
                        recorded_by=request.user
                    )
                messages.success(
                    request, f'Stock for {item.name} adjusted by {adjustment_quantity}. New total: {item.quantity_total}.')
                return redirect('adjust_stock')
            except Exception as e:
                messages.error(request, f"Error adjusting stock: {e}")
        else:
            messages.error(
                request, "Please correct the errors in the adjustment form.")
    else:
        form = AdjustStockForm()

    # Filter for 'Adjustment' transactions for this display, as 'Issue' and 'Return' will be handled elsewhere
    recent_transactions = StockTransaction.objects.filter(
        transaction_type='Adjustment').order_by('-transaction_date')[:10]

    context = {
        'form': form,
        'recent_transactions': recent_transactions,
    }
    return render(request, 'invent/adjust_stock.html', context)


def add_supplier(request):
    if request.method == 'POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Supplier added successfully!")
            # go back to clerk dashboard
            return redirect('store_clerk_dashboard')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = SupplierForm()

    return render(request, 'invent/add_supplier.html', {'form': form})


def add_box(request):
    if request.method == 'POST':
        form = BoxForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Box added successfully!")
            return redirect('store_clerk_dashboard')  # Redirect to dashboard
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = BoxForm()

    return render(request, 'invent/add_box.html', {'form': form})


@login_required
@permission_required('invent.change_inventoryitem', raise_exception=True)
def reports(request):
    # This view seems to be a placeholder or generic reports view.
    # The actual data is fetched in `reports_view` below.
    # It might be better to consolidate, or have this render a template that
    # includes components using the data from `reports_view`.
    # For now, I'll update reports_view and keep this for URL mapping if needed.
    return render(request, 'invent/reports.html')


# Consolidated reports_view for cleaner logic and direct use.
# Added permission requirement for store clerks.
@login_required
# ✅ corrected permission
@permission_required('invent.view_device', raise_exception=True)
def reports_view(request):
    context = {
        # Total stock count
        'total_items': Device.objects.aggregate(total=Sum('total_quantity'))['total'] or 0,

        # Request stats
        'total_requests': DeviceRequest.objects.count(),
        'pending_count': DeviceRequest.objects.filter(status='Pending').count(),
        'approved_count': DeviceRequest.objects.filter(status='Approved').count(),
        'issued_count': DeviceRequest.objects.filter(status='Issued').count(),
        'rejected_count': DeviceRequest.objects.filter(status='Rejected').count(),
        'fully_returned_count': DeviceRequest.objects.filter(status='Fully Returned').count(),
        'partially_returned_count': DeviceRequest.objects.filter(status='Partially Returned').count(),

        # Total returned quantity (if field exists)
        'total_returned_quantity_all_items': DeviceRequest.objects.aggregate(
            total_returned=Sum('returned_quantity')
        )['total_returned'] or 0,

        # Top 2 requested devices (grouped by device name)
        'top_requested_items': (
            DeviceRequest.objects.values('device__name')
            .annotate(request_count=Count('id'))
            .order_by('-request_count')[:2]
        )
    }
    return render(request, 'invent/reports.html', context)


@login_required
@permission_required('invent.add_inventoryitem', raise_exception=True)
def upload_inventory(request):
    """
    Upload IoT devices from Excel.
    Expected columns:
    Box, Product ID, IMEI No, Serial No, Category, Description,
    Selling Price (USD), Selling Price (KSH), Selling Price (TSH),
    Status (available, issued, returned, faulty)
    """

    if request.method == 'POST' and request.FILES.get('excel_file'):
        excel_file = request.FILES['excel_file']

        # Validate extension
        if not excel_file.name.endswith('.xlsx'):
            messages.error(request, "Only .xlsx files are supported.")
            return redirect('upload_inventory')

        # Save temporarily
        file_name = default_storage.save(
            excel_file.name, ContentFile(excel_file.read())
        )
        file_path = default_storage.path(file_name)

        try:
            wb = openpyxl.load_workbook(file_path)
            sheet = wb.active

            success_count = 0
            skipped_count = 0

            # Normalize headers
            headers = [cell.value for cell in sheet[1]]
            headers = [h.strip().lower() if h else "" for h in headers]

            valid_statuses = ["available", "issued", "returned", "faulty"]

            for row in sheet.iter_rows(min_row=2, values_only=True):
                row_data = dict(zip(headers, row))

                try:
                    imei = (row_data.get("imei no") or "").strip()
                    serial_no = (row_data.get("serial no")
                                 or "").strip() or None
                    category = (row_data.get("category") or "").strip()
                    description = row_data.get("description") or ""
                    raw_box = (row_data.get("box") or "").strip()

                    # Prices (optional, any or all may be present)
                    price_usd = row_data.get("selling price (usd)") or None
                    price_ksh = row_data.get("selling price (ksh)") or None
                    price_tsh = row_data.get("selling price (tsh)") or None

                    # Status validation
                    status = (row_data.get("status")
                              or "available").strip().lower()
                    if status not in valid_statuses:
                        status = "available"

                    # Must have IMEI
                    if not imei:
                        skipped_count += 1
                        continue

                    # Ensure unique IMEI
                    if Device.objects.filter(imei_no=imei).exists():
                        messages.warning(
                            request, f"Duplicate IMEI '{imei}' skipped.")
                        skipped_count += 1
                        continue

                    # Must have Box → enforce strictly numeric/alphanumeric, no "Box001"
                    if not raw_box:
                        messages.warning(
                            request, f"Missing Box for IMEI {imei}, skipped.")
                        skipped_count += 1
                        continue

                    # Reject if it starts with "box" or contains non-alphanumeric
                    if raw_box.lower().startswith("box"):
                        messages.warning(
                            request, f"Invalid Box '{raw_box}' for IMEI {imei}. Use only the number like '001'.")
                        skipped_count += 1
                        continue

                    if not re.match(r"^[A-Za-z0-9]+$", raw_box):
                        messages.warning(
                            request, f"Invalid Box '{raw_box}' for IMEI {imei}. Only numbers/letters allowed.")
                        skipped_count += 1
                        continue

                    # Box is valid
                    box, _ = Box.objects.get_or_create(number=raw_box)

                    # Create device
                    Device.objects.create(
                        box=box,
                        product_id=row_data.get("product id") or imei,
                        imei_no=imei,
                        serial_no=serial_no,
                        category=category,
                        description=description,
                        selling_price_usd=price_usd,
                        selling_price_ksh=price_ksh,
                        selling_price_tsh=price_tsh,
                        status=status
                    )
                    success_count += 1

                except Exception as e:
                    messages.error(request, f"Error on row {row}: {e}")
                    skipped_count += 1

            messages.success(
                request,
                f"{success_count} device(s) uploaded successfully. "
                f"{skipped_count} row(s) skipped."
            )
            return redirect('upload_inventory')

        except Exception as e:
            messages.error(request, f"Failed to process file: {e}")
            return redirect('upload_inventory')

        finally:
            if default_storage.exists(file_name):
                default_storage.delete(file_name)

    return render(request, 'invent/upload_inventory.html')

# <-- Reports Section ---


def total_requests(request):
    status_filter = request.GET.get('status')
    # Filter ItemRequest by relevant statuses for the "All Requests" report
    # and exclude partially/fully returned if you only want truly active ones.
    # For a total request list, usually all are included unless specified.
    requests = ItemRequest.objects.all()

    if status_filter:
        requests = requests.filter(status=status_filter)

    paginator = Paginator(requests.order_by('-date_requested'), 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'status_filter': status_filter,
    }
    return render(request, 'invent/total_requests.html', context)

# Export


def export_total_requests(request):
    import openpyxl
    from openpyxl.utils import get_column_letter
    from django.http import HttpResponse
    from .models import DeviceRequest  # import your DeviceRequest model

    # Optional filter (if you want to filter by status)
    status_filter = request.GET.get('status')
    queryset = DeviceRequest.objects.select_related(
        "device", "client", "requestor", "device__box"
    )

    if status_filter:
        queryset = queryset.filter(status=status_filter)

    # Create workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Device Requests"

    # Define headers (matching your table view)
    headers = [
        "Box",
        "Category",
        "IMEI",
        "Serial",
        "Status",
        "Client",
        "Issued At",
    ]
    ws.append(headers)

    # Add data rows
    for req in queryset:
        device = req.device
        ws.append([
            device.box.number if device.box else "-",   # Box number
            device.category or "-",                     # Category
            device.imei_no or "-",                      # IMEI
            device.serial_no or "-",                    # Serial
            req.status,                                 # Request status
            req.client.name if req.client else "-",     # Client name
            req.date_issued.strftime(
                "%Y-%m-%d %H:%M") if req.date_issued else "-"
        ])

    # Adjust column widths
    for i, col in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(i)].width = 20

    # Set up HTTP response
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename=total_requests.xlsx'
    wb.save(response)
    return response


def export_inventory_items(request):
    import openpyxl
    from openpyxl.utils import get_column_letter
    from django.http import HttpResponse
    from .models import Device, IssuanceRecord

    # Optional filter by status
    status_filter = request.GET.get('status')
    queryset = Device.objects.all()
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Inventory Items"

    headers = ['Box', 'Category', 'IMEI', 'Serial',
               'Status', 'Client', 'Issued At']
    ws.append(headers)

    for device in queryset:
        # Try to fetch latest issuance record (if exists)
        issuance = IssuanceRecord.objects.filter(
            device=device).order_by('-issued_at').first()

        ws.append([
            device.box.number,   # FK to Box
            device.category,
            device.imei_no,
            device.serial_no or "-",
            device.status,
            issuance.client.name if issuance else "-",   # client if issued
            issuance.issued_at.strftime(
                '%Y-%m-%d %H:%M') if issuance else "-"  # issued_at if issued
        ])

    # Auto-adjust column widths
    for i, col in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(i)].width = 20

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename=inventory_items.xlsx'
    wb.save(response)
    return response


# --- NEW RETURN LOGIC VIEWS ---

@login_required
# Assuming clerks handle returns
@permission_required('invent.can_issue_item', raise_exception=True)
def list_issued_requests_for_return(request):
    # Filter ItemRequests that have been 'Issued' and where the returned_quantity
    # is less than the original requested quantity (meaning not fully returned yet)
    issued_requests = ItemRequest.objects.filter(
        status='Issued'
    ).exclude(
        # Exclude if original quantity <= returned quantity
        quantity__lte=F('returned_quantity')
    ).select_related('item', 'requestor').order_by('-date_issued')

    context = {
        'issued_requests': issued_requests,
        'title': 'Issued Items for Return'
    }
    return render(request, 'invent/list_issued_requests_for_return.html', context)


@login_required
# Assuming clerks handle returns
@permission_required('invent.can_issue_item', raise_exception=True)
def process_return_for_request(request, request_id):
    # Retrieve the ItemRequest, ensuring it's an 'Issued' request and not fully returned
    item_request = get_object_or_404(
        ItemRequest.objects.filter(status='Issued').exclude(
            quantity__lte=F('returned_quantity')),
        id=request_id
    )

    if request.method == 'POST':
        form = ReturnItemForm(request.POST, item_request=item_request)
        if form.is_valid():
            returned_quantity = form.cleaned_data['returned_quantity']
            # Use .get for optional fields
            reason = form.cleaned_data.get('reason')

            # This check is also in the form's clean method, but a double-check here is fine.
            if returned_quantity > item_request.quantity_to_be_returned():
                messages.error(
                    request, "Cannot return more than the remaining issued quantity for this request.")
                return render(request, 'invent/process_return_for_request.html', {'form': form, 'item_request': item_request})

            try:
                with transaction.atomic():
                    # 1. Update InventoryItem's quantity_issued and quantity_total
                    # When an item is returned, it should be deducted from 'quantity_issued'
                    # and added back to 'quantity_total' (available stock).
                    item = item_request.item
                    item.quantity_issued = F(
                        'quantity_issued') - returned_quantity  # Reduce issued count
                    # Increase total available stock
                    item.quantity_total = F(
                        'quantity_total') + returned_quantity
                    # Update aggregate returned count on InventoryItem
                    item.quantity_returned = F(
                        'quantity_returned') + returned_quantity
                    item.save(update_fields=[
                              'quantity_issued', 'quantity_total', 'quantity_returned'])
                    # Reload the item instance to get the updated values after F() expression save
                    item.refresh_from_db()

                    # 2. Create a StockTransaction for the return
                    StockTransaction.objects.create(
                        item=item,
                        transaction_type='Return',
                        quantity=returned_quantity,  # Store the positive quantity that was returned
                        item_request=item_request,  # Link to the original request
                        reason=reason,
                        recorded_by=request.user
                    )

                    # 3. Update ItemRequest's returned_quantity and status
                    item_request.returned_quantity = F(
                        'returned_quantity') + returned_quantity
                    # Save before checking status to ensure F() is applied
                    item_request.save(update_fields=['returned_quantity'])
                    # Refresh to get the actual updated returned_quantity
                    item_request.refresh_from_db()

                    if item_request.returned_quantity == item_request.quantity:
                        item_request.status = 'Fully Returned'
                    elif item_request.returned_quantity > 0:  # Check > 0 after the update
                        item_request.status = 'Partially Returned'
                    item_request.save()  # This save will trigger the email notification for status change

                    messages.success(
                        request, f"Successfully returned {returned_quantity} of {item_request.item.name} for request ID {item_request.id}.")
                    # Redirect back to the list
                    return redirect('list_issued_requests_for_return')

            except Exception as e:
                messages.error(
                    request, f"An error occurred while processing the return: {e}")
    else:
        # Initialize form with maximum allowed return quantity
        form = ReturnItemForm(item_request=item_request)

    context = {
        'form': form,
        'item_request': item_request,
        'title': f'Return Item for Request {item_request.id}'
    }
    return render(request, 'invent/process_return_for_request.html', context)
