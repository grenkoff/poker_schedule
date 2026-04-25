"""`manage.py promote_to_superadmin <identifier> [--create] [--email] [--password]`

Recovery escape hatch. Available only via shell access on the host, so
this is the path you take if every SUPERADMIN account is locked out.

Two modes:

  * **Promote existing user**: pass a username or email. The matching
    user gets `role=SUPERADMIN` and is saved.

  * **Create + promote**: pass `--create` plus `--email` (and optionally
    `--password`; if omitted, the command asks interactively).

Every invocation logs a `WARNING` so post-mortems can spot uses of this
command in the audit trail.
"""

from __future__ import annotations

import getpass
import logging
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

logger = logging.getLogger("apps.users.recovery")


class Command(BaseCommand):
    help = (
        "Promote an existing user (or create a new one) to SUPERADMIN. "
        "Use only as a recovery escape hatch when no SUPERADMIN can log in."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "identifier",
            help="username or email of the target user",
        )
        parser.add_argument(
            "--create",
            action="store_true",
            help="Create the user if no row matches the identifier.",
        )
        parser.add_argument(
            "--email",
            help="Email for --create. If omitted with --create and identifier is "
            "a username, the user is created with email = '<identifier>@local'.",
        )
        parser.add_argument(
            "--password",
            help="Password for --create. If omitted, prompted interactively. "
            "(Be aware this leaks into shell history if passed on the command line.)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        User = get_user_model()
        from apps.users.models import Role

        identifier: str = options["identifier"]
        do_create: bool = options["create"]
        email_opt: str | None = options.get("email")
        password_opt: str | None = options.get("password")

        # Resolve by username OR email — whichever matches first.
        user = User.objects.filter(Q(username=identifier) | Q(email=identifier)).first()

        if user is None:
            if not do_create:
                raise CommandError(
                    f"No user with username or email {identifier!r}. "
                    "Pass --create to make a new SUPERADMIN."
                )
            email = email_opt or (identifier if "@" in identifier else f"{identifier}@local")
            username = identifier if "@" not in identifier else identifier.split("@", 1)[0]
            password = password_opt or getpass.getpass("Password (will not echo): ")
            if not password:
                raise CommandError("Password is required when creating a new user.")
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                role=Role.SUPERADMIN,
            )
            logger.warning(
                "RECOVERY: created new SUPERADMIN '%s' via promote_to_superadmin",
                user.username,
            )
            self.stdout.write(self.style.SUCCESS(f"Created SUPERADMIN '{user.username}'."))
            return

        if user.role == Role.SUPERADMIN:
            self.stdout.write(
                self.style.WARNING(f"User '{user.username}' is already a SUPERADMIN. No change.")
            )
            return

        previous_role = user.role
        user.role = Role.SUPERADMIN
        user.save()
        logger.warning(
            "RECOVERY: promoted user '%s' (role %s -> superadmin) via promote_to_superadmin",
            user.username,
            previous_role,
        )
        self.stdout.write(
            self.style.SUCCESS(f"Promoted '{user.username}' from {previous_role} to SUPERADMIN.")
        )
