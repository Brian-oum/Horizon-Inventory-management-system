from . import views
from django.urls import path

urlpatterns = [
    path('register/', views.register, name='register'),
    path('custom_login/', views.custom_login, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Requestor Paths
    path('', views.requestor_dashboard, name='requestor_dashboard'),
    path('request_item/', views.request_item, name='request_item'),
    path('request_summary/', views.request_summary, name='request_summary'),
    path('cancel-request/<int:request_id>/',
         views.cancel_request, name='cancel_request'),


    # Store Clerk Paths
    path('store_clerk_dashboard/', views.store_clerk_dashboard,
         name='store_clerk_dashboard'),
    path('manage_stock/', views.manage_stock, name='manage_stock'),
    path('edit_item/<int:item_id>/', views.edit_item, name='edit_item'),
    # This maps to reports_view
    path('reports/', views.reports_view, name='reports'),
    path('reports/export/inventory-items/',
         views.export_inventory_items, name='export_inventory_items'),

    # NEW Functionalities (Issue and Adjust)
    path('issue-item/', views.issue_item, name='issue_item'),
    path('adjust_stock/', views.adjust_stock, name='adjust_stock'),
    path('upload-inventory/', views.upload_inventory, name='upload_inventory'),

    # NEW: Return Logic Paths (Aligning with your provided view names)
    path('returns/', views.list_issued_requests_for_return, # This was previously select_request_for_return in my views.py
         name='list_issued_requests_for_return'),
    path('returns/process/<int:request_id>/', # This was previously return_item in my views.py
         views.process_return_for_request, name='process_return_for_request'),

    # NEW: Standalone page for listing all inventory items
    path('inventory_list/', views.inventory_list_view, name='inventory_list'), # Added this URL pattern

    # IoT Device Issuance/Return Paths
    path('issue_device/', views.issue_device, name='issue_device'),
    path('return_device/', views.return_device, name='return_device'),

    # Reports
    path('reports/total-requests/', views.total_requests, name='total_requests'),
    path('reports/export/total-requests/',
         views.export_total_requests, name='export_total_requests'),
]