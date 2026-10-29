"""Turn the failures reported by the other apps into notifications."""

import datetime

from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext as _

from base.scheduler import job_failed
from base.services.mailer import email_failed
from notifications.registry import Event
from notifications.services import notify


@receiver(job_failed, dispatch_uid="notify-job-failed")
def _job_failed(sender, job, error, **kwargs):
    notify(
        "job_failed",
        Event(
            # One notification per job and day, however often it fails.
            key=f"{job.name}:{datetime.date.today().isoformat()}",
            title=_("Background job failed: %(job)s") % {"job": job.label},
            body=f"{type(error).__name__}: {error}"[:1000],
            url=f"{reverse('accounts:settings')}#background-jobs",
            level="danger",
        ),
    )


@receiver(email_failed, dispatch_uid="notify-email-failed")
def _email_failed(sender, email, **kwargs):
    notify(
        "email_failed",
        Event(
            key=str(email.pk),
            title=_("Email not sent: %(subject)s") % {"subject": email.subject},
            body=_("To %(to)s — %(error)s")
            % {"to": ", ".join(email.to), "error": email.error},
            level="danger",
        ),
    )
