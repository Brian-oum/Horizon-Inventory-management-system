from .models import DeviceRequest

def pending_requests_count(request):
    """
    Provide pending requests count for the sidebar:
      - Superusers see the global pending count.
      - Users with 'invent.can_issue_item' see pending requests for their branch (if set).
      - Others see 0.
    Returns context variable: pending_requests_count_for_sidebar
    """
    if not request.user.is_authenticated:
        return {'pending_requests_count_for_sidebar': 0}

    try:
        if request.user.is_superuser:
            count = DeviceRequest.objects.filter(status='Pending').count()
            return {'pending_requests_count_for_sidebar': count}

        if request.user.has_perm('invent.can_issue_item'):
            profile = getattr(request.user, 'profile', None)
            branch = getattr(profile, 'branch', None)

            if branch:
                count = DeviceRequest.objects.filter(status='Pending', branch=branch).count()
            else:
                # fallback to global count if user has no branch assigned
                count = DeviceRequest.objects.filter(status='Pending').count()

            return {'pending_requests_count_for_sidebar': count}

    except Exception:
        return {'pending_requests_count_for_sidebar': 0}

    return {'pending_requests_count_for_sidebar': 0}


def user_branch(request):
    """
    Add the current user's branch (Profile.branch) to template context as `user_branch`.
    Returns None for anonymous users or users without a profile/branch.
    """
    branch = None
    try:
        if request.user.is_authenticated:
            profile = getattr(request.user, 'profile', None)
            branch = getattr(profile, 'branch', None)
    except Exception:
        branch = None

    return {'user_branch': branch}