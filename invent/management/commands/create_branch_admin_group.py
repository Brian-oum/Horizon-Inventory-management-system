"""
Create 'Branch Admin' group and attach model permissions suitable for branch-level admins.

Run:
    python manage.py create_branch_admin_group
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.apps import apps

# Models to grant basic CRUD/view permissions for branch admins.
MODELS_TO_GRANT = [
    'device',
    'devicerequest',
    'issuancerecord',
    'returnrecord',
    'purchaseorder',
    'client',
    'oem',
    'branch',
]

class Command(BaseCommand):
    help = "Create 'Branch Admin' group and attach appropriate permissions."

    def handle(self, *args, **options):
        group_name = "Branch Admin"
        group, created = Group.objects.get_or_create(name=group_name)
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created group '{group_name}'"))
        else:
            self.stdout.write(self.style.NOTICE(f"Group '{group_name}' already exists"))

        added = 0
        for model_label in MODELS_TO_GRANT:
            try:
                model = apps.get_model('invent', model_label)
            except LookupError:
                self.stdout.write(self.style.WARNING(f"Model 'invent.{model_label}' not found — skipping"))
                continue

            ct = ContentType.objects.get_for_model(model)
            perms = Permission.objects.filter(content_type=ct)
            for p in perms:
                if p.codename.startswith(('add_', 'change_', 'delete_', 'view_')):
                    if p not in group.permissions.all():
                        group.permissions.add(p)
                        added += 1

        group.save()
        self.stdout.write(self.style.SUCCESS(f"Added {added} permissions to group '{group_name}'"))
        self.stdout.write(self.style.SUCCESS("Done. Assign users to the 'Branch Admin' group and set their Profile.branch."))