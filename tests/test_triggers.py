import pytest

from flowcontrol.engine import create_flowrun, trigger_flows


@pytest.mark.django_db
def test_trigger_flowrun(trigger):
    runs = trigger_flows(trigger.trigger)
    assert len(runs) == 1
    run = runs[0]
    assert run.flow == trigger.flow
    assert run.trigger == trigger


@pytest.mark.django_db
def test_trigger_flowrun_limited(trigger):
    flow = trigger.flow
    flow.max_concurrent = 1
    flow.save()
    run = create_flowrun(flow)
    assert run is not None

    runs = trigger_flows(trigger.trigger)
    assert len(runs) == 0
