from datetime import timedelta
from io import BytesIO

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone
from xhtml2pdf import pisa

from entries.reports import build_usage_report


class Command(BaseCommand):
    """Emails ADMIN_EMAIL a PDF usage report for the last N days.

    Not yet wired to any scheduler — run manually for now (`uv run manage.py send_usage_report`).
    To automate, point a periodic job (e.g. a Fly Machines schedule, or an external cron hitting
    `fly ssh console -C "python manage.py send_usage_report"`) at this command.
    """

    help = "Email ADMIN_EMAIL a PDF usage report covering the last N days (default 7)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7, help="Number of trailing days to report on (default 7).")

    def handle(self, *args, **options):
        days = options["days"]
        end_date = timezone.localdate()
        start_date = end_date - timedelta(days=days - 1)

        report = build_usage_report(start_date, end_date)

        html = render_to_string("admin/activity_report_pdf.html", {"report": report})
        buffer = BytesIO()
        pisa.CreatePDF(html, dest=buffer)

        subject = f"The Wax Tablet usage report: {start_date} to {end_date}"
        body = (
            f"Attached: feature usage totals, daily/weekly active-user trends, and a per-user "
            f"activity summary for {start_date} to {end_date}. No entry content included."
        )
        email = EmailMessage(subject, body, settings.DEFAULT_FROM_EMAIL, [settings.ADMIN_EMAIL])
        email.attach(f"wax_tablet_usage_report_{start_date}_{end_date}.pdf", buffer.getvalue(), "application/pdf")
        email.send()

        self.stdout.write(self.style.SUCCESS(f"Sent usage report ({start_date} to {end_date}) to {settings.ADMIN_EMAIL}"))
