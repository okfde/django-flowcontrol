from unittest.mock import Mock

from flowcontrol.models import FlowRun
from flowcontrol.tasks import (
    continue_flowruns_task,
    enqueue_flowruns_task,
    execute_flowrun_task,
)


def test_enqueue_flowruns_task(flowrun, monkeypatch):
    mock = Mock()
    monkeypatch.setattr(execute_flowrun_task, "delay", mock)

    enqueue_flowruns_task()
    assert mock.assert_called_with(flowrun.id, FlowRun.Status.PENDING) is None
    flowrun.refresh_from_db()
    assert flowrun.status == FlowRun.Status.ENQUEUED
    execute_flowrun_task(flowrun.id, FlowRun.Status.PENDING)
    flowrun.refresh_from_db()
    assert flowrun.status == FlowRun.Status.DONE


def test_continue_flowruns_task(flowrun):
    assert flowrun.status == FlowRun.Status.PENDING
    continue_flowruns_task()
    flowrun.refresh_from_db()
    assert flowrun.status == FlowRun.Status.DONE
