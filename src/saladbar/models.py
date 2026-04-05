from django.db import models


class SaladBarPermissions(models.Model):
    """Unmanaged model solely for defining saladbar permissions."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("can_view_saladbar", "Can view Salad Bar dashboard"),
            ("can_manage_saladbar", "Can manage tasks and purge queues"),
        ]
