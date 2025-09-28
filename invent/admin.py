from .models import Office, Supplier, PurchaseOrder, Device, Client, IssuanceRecord, ReturnRecord
from django.contrib import admin
# Import all your models
from .models import InventoryItem, ItemRequest, StockTransaction
from django.utils import timezone
from django.db import transaction
from django.db.models import F

# Register your models here so they appear in the Django admin.


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'serial_number',
        'category',
        'condition',
        'status',
        'quantity_total',
        'quantity_issued',
        'quantity_returned',  # Display the new field
        'quantity_remaining',  # Display the calculated property
        'created_at',
        'updated_at'
    )
    list_filter = ('category', 'condition', 'status')
    search_fields = ('name', 'serial_number', 'category')
    readonly_fields = ('created_at', 'updated_at',
                       'created_by')  # Make these read-only
    fieldsets = (
        (None, {
            'fields': ('name', 'serial_number', 'category', 'condition', 'status', 'expiration_date')
        }),
        ('Quantities', {
            'fields': ('quantity_total', 'quantity_issued', 'quantity_returned')
        }),
        ('Audit Info', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)  # Collapse this section by default
        }),
    )


@admin.register(ItemRequest)
class ItemRequestAdmin(admin.ModelAdmin):
    list_display = (
        'item',
        'requestor',
        'quantity',
        'returned_quantity',  # Display the new field
        'status',
        'application_date',
        'date_issued',  # Display the new field
        'date_requested'
    )
    list_filter = ('status', 'application_date', 'date_issued')
    search_fields = ('item__name', 'requestor__username', 'reason')
    # Use raw_id_fields for FKs for better performance with many items/users
    raw_id_fields = ('item', 'requestor')
    actions = ['mark_approved', 'mark_issued', 'mark_rejected',
               'mark_cancelled', 'mark_fully_returned']  # Custom actions

    def mark_approved(self, request, queryset):
        queryset.update(status='Approved')
        self.message_user(request, "Selected requests marked as Approved.")
    mark_approved.short_description = "Mark selected requests as Approved"

    def mark_issued(self, request, queryset):
        # This action should ideally trigger the same logic as your issue_item view
        # For simplicity in admin, we'll just change status and update quantity_issued
        # A more robust solution might involve a custom admin form or a signal.
        for item_request in queryset:
            if item_request.status == 'Approved':
                with transaction.atomic():
                    item = item_request.item
                    item.quantity_issued = F(
                        'quantity_issued') + item_request.quantity
                    item.save(update_fields=['quantity_issued'])

                    StockTransaction.objects.create(
                        item=item,
                        transaction_type='Issue',
                        quantity=item_request.quantity,
                        item_request=item_request,
                        issued_to=item_request.requestor.username,
                        reason=f"Issued via admin for request ID: {item_request.id}",
                        recorded_by=request.user
                    )
                    item_request.status = 'Issued'
                    item_request.date_issued = timezone.now()
                    item_request.save()  # This save will send email
                self.message_user(
                    request, f"Request {item_request.id} marked as Issued and stock updated.")
            else:
                self.message_user(
                    request, f"Request {item_request.id} is not Approved and cannot be issued.", level='warning')
    mark_issued.short_description = "Mark selected requests as Issued and update stock"

    def mark_rejected(self, request, queryset):
        queryset.update(status='Rejected')
        self.message_user(request, "Selected requests marked as Rejected.")
    mark_rejected.short_description = "Mark selected requests as Rejected"

    def mark_cancelled(self, request, queryset):
        queryset.update(status='Cancelled')
        self.message_user(request, "Selected requests marked as Cancelled.")
    mark_cancelled.short_description = "Mark selected requests as Cancelled"

    def mark_fully_returned(self, request, queryset):
        for item_request in queryset:
            if item_request.status == 'Issued' or item_request.status == 'Partially Returned':
                with transaction.atomic():
                    # Calculate remaining quantity to return for this request
                    remaining_to_return = item_request.quantity - item_request.returned_quantity

                    if remaining_to_return > 0:
                        item = item_request.item
                        item.quantity_issued = F(
                            'quantity_issued') - remaining_to_return
                        item.quantity_total = F(
                            'quantity_total') + remaining_to_return
                        item.quantity_returned = F(
                            'quantity_returned') + remaining_to_return
                        item.save(update_fields=[
                                  'quantity_issued', 'quantity_total', 'quantity_returned'])
                        item.refresh_from_db()  # Get updated values

                        StockTransaction.objects.create(
                            item=item,
                            transaction_type='Return',
                            quantity=remaining_to_return,
                            item_request=item_request,
                            reason=f"Fully returned via admin for request ID: {item_request.id}",
                            recorded_by=request.user
                        )

                        item_request.returned_quantity = F(
                            'returned_quantity') + remaining_to_return
                        item_request.status = 'Fully Returned'
                        item_request.save()  # This save will trigger email
                        self.message_user(
                            request, f"Request {item_request.id} marked as Fully Returned and stock updated.")
                    else:
                        self.message_user(
                            request, f"Request {item_request.id} has no outstanding quantity to return.", level='warning')
            else:
                self.message_user(
                    request, f"Request {item_request.id} cannot be marked as Fully Returned from its current status '{item_request.status}'.", level='error')
    mark_fully_returned.short_description = "Mark selected requests as Fully Returned and update stock"


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'item',
        'transaction_type',
        'quantity',
        'item_request',  # Display the new ForeignKey
        'issued_to',
        'reason',
        'transaction_date',
        'recorded_by'
    )
    list_filter = ('transaction_type', 'transaction_date', 'recorded_by')
    search_fields = ('item__name', 'issued_to', 'reason',
                     'item_request__requestor__username')
    readonly_fields = ('transaction_date',)
    # Use raw_id_fields for FKs
    raw_id_fields = ('item', 'item_request', 'recorded_by')


admin.site.register(Office)
admin.site.register(Supplier)
admin.site.register(PurchaseOrder)
admin.site.register(Device)
admin.site.register(Client)
admin.site.register(IssuanceRecord)
admin.site.register(ReturnRecord)
