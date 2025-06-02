import inspect

from django.utils import timezone

import pytest

# Make sure to import the actions to register them
import flowcontrol.actions  # noqa: F401
from flowcontrol.base import BaseAction
from flowcontrol.models.core import FlowRun, Trigger
from flowcontrol.registry import (
    register_action,
    register_trigger,
    register_trigger_as_signal_handler,
)


def test_duplicate_action():
    class IfAction(BaseAction):
        pass

    with pytest.raises(ValueError, match="Action IfAction is already registered"):
        register_action(IfAction)


def test_action_with_no_name():
    class SomeAction(BaseAction):
        name = ""

    with pytest.raises(ValueError, match="Action name cannot be empty"):
        register_action(SomeAction)


def test_action_with_name_too_long():
    class SomeAction(BaseAction):
        name = "a" * 101

    with pytest.raises(
        ValueError, match="Action name is too long, must be less than 101 characters"
    ):
        register_action(SomeAction)


def test_duplicate_trigger(temp_registry):
    register_trigger("some_name")

    with pytest.raises(ValueError, match="Trigger some_name is already registered"):
        register_trigger("some_name")


def test_trigger_with_no_name():
    with pytest.raises(ValueError, match="Trigger name cannot be empty"):
        register_trigger("")


def test_trigger_withname_too_long():
    with pytest.raises(
        ValueError, match="Trigger name is too long, must be less than 101 characters"
    ):
        register_trigger("a" * 101)


@pytest.mark.django_db
def test_trigger_register_function(temp_registry, flow, user):
    trigger_name = "some_name"
    trigger_func = register_trigger(trigger_name)
    assert callable(trigger_func)

    trigger_func()

    assert FlowRun.objects.all().count() == 0

    trigger = Trigger.objects.create(
        flow=flow,
        trigger=trigger_name,
        active_at=timezone.now(),
    )
    trigger_func()

    run = FlowRun.objects.filter(flow=flow, trigger=trigger).get()
    assert run.status == FlowRun.Status.PENDING
    assert run.content_object is None
    run.delete()

    trigger_func(obj=user, state={"foo": "bar"}, immediate=True)

    run = FlowRun.objects.filter(flow=flow, trigger=trigger).get()
    assert run.state == {"foo": "bar"}
    assert run.content_object == user
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.COMPLETE


@pytest.mark.django_db
def test_trigger_register_signal(temp_registry, flow, user):
    trigger_name = "some_name"
    trigger_func = register_trigger_as_signal_handler(trigger_name)
    assert callable(trigger_func)

    with pytest.raises(TypeError):
        trigger_func()

    # Check if the function accepts the correct parameters
    sig = inspect.signature(trigger_func)

    assert "sender" in sig.parameters
    assert "kwargs" in sig.parameters

    trigger_func(sender=user)

    assert FlowRun.objects.all().count() == 0
