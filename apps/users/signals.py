"""Signal wiring for role-change audit.

`pre_save` snapshots the prior role onto the instance so `post_save` can
diff. We deliberately use both halves rather than a single `post_save`
that re-queries: the pre/post pair handles both edits and creates with
no extra query.
"""

from __future__ import annotations

from typing import Any

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .audit_context import client_ip_from, get_current_request
from .models import AuditSource, RoleChangeAudit, User

_AUDIT_PRIOR_ATTR = "_audit_prior_role"


@receiver(pre_save, sender=User)
def snapshot_prior_role(sender, instance: User, **kwargs: Any) -> None:
    if instance.pk:
        prior = User.objects.filter(pk=instance.pk).only("role").first()
        setattr(instance, _AUDIT_PRIOR_ATTR, prior.role if prior else "")
    else:
        setattr(instance, _AUDIT_PRIOR_ATTR, "")


@receiver(post_save, sender=User)
def write_role_audit(sender, instance: User, created: bool, **kwargs: Any) -> None:
    prior = getattr(instance, _AUDIT_PRIOR_ATTR, "")
    if not created and prior == instance.role:
        return  # nothing to record

    request = get_current_request()
    actor: User | None = None
    ua = ""
    ip: str | None = None
    source = AuditSource.CLI
    if request is not None:
        if getattr(request.user, "is_authenticated", False):
            actor = request.user  # type: ignore[assignment]
        ua = request.META.get("HTTP_USER_AGENT", "")[:512]
        ip = client_ip_from(request)
        source = AuditSource.ADMIN if request.path.startswith("/admin/") else AuditSource.SIGNUP

    # Don't audit-self (changed_by can equal the target — that's fine for
    # signups, where the user creates themselves through allauth).
    RoleChangeAudit.objects.create(
        user=instance,
        old_role=prior,
        new_role=instance.role,
        changed_by=actor,
        source=source,
        ip_address=ip,
        user_agent=ua,
    )
