from celery import shared_task


@shared_task
def continue_flowruns_task():
    from .engine import continue_flowruns

    continue_flowruns()
