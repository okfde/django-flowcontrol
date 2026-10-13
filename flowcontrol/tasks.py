from functools import partial

from django.db import transaction
from django.db.models import QuerySet

from celery import shared_task


@shared_task
def continue_flowruns_task():
    from .engine import continue_flowruns

    continue_flowruns()


@shared_task
def enqueue_flowruns_task():
    from .models import FlowRun

    runnable: QuerySet[FlowRun] = FlowRun.objects.get_runnable().select_for_update()
    with transaction.atomic():
        for runnable_run in runnable:
            status = runnable_run.status
            runnable_run.enqueue()
            transaction.on_commit(
                partial(execute_flowrun_task.delay, runnable_run.id, status)
            )


@shared_task
def execute_flowrun_task(flowrun_id, status):
    from .engine import execute_flowrun
    from .models import FlowRun

    try:
        flowrun = FlowRun.objects.get_enqueued().get(id=flowrun_id)
    except FlowRun.DoesNotExist:
        return

    flowrun.status = status
    flowrun.save(update_fields=["status"])
    execute_flowrun(flowrun)


@shared_task
def reset_flowruns_task(filter_params):
    from .engine import execute_on_filtered_flowrun_queryset, reset_flowrun

    execute_on_filtered_flowrun_queryset(reset_flowrun, filter_params=filter_params)


@shared_task
def restart_flowruns_with_current_action_task(filter_params):
    from .engine import (
        execute_on_filtered_flowrun_queryset,
        restart_flowrun_with_current_action,
    )

    execute_on_filtered_flowrun_queryset(
        restart_flowrun_with_current_action, filter_params=filter_params
    )


@shared_task
def restart_flowruns_with_next_action_task(filter_params):
    from .engine import (
        execute_on_filtered_flowrun_queryset,
        restart_flowrun_with_next_action,
    )

    execute_on_filtered_flowrun_queryset(
        restart_flowrun_with_next_action, filter_params=filter_params
    )
