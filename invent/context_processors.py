from .models import DeviceRequest, Profile  # Use your current models


def pending_requests_count(request):
    """
    Adds the count of pending device requests to the context for sidebar notifications.
    This function will be automatically called by Django for every template render.
    """
    count = 0  # Default to 0

    if request.user.is_authenticated:
        # Check if the user has the specific permission to issue device
        # Adjust 'invent.can_issue_device' if your permission name is different
        if request.user.has_perm('invent.can_issue_device'):
            count = DeviceRequest.objects.filter(status='Pending').count()

    return {'pending_requests_count_for_sidebar': count}


def user_branch(request):
    """
    Adds the logged-in user's branch (Profile.branch) to the template context as `user_branch`.
    Returns None for anonymous users or users without a profile/branch.
    """
    branch = None
    try:
        if request.user.is_authenticated:
            # Use getattr to avoid raising if profile is missing
            profile = getattr(request.user, 'profile', None)
            branch = getattr(profile, 'branch', None)
    except Exception:
        branch = None
    # Return a simple object (Branch instance or None) — templates can access branch.name, branch.address, etc.
    return {'user_branch': branch}