"""
api/management/commands/setup_auth.py

Django Management Command: setup_auth

Usage:
    python manage.py setup_auth
    
Creates:
- Default user groups (admin, user)
- Default admin user (ece30861defaultadminuser)
"""
from django.core.management.base import BaseCommand
from api.models import User, UserGroup


class Command(BaseCommand):
    help = 'Setup authentication system with default admin user and groups'

    def handle(self, *args, **kwargs):
        self.stdout.write('=' * 70)
        self.stdout.write('Setting up authentication system...')
        self.stdout.write('=' * 70)
        
        # Create admin group
        admin_group, created = UserGroup.objects.get_or_create(
            name='admin',
            defaults={
                'description': 'Administrators with full access to all features',
                'can_upload': True,
                'can_download': True,
                'can_search': True,
                'can_rate': True,
                'can_delete_any': True,
                'can_reset_registry': True,
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS('Created admin group'))
        else:
            self.stdout.write('  Admin group already exists')
        
        # Create user group
        user_group, created = UserGroup.objects.get_or_create(
            name='user',
            defaults={
                'description': 'Regular users with standard permissions',
                'can_upload': True,
                'can_download': True,
                'can_search': True,
                'can_rate': True,
                'can_delete_any': False,
                'can_reset_registry': False,
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS('Created user group'))
        else:
            self.stdout.write('  User group already exists')
        
        # Create default admin user
        admin_user, created = User.objects.get_or_create(
            name='ece30861defaultadminuser',
            defaults={
                'is_admin': True,
                'is_active': True,
                'group': admin_group,
            }
        )
        
        if created:
            # Set the password from spec example
            admin_user.set_password(
                "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"
            )
            admin_user.save()
            
            self.stdout.write(self.style.SUCCESS(
                '\nCreated default admin user'
            ))
            self.stdout.write(f'  Username: {admin_user.name}')
            self.stdout.write(f'  Password: (from spec example)')
            self.stdout.write(f'  Is Admin: {admin_user.is_admin}')
        else:
            self.stdout.write('\n  Admin user already exists')
            self.stdout.write(f'  Username: {admin_user.name}')
            self.stdout.write(f'  Is Admin: {admin_user.is_admin}')
            self.stdout.write(f'  Is Active: {admin_user.is_active}')
        
        # Summary
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.SUCCESS('Authentication setup complete!'))
        self.stdout.write('=' * 70)
        
        # Show stats
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        admin_users = User.objects.filter(is_admin=True).count()
        
        self.stdout.write(f'\nCurrent statistics:')
        self.stdout.write(f'  Total users: {total_users}')
        self.stdout.write(f'  Active users: {active_users}')
        self.stdout.write(f'  Admin users: {admin_users}')
