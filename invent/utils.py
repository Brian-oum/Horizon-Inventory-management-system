from functools import wraps
from django.shortcuts import redirect
from django.core.exceptions import PermissionDenied

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