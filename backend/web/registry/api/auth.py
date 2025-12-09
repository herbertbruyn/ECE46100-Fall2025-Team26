"""
api/auth.py

Authentication Middleware and Decorators

Provides:
- Authentication decorators
- Permission checking
- Token validation
"""
# Branch retains security 
from functools import wraps
from rest_framework.response import Response
from rest_framework.decorators import api_view
from .models import User, AuthToken


def authenticate_user(request):
    """
    Authenticate user from X-Authorization header
    
    Returns:
        tuple: (user, error_response)
        - If successful: (User object, None)
        - If failed: (None, Response object with error)
    """
    auth_token = request.headers.get('X-Authorization')
    
    if not auth_token:
        return None, Response(
            {"detail": "Authentication failed due to invalid or missing AuthenticationToken"},
            status=403
        )
    
    try:
        # Find token in database
        token = AuthToken.objects.select_related('user').get(token=auth_token)
        
        # Check if token is valid
        if not token.is_valid():
            return None, Response(
                {"detail": "Authentication failed due to invalid or missing AuthenticationToken"},
                status=403
            )
        
        # Update last used
        token.update_last_used()
        
        return token.user, None
        
    except AuthToken.DoesNotExist:
        return None, Response(
            {"detail": "Authentication failed due to invalid or missing AuthenticationToken"},
            status=403
        )


def require_auth(view_func):
    """
    Decorator to require authentication
    
    Usage:
        @api_view(["GET"])
        @require_auth
        def my_view(request):
            user = request.user  # User object available
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user, error_response = authenticate_user(request)
        
        if error_response:
            return error_response
        
        # Attach user to request
        request.user = user
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def require_admin(view_func):
    """
    Decorator to require admin privileges
    
    Usage:
        @api_view(["DELETE"])
        @require_admin
        def admin_only_view(request):
            # Only admins can access this
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user, error_response = authenticate_user(request)
        
        if error_response:
            return error_response
        
        if not user.is_admin:
            return Response(
                {"detail": "You do not have permission to perform this action"},
                status=401
            )
        
        # Attach user to request
        request.user = user
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def require_permission(permission_name):
    """
    Decorator to require specific permission
    
    Usage:
        @api_view(["POST"])
        @require_permission('can_upload')
        def upload_view(request):
            # Only users with upload permission can access
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user, error_response = authenticate_user(request)
            
            if error_response:
                return error_response
            
            permissions = user.get_permissions()
            
            if not permissions.get(permission_name, False):
                return Response(
                    {"detail": f"You do not have permission to perform this action (requires: {permission_name})"},
                    status=401
                )
            
            # Attach user to request
            request.user = user
            
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def optional_auth(view_func):
    """
    Decorator for optional authentication
    Attaches user if token provided, otherwise user is None
    
    Usage:
        @api_view(["GET"])
        @optional_auth
        def public_view(request):
            if hasattr(request, 'user') and request.user:
                # User is authenticated
                ...
            else:
                # Anonymous access
                ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user, _ = authenticate_user(request)
        
        if user:
            request.user = user
        else:
            request.user = None
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


# Helper functions for views

def check_artifact_access(user, artifact):
    """
    Check if user can access artifact
    
    Args:
        user: User object or None
        artifact: Artifact object
    
    Returns:
        tuple: (can_access: bool, error_response: Response or None)
    """
    # Public artifacts are accessible to all
    if artifact.is_public:
        return True, None
    
    # Anonymous users can't access private artifacts
    if not user:
        return False, Response(
            {"detail": "Authentication required to access this artifact"},
            status=403
        )
    
    # Check if user can access
    if not artifact.can_user_access(user):
        return False, Response(
            {"detail": "You do not have permission to access this artifact"},
            status=401
        )
    
    return True, None


def check_artifact_modify(user, artifact):
    """
    Check if user can modify artifact
    """
    if not user:
        return False, Response(
            {"detail": "Authentication required"},
            status=403
        )
    
    if not artifact.can_user_modify(user):
        return False, Response(
            {"detail": "You do not have permission to modify this artifact"},
            status=401
        )
    
    return True, None


def check_artifact_delete(user, artifact):
    """
    Check if user can delete artifact
    """
    if not user:
        return False, Response(
            {"detail": "Authentication required"},
            status=403
        )
    
    if not artifact.can_user_delete(user):
        return False, Response(
            {"detail": "You do not have permission to delete this artifact"},
            status=401
        )
    
    return True, None