from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType

import pytest

from flowcontrol.engine import (
    abort_flowrun,
    cancel_flowrun,
    cancel_flowruns_for_object,
    continue_flowruns,
    create_flowrun,
    discard_flowrun,
    error_flowrun,
    start_flowrun,
)
from flowcontrol.models import FlowRun


@pytest.mark.django_db
def test_create_flowrun(flow, user):
    run = create_flowrun(flow, user)
    assert isinstance(run, FlowRun)
    assert run.flow == flow
    assert run.content_object == user


@pytest.mark.django_db
def test_start_flowrun(flow, user):
    run = start_flowrun(flow, user)
    assert isinstance(run, FlowRun)
    assert run.status == FlowRun.Status.DONE or run.status == FlowRun.Status.PENDING


@pytest.mark.django_db
def test_start_flowrun_flow_condition_false(flow, user):
    flow.condition = 'object.id == "foobar"'
    run = start_flowrun(flow, user)
    assert isinstance(run, FlowRun)
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.OBSOLETE
    assert "Discarded because flow condition" in run.log


@pytest.mark.django_db
def test_start_flowrun_flow_condition_true(flow, user):
    user.username = "foobar"
    user.save()
    flow.condition = 'object.username == "foobar"'
    run = start_flowrun(flow, user)
    assert isinstance(run, FlowRun)
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.COMPLETE
    assert run.log == ""


@pytest.mark.django_db
def test_start_flowrun_flow_content_type(flow, user):
    flow.content_type = ContentType.objects.get_for_model(Group)
    run = start_flowrun(flow, user)
    assert run is None
    flow.content_type = ContentType.objects.get_for_model(user)
    run = start_flowrun(flow, user)
    assert run is not None


@pytest.mark.django_db
def test_discard_flowrun(flowrun):
    discard_flowrun(flowrun)
    assert flowrun.status == FlowRun.Status.DONE
    assert flowrun.outcome == FlowRun.Outcome.OBSOLETE


@pytest.mark.django_db
def test_abort_flowrun(flowrun):
    abort_flowrun(flowrun)
    assert flowrun.status == FlowRun.Status.DONE
    assert flowrun.outcome == FlowRun.Outcome.ABORTED


@pytest.mark.django_db
def test_error_flowrun(flowrun):
    error_flowrun(flowrun, message="error!")
    assert flowrun.status == FlowRun.Status.DONE
    assert flowrun.outcome == FlowRun.Outcome.ERRORED
    assert "error!" in flowrun.log


@pytest.mark.django_db
def test_cancel_flowrun(flowrun):
    cancel_flowrun(flowrun)
    assert flowrun.status == FlowRun.Status.DONE
    assert flowrun.outcome == FlowRun.Outcome.CANCELED


@pytest.mark.django_db
def test_cancel_flowrun_with_object(flow, user):
    flowrun = create_flowrun(flow, user)
    cancel_flowruns_for_object(user)
    flowrun.refresh_from_db()
    assert flowrun.status == FlowRun.Status.DONE
    assert flowrun.outcome == FlowRun.Outcome.CANCELED


@pytest.mark.django_db
def test_continue_flowrun(flow, user):
    flowrun = create_flowrun(flow)
    assert flowrun.status == FlowRun.Status.PENDING
    continue_flowruns()
    flowrun.refresh_from_db()
    assert flowrun.status == FlowRun.Status.DONE
    assert flowrun.outcome == FlowRun.Outcome.COMPLETE
