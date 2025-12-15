"""
api/auth.py

Authentication Middleware and Decorators

Provides:
- Authentication decorators
- Permission checking
- Token validation
"""
import logging
from functools import wraps
from rest_framework.response import Response
from rest_framework.decorators import api_view
from .models import User, AuthToken

logger = logging.getLogger(__name__)


def authenticate_user(request):
    """
    Authenticate user from X-Authorization or Authorization header

    Returns:
        tuple: (user, error_response)
        - If successful: (User object, None)
        - If failed: (None, Response object with error)
    """
    # Check both X-Authorization and Authorization headers
    auth_token = request.headers.get('X-Authorization') or request.headers.get('Authorization')

    # DEBUG: Log what we received
    logger.info(f"=== AUTH DEBUG ===")
    logger.info(f"X-Authorization header: {request.headers.get('X-Authorization')}")
    logger.info(f"Authorization header: {request.headers.get('Authorization')}")
    logger.info(f"auth_token: '{auth_token}'")

    # Don't strip the prefix - we store tokens with "bearer " in the database
    # The token should be looked up exactly as received
    logger.info(f"Using token as-is (no stripping) for database lookup")

    if not auth_token:
        logger.warning("No auth token provided")
        return None, Response(
            {"detail": "Authentication failed due to invalid or missing AuthenticationToken"},
            status=403
        )
    
    try:
        # Find token in database
        logger.info(f"Looking up token in database: '{auth_token[:20]}...' (length={len(auth_token)})")
        token = AuthToken.objects.select_related('user').get(token=auth_token)
        
        # Check if token is valid
        if not token.is_valid():
            logger.warning(f"Token found but expired for user: {token.user.name}")
            return None, Response(
                {"detail": "Authentication failed due to invalid or missing AuthenticationToken"},
                status=403
            )
        
        # Update last used
        token.update_last_used()
        
        logger.info(f"✓ Authentication successful for user: {token.user.name} (is_admin={token.user.is_admin})")
        return token.user, None
        
    except AuthToken.DoesNotExist:
        logger.warning(f"✗ Token not found in database: '{auth_token[:20]}...'")
        # DEBUG: Show what tokens ARE in the database
        all_tokens = AuthToken.objects.all()
        logger.info(f"Available tokens in DB ({all_tokens.count()}): {[t.token[:30]+'...' for t in all_tokens[:5]]}")
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