import logging

from django.core.management import call_command
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Generate a fixture "

    def handle(self, *args, **options):
        call_command("migrate")
        call_command(
            "provisiondevice",
            facility="Test",
            superusername="test",
            superuserpassword="test",
            preset="formal",
            language_id="en",
            noinput=True,
        )
        call_command("generateuserdata")
        call_command("dumpdata")
