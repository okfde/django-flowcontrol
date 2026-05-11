from django.utils import timezone

import pytest

from flowcontrol.actions import WaitForTriggerAction
from flowcontrol.engine import create_flowrun, start_flowrun, trigger_flows
from flowcontrol.models.core import Trigger
from flowcontrol.utils import ActionNode, make_action_tree


@pytest.fixture
def conditional_trigger(flow):
    return Trigger.objects.create(
        flow=flow,
        trigger="trigger_name",
        active_at=timezone.now(),
        condition="object.username == 'example'",
    )


@pytest.mark.django_db
def test_trigger_flowrun(trigger):
    runs = trigger_flows(trigger.trigger)
    assert len(runs) == 1
    run = runs[0]
    assert run.flow == trigger.flow
    assert run.trigger == trigger


@pytest.mark.django_db
def test_conditional_trigger_flowrun(conditional_trigger, user):
    runs = trigger_flows(conditional_trigger.trigger, obj=user)
    assert len(runs) == 0
    user.username = "example"
    runs = trigger_flows(conditional_trigger.trigger, obj=user)
    assert len(runs) == 1


@pytest.mark.django_db
def test_trigger_flowrun_limited(trigger):
    flow = trigger.flow
    flow.max_concurrent = 1
    flow.save()
    run = create_flowrun(flow)
    assert run is not None

    runs = trigger_flows(trigger.trigger)
    assert len(runs) == 0


@pytest.mark.django_db
def test_wait_for_trigger_scheduled(flow, wait_trigger):
    make_action_tree(
        flow,
        [
            ActionNode(WaitForTriggerAction, {"trigger": wait_trigger}),
        ],
    )
    started_run = start_flowrun(flow)
    assert started_run
    assert started_run.status == started_run.Status.WAITING
    assert started_run.waiting_trigger == wait_trigger
    assert started_run.continue_after is None
    runs = trigger_flows(wait_trigger.trigger)
    assert len(runs) == 1
    run = runs[0]
    assert run.waiting_trigger is None
    assert run.continue_after is not None


@pytest.mark.django_db
def test_wait_for_trigger_immediate(flow, wait_trigger):
    make_action_tree(
        flow,
        [
            ActionNode(WaitForTriggerAction, {"trigger": wait_trigger}),
        ],
    )
    started_run = start_flowrun(flow)
    assert started_run
    assert started_run.status == started_run.Status.WAITING
    assert started_run.waiting_trigger == wait_trigger
    assert started_run.continue_after is None

    runs = trigger_flows(wait_trigger.trigger, immediate=True)
    assert len(runs) == 1
    run = runs[0]
    assert run.waiting_trigger is None
    assert run.continue_after is None
    assert run.status == run.Status.DONE


@pytest.mark.django_db
def test_wait_for_trigger_object_immediate(flow, wait_trigger, user, admin_user):
    make_action_tree(
        flow,
        [
            ActionNode(
                WaitForTriggerAction, {"trigger": wait_trigger, "require_object": True}
            ),
        ],
    )
    started_run = start_flowrun(flow, obj=user)
    assert started_run
    assert started_run.status == started_run.Status.WAITING
    assert started_run.waiting_trigger == wait_trigger
    assert started_run.continue_after is None

    runs = trigger_flows(wait_trigger.trigger, obj=admin_user, immediate=True)
    assert len(runs) == 0

    runs = trigger_flows(wait_trigger.trigger, obj=user, immediate=True)
    assert len(runs) == 1
    run = runs[0]
    assert run.waiting_trigger is None
    assert run.continue_after is None
    assert run.status == run.Status.DONE
