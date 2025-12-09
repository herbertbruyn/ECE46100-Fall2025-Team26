"""
api/auth_views.py

Authentication Views

Implements:
- PUT /authenticate - Login and get token
- POST /users - Create new user (admin only)
- GET /users - List users (admin only)
"""
import logging
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db import transaction

from .models import User, AuthToken, UserGroup
from .auth import require_admin, authenticate_user

logger = logging.getLogger(__name__)


@api_view(["PUT"])
def authenticate(request):
    """
    PUT /authenticate
    
    Authenticate user and return access token.
    
    Request body:
    {
        "user": {
            "name": "username",
            "is_admin": true
        },
        "secret": {
            "password": "password123"
        }
    }
    
    Returns:
        200: Authentication token (bearer token)
        400: Missing fields or malformed request
        401: Invalid credentials
        501: Authentication not implemented (if you want to disable it)
    """
    # Uncomment this to disable authentication
    # return Response({"detail": "This system does not support authentication"}, status=501)
    
    try:
        # Parse request body
        data = request.data
        
        if not data:
            return Response(
                {"detail": "There is missing field(s) in the AuthenticationRequest or it is formed improperly."},
                status=400
            )
        
        user_data = data.get('user', {})
        secret_data = data.get('secret', {})
        
        username = user_data.get('name')
        password = secret_data.get('password')
        
        if not username or not password:
            return Response(
                {"detail": "There is missing field(s) in the AuthenticationRequest or it is formed improperly."},
                status=400
            )
        
        # Find user
        try:
            user = User.objects.get(name=username)
        except User.DoesNotExist:
            logger.warning(f"Authentication failed: user '{username}' not found")
            return Response(
                {"detail": "The user or password is invalid."},
                status=401
            )
        
        # Check if user is active
        if not user.is_active:
            logger.warning(f"Authentication failed: user '{username}' is inactive")
            return Response(
                {"detail": "The user or password is invalid."},
                status=401
            )
        
        # Verify password
        if not user.check_password(password):
            logger.warning(f"Authentication failed: invalid password for user '{username}'")
            return Response(
                {"detail": "The user or password is invalid."},
                status=401
            )
        
        # Check is_admin matches (optional strict check)
        expected_is_admin = user_data.get('is_admin', False)
        if expected_is_admin != user.is_admin:
            logger.warning(f"Authentication failed: is_admin mismatch for user '{username}'")
            return Response(
                {"detail": "The user or password is invalid."},
                status=401
            )
        
        # Generate token
        token = AuthToken.generate_token(user, expires_in_hours=24)
        
        # Update last login
        user.update_last_login()
        
        logger.info(f"User '{username}' authenticated successfully")
        
        # Return token as string (wrapped in quotes as per spec)
        return Response(token, status=200)
        
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}", exc_info=True)
        return Response(
            {"detail": "There is missing field(s) in the AuthenticationRequest or it is formed improperly."},
            status=400
        )


@api_view(["POST"])
@require_admin
def create_user(request):
    """
    POST /users (admin only)
    
    Create a new user.
    
    Request body:
    {
        "name": "username",
        "password": "password123",
        "is_admin": false
    }
    """
    try:
        data = request.data
        
        username = data.get('name')
        password = data.get('password')
        is_admin = data.get('is_admin', False)
        
        if not username or not password:
            return Response(
                {"detail": "Missing required fields: name, password"},
                status=400
            )
        
        # Check if user already exists
        if User.objects.filter(name=username).exists():
            return Response(
                {"detail": f"User '{username}' already exists"},
                status=409
            )
        
        # Get appropriate group
        if is_admin:
            group = UserGroup.objects.get(name='admin')
        else:
            group = UserGroup.objects.get(name='user')
        
        # Create user
        user = User.objects.create(
            name=username,
            is_admin=is_admin,
            is_active=True,
            group=group
        )
        user.set_password(password)
        user.save()
        
        logger.info(f"User '{username}' created by '{request.user.name}'")
        
        return Response({
            "detail": "User created successfully",
            "user": {
                "name": user.name,
                "is_admin": user.is_admin,
                "created_at": user.created_at.isoformat()
            }
        }, status=201)
        
    except Exception as e:
        logger.error(f"User creation error: {str(e)}", exc_info=True)
        return Response(
            {"detail": f"Failed to create user: {str(e)}"},
            status=500
        )


@api_view(["GET"])
@require_admin
def list_users(request):
    """
    GET /users (admin only)
    
    List all users.
    """
    users = User.objects.all().select_related('group')
    
    user_list = [
        {
            "name": user.name,
            "is_admin": user.is_admin,
            "is_active": user.is_active,
            "group": user.group.name if user.group else None,
            "created_at": user.created_at.isoformat(),
            "last_login": user.last_login.isoformat() if user.last_login else None,
        }
        for user in users
    ]
    
    return Response(user_list, status=200)


@api_view(["DELETE"])
@require_admin
def delete_user(request, username):
    """
    DELETE /users/{username} (admin only)
    
    Delete a user.
    """
    try:
        user = User.objects.get(name=username)
        
        # Prevent deleting yourself
        if user.name == request.user.name:
            return Response(
                {"detail": "You cannot delete yourself"},
                status=400
            )
        
        # Delete user (cascade will delete tokens)
        user.delete()
        
        logger.info(f"User '{username}' deleted by '{request.user.name}'")
        
        return Response(
            {"detail": f"User '{username}' deleted successfully"},
            status=200
        )
        
    except User.DoesNotExist:
        return Response(
            {"detail": f"User '{username}' not found"},
            status=404
        )


@api_view(["PUT"])
def change_password(request):
    """
    PUT /users/password
    
    Change own password.
    
    Request body:
    {
        "old_password": "current_password",
        "new_password": "new_password"
    }
    """
    user, error_response = authenticate_user(request)
    if error_response:
        return error_response
    
    try:
        data = request.data
        old_password = data.get('old_password')
        new_password = data.get('new_password')
        
        if not old_password or not new_password:
            return Response(
                {"detail": "Missing required fields: old_password, new_password"},
                status=400
            )
        
        # Verify old password
        if not user.check_password(old_password):
            return Response(
                {"detail": "Old password is incorrect"},
                status=401
            )
        
        # Set new password
        user.set_password(new_password)
        user.save()
        
        # Invalidate all existing tokens (force re-login)
        AuthToken.objects.filter(user=user).delete()
        
        logger.info(f"Password changed for user '{user.name}'")
        
        return Response(
            {"detail": "Password changed successfully. Please login again."},
            status=200
        )
        
    except Exception as e:
        logger.error(f"Password change error: {str(e)}", exc_info=True)
        return Response(
            {"detail": f"Failed to change password: {str(e)}"},
            status=500
        )


@api_view(["POST"])
@require_admin
def cleanup_tokens(request):
    """
    POST /tokens/cleanup (admin only)
    
    Remove expired tokens.
    """
    count = AuthToken.cleanup_expired()
    
    return Response({
        "detail": f"Cleaned up {count} expired tokens"
    }, status=200)