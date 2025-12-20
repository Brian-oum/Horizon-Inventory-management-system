from django.urls import path
from . import views

urlpatterns = [
    # Authentication
    path('', views.custom_login, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Requestor Paths
    path('requestor_dashboard', views.requestor_dashboard, name='requestor_dashboard'),
    path('request_device/', views.request_device, name='request_device'),
    path('request_summary/', views.request_summary, name='request_summary'),
    path('client_list/', views.client_list, name='client_list'),
    path('requests/<str:status>/', views.request_list, name='request_list'),
    path('cancel-request/<int:request_id>/',
         views.cancel_request, name='cancel_request'),

    # Store Clerk Dashboard
    path('store_clerk_dashboard/', views.store_clerk_dashboard,
         name='store_clerk_dashboard'),
    path('manage_stock/', views.manage_stock, name='manage_stock'),
    path('edit_item/<int:item_id>/', views.edit_item, name='edit_item'),
    path('select_imeis/<int:request_id>/', views.select_imeis, name='select_imeis'),
    path("delivery_note/<int:request_id>/", views.delivery_note, name="delivery_note"),


    # Inventory Management
    path('inventory_list/', views.inventory_list_view, name='inventory_list'),
    path('adjust_stock/', views.adjust_stock, name='adjust_stock'),
    path('upload-inventory/', views.upload_inventory, name='upload_inventory'),

    # Device Deletion
    path('devices/delete/', views.delete_device,
         name='delete_device'),  # bulk delete
    path('devices/<int:device_id>/delete/', views.delete_device,
         name='delete_device_single'),  # single delete

    # Purchase Orders
    #path('purchase-orders/', views.purchase_orders, name='purchase_orders'),

    # Reports
    path('reports/', views.reports_view, name='reports'),
    path('reports/export/inventory-items/',
         views.export_inventory_items, name='export_inventory_items'),
    path('reports/total-requests/', views.total_requests, name='total_requests'),
    path('reports/export/total-requests/',
         views.export_total_requests, name='export_total_requests'),
    path('inventory/export_grouped/', views.export_grouped_inventory,
         name='export_grouped_inventory'),

    # IoT Device Issuance / Return
    path('issue_device/', views.issue_device, name='issue_device'),
    path('return_device/', views.return_device, name='return_device'),

    # Clerk Submits Devices for Admin Approval
    path('submit_devices_for_approval/', views.submit_devices_for_approval,
         name='submit_devices_for_approval'),

    # Branch Admin Approves/Rejects Selected Devices
    path('approve-device-selection/', views.approve_device_selection,
         name='approve_device_selection'),

    # Clerk Issues Approved Devices
    path('issue-approved-devices/', views.issue_approved_devices,
         name='issue_approved_devices'),

    # Return Processing
    path('returns/', views.list_issued_requests_for_return,
         name='list_issued_requests_for_return'),
    path('returns/process/<int:request_id>/',
         views.process_return_for_request, name='process_return_for_request'),

    # OEM Management
    path('add-oem/', views.add_oem, name='add_oem'),

    # Device Request Approval / Rejection
    path('approve-request/<int:request_id>/',
         views.approve_request, name='approve_request'),
    path('reject-request/<int:request_id>/',
         views.reject_request, name='reject_request'),
]
