import pytest

from flowcontrol.engine import (
    abort_flowrun,
    create_flow_run,
    discard_flowrun,
    error_flowrun,
    start_flow_run,
)
from flowcontrol.models import FlowRun


@pytest.mark.django_db
def test_create_flow_run(flow, user):
    run = create_flow_run(flow, user)
    assert isinstance(run, FlowRun)
    assert run.flow == flow
    assert run.content_object == user


@pytest.mark.django_db
def test_start_flow_run(flow, user):
    run = start_flow_run(flow, user)
    assert isinstance(run, FlowRun)
    assert run.status == FlowRun.Status.DONE or run.status == FlowRun.Status.PENDING


@pytest.mark.django_db
def test_discard_flowrun(flow_run):
    discard_flowrun(flow_run)
    assert flow_run.status == FlowRun.Status.DONE
    assert flow_run.outcome == FlowRun.Outcome.OBSOLETE


@pytest.mark.django_db
def test_abort_flowrun(flow_run):
    abort_flowrun(flow_run)
    assert flow_run.status == FlowRun.Status.DONE
    assert flow_run.outcome == FlowRun.Outcome.ABORTED


@pytest.mark.django_db
def test_error_flowrun(flow_run):
    error_flowrun(flow_run, message="error!")
    assert flow_run.status == FlowRun.Status.DONE
    assert flow_run.outcome == FlowRun.Outcome.ERRORED
    assert "error!" in flow_run.log
