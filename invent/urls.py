from . import views
from django.urls import path

urlpatterns = [
    path('register/', views.register, name='register'),
    path('custom_login/', views.custom_login, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Requestor Paths
    path('', views.requestor_dashboard, name='requestor_dashboard'),
    path('request_device/', views.request_device, name='request_device'),
    path('request_summary/', views.request_summary, name='request_summary'),
    path('cancel-request/<int:request_id>/',
         views.cancel_request, name='cancel_request'),

    # Store Clerk Paths
    path('store_clerk_dashboard/', views.store_clerk_dashboard,
         name='store_clerk_dashboard'),
    path('manage_stock/', views.manage_stock, name='manage_stock'),
    path('edit_item/<int:item_id>/', views.edit_item, name='edit_item'),
    path('delete-device/<int:device_id>/', views.delete_device, name='delete_device'),
    path('delete-device/', views.delete_device, name='delete_device'),  # For bulk deletion

    # Reports
    path('reports/', views.reports_view, name='reports'),
    path('reports/export/inventory-items/',
         views.export_inventory_items, name='export_inventory_items'),
    path('reports/total-requests/', views.total_requests, name='total_requests'),
    path('reports/export/total-requests/',
         views.export_total_requests, name='export_total_requests'),

    # Inventory Actions
    path('issue-item/', views.issue_item, name='issue_item'),
    path('adjust_stock/', views.adjust_stock, name='adjust_stock'),
    path('upload-inventory/', views.upload_inventory, name='upload_inventory'),

    # Return Logic
    path('returns/', views.list_issued_requests_for_return,
         name='list_issued_requests_for_return'),
    path('returns/process/<int:request_id>/',
         views.process_return_for_request, name='process_return_for_request'),

    # Inventory List
    path('inventory_list/', views.inventory_list_view, name='inventory_list'),

    # IoT Device Issuance/Return
    path('issue_device/', views.issue_device, name='issue_device'),
    path('return_device/', views.return_device, name='return_device'),

    # Supplier Management
    path('add-supplier/', views.add_supplier, name='add_supplier'),

    # Device Request Management
    path('approve-request/<int:request_id>/',
         views.approve_request, name='approve_request'),
    path('reject-request/<int:request_id>/',
         views.reject_request, name='reject_request'),
]
