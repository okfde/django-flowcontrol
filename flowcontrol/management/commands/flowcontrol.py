from collections import Counter

from django.core.management.base import BaseCommand, CommandParser

from ...engine import execute_flow_run
from ...models import FlowRun


class Command(BaseCommand):
    help = "Flowcontrol management command with subcommands"

    def add_arguments(self, parser: CommandParser):
        subparsers = parser.add_subparsers(dest="subcommand", help="Subcommands")
        # Add 'run' subcommand
        run_parser = subparsers.add_parser("run", help="Run the flowcontrol process")
        # You can add more arguments to 'run' here if needed

    def handle(self, *args, **options):
        subcommand = options.get("subcommand")
        if subcommand == "run":
            self.handle_run(options)
        else:
            self.stdout.write(self.style.ERROR("No valid subcommand provided."))

    def handle_run(self, options):
        runnable = FlowRun.objects.get_runnable()
        count = runnable.count()
        status_counter = Counter()
        outcome_counter = Counter()

        self.stdout.write(f"Executing {count} runnable flow runs...\n")

        for runnable_run in runnable:
            execute_flow_run(runnable_run)
            status_counter[runnable_run.status] += 1
            if runnable_run.outcome:
                outcome_counter[runnable_run.outcome] += 1

        self.stdout.write(self.style.SUCCESS("Finished executing runnable flow runs."))
        self.stdout.write(f"Status counts: {status_counter.most_common()}")
        self.stdout.write(f"Outcome counts: {outcome_counter.most_common()}")
