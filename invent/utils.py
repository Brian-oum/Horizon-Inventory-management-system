from functools import wraps
from django.shortcuts import redirect
from django.core.exceptions import PermissionDenied
import io, os
from django.conf import settings
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from django.core.mail import EmailMessage
from datetime import datetime

def generate_delivery_note(device_request):
    """
    Generate a PDF delivery note with company logo and list all issued devices/IMEIs.
    Sends the PDF via email to the requestor.
    """
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # -------------------- Draw Company Logo -------------------- #
    logo_path = os.path.join(settings.BASE_DIR, "static", "invent", "images", "logo.png")
    if os.path.exists(logo_path):
        pdf.drawImage(
            logo_path,
            x=50,
            y=height - 80,
            width=150,
            height=50,
            preserveAspectRatio=True,
            mask='auto'
        )
    else:
        print("Logo not found at:", logo_path)

    # -------------------- Delivery Note Title -------------------- #
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, height - 110, f"Delivery Note - Request #{device_request.id}")

    # -------------------- Request Info -------------------- #
    pdf.setFont("Helvetica", 12)
    y = height - 140
    pdf.drawString(50, y, f"Client: {device_request.client.name if device_request.client else 'N/A'}")
    y -= 20
    pdf.drawString(50, y, f"Branch: {device_request.branch.name if device_request.branch else 'N/A'}")
    y -= 20
    pdf.drawString(50, y, f"Date Issued: {device_request.date_issued.strftime('%Y-%m-%d %H:%M') if device_request.date_issued else datetime.now().strftime('%Y-%m-%d %H:%M')}")
    y -= 30

    # -------------------- Devices Table -------------------- #
    data = [["Device Name", "IMEI", "Serial No"]]

    # List all selected devices for this request
    for sd in device_request.selected_devices.all():
        device = sd.device
        # Pick the assigned IMEI (must be marked unavailable already)
        imei_obj = device.imeis.filter(is_available=False).first()
        imei_number = imei_obj.imei_number if imei_obj else "N/A"
        serial_no = imei_obj.serial_no if imei_obj and imei_obj.serial_no else "N/A"
        data.append([device.name, imei_number, serial_no])

    table = Table(data, colWidths=[200, 150, 150])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("TEXTCOLOR", (0,0), (-1,0), colors.black),
        ("ALIGN", (0,0), (-1,-1), "LEFT"),
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
    ]))

    # Draw table
    table.wrapOn(pdf, width, height)
    table.drawOn(pdf, 50, y - (20 * len(data)))

    # -------------------- Finalize PDF -------------------- #
    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    # -------------------- Send PDF via Email -------------------- #
    email = EmailMessage(
        subject=f"Delivery Note - Request #{device_request.id}",
        body="Please find attached your delivery note.",
        from_email=None,
        to=[device_request.requestor.email],
    )
    email.attach(f"delivery_note_{device_request.id}.pdf", buffer.read(), "application/pdf")
    email.send(fail_silently=False)


def is_branch_admin(user):
    """
    Returns True if user is superuser OR belongs to 'Branch Admin' group.
    """
    if user.is_superuser:
        return True
    return user.groups.filter(name='Branch Admin').exists()

def get_user_branch(user):
    try:
        return getattr(user.profile, 'branch', None)
    except Exception:
        return None

def branch_admin_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not is_branch_admin(request.user):
            raise PermissionDenied("You must be a Branch Admin to access this page.")
        return view_func(request, *args, **kwargs)
    return _wrapped