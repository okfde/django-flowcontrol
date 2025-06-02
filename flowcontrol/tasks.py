from celery import shared_task


@shared_task
def continue_flowruns():
    from .engine import execute_flow_run
    from .models import FlowRun

    runnable = FlowRun.objects.get_runnable()

    for runnable_run in runnable:
        execute_flow_run(runnable_run)
