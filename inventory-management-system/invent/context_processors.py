from .models import ItemRequest  # Import your ItemRequest model


def pending_requests_count(request):
    """
    Adds the count of pending item requests to the context for sidebar notifications.
    This function will be automatically called by Django for every template render.
    """
    count = 0  # Default to 0

    if request.user.is_authenticated:
        # Check if the user has the specific permission to issue items
        # This is a good practice to ensure the count is only relevant for authorized users
        # Adjust 'invent.can_issue_item' if your permission name is different
        if request.user.has_perm('invent.can_issue_item'):
            count = ItemRequest.objects.filter(status='Pending').count()

    return {'pending_requests_count_for_sidebar': count}
