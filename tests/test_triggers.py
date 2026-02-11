from django.utils import timezone

import pytest

from flowcontrol.engine import create_flowrun, trigger_flows
from flowcontrol.models.core import Trigger


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
