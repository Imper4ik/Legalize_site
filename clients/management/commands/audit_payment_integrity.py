from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from clients.services.payment_integrity import (
    audit_payment_integrity,
    payment_integrity_report_as_dict,
)


class Command(BaseCommand):
    help = "Check existing Payment rows before enforcing database payment constraints."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--sample-limit",
            type=int,
            default=20,
            help="Maximum payment ids to print per failed integrity rule.",
        )
        parser.add_argument(
            "--warn-only",
            action="store_true",
            help="Print failures without exiting non-zero.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print a machine-readable JSON report.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        sample_limit = int(options["sample_limit"])
        report = audit_payment_integrity(sample_limit=sample_limit)

        if options["json"]:
            self.stdout.write(json.dumps(payment_integrity_report_as_dict(report), indent=2))

        if report.table_missing:
            self.stdout.write(
                self.style.WARNING("Payment table does not exist yet; skipping integrity audit.")
            )
            return

        if report.is_valid:
            self.stdout.write(self.style.SUCCESS("Payment integrity audit passed."))
            return

        for issue in report.issues:
            sample_ids = ", ".join(str(pk) for pk in issue.sample_ids) or "none"
            self.stderr.write(
                f"{issue.code}: {issue.count} row(s). Sample payment ids: {sample_ids}"
            )

        message = (
            "Payment integrity audit failed. Clean these rows before applying "
            "payment database constraints."
        )
        if options["warn_only"]:
            self.stdout.write(self.style.WARNING(message))
            return
        raise CommandError(message)
