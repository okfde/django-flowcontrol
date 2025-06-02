from datetime import datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

import pytest
from dateutil.parser import parse

from flowcontrol.actions import (
    AbortAction,
    DelayAction,
    ForLoopAction,
    IfAction,
    SetStateAction,
    StartFlowAction,
    UpdateStateAction,
    WhileLoopAction,
)
from flowcontrol.base import BaseAction, FlowDirective
from flowcontrol.models import Flow, FlowRun
from flowcontrol.models.config import Condition, Delay, ForLoop, StartFlow, State


@pytest.fixture
def run(flow):
    return FlowRun(flow=flow)


def test_base_action():
    action = BaseAction()
    with pytest.raises(NotImplementedError):
        action.run(obj=None, run=None, config=None)

    result = action.return_from_children(obj=None, run=None, config=None)
    assert result is None
    action.has_children = True

    with pytest.raises(NotImplementedError):
        action.return_from_children(obj=None, run=None, config=None)


def test_if_action_empty_condition(run):
    condition = Condition(condition="")
    action = IfAction()
    action._set_context(run.state.copy())
    directive = action.run(obj=None, run=run, config=condition)
    assert directive == FlowDirective.CONTINUE


def test_if_action_true_condition(run):
    condition = Condition(condition="True")
    action = IfAction()
    action._set_context(run.state.copy())
    directive = action.run(obj=None, run=run, config=condition)
    assert directive == FlowDirective.ENTER


def test_if_action_false_condition(run):
    condition = Condition(condition="False")
    action = IfAction()
    action._set_context(run.state.copy())
    directive = action.run(obj=None, run=run, config=condition)
    assert directive == FlowDirective.CONTINUE


def test_if_action_context_condition(run):
    condition = Condition(condition="foo == 'bar'")
    action = IfAction()
    action._set_context(run.state.copy())
    directive = action.run(obj=None, run=run, config=condition)
    assert directive == FlowDirective.CONTINUE

    action._set_context({"foo": "bad"})
    directive = action.run(obj=None, run=run, config=condition)
    assert directive == FlowDirective.CONTINUE

    action._set_context({"foo": "bar"})
    directive = action.run(obj=None, run=run, config=condition)
    assert directive == FlowDirective.ENTER


def test_delay_action_sets_continue_after(run):
    now = timezone.now()
    serialized = now.isoformat()
    delta = timezone.timedelta(seconds=65)
    delay = Delay(seconds=delta, base_date_template=f"'{serialized}'")

    action = DelayAction()
    action._set_context(run.state.copy())
    directive = action.run(obj=None, run=run, config=delay)
    assert directive == FlowDirective.SUSPEND
    assert run.continue_after == now + delta


@pytest.mark.parametrize(
    "action_if_past,is_past",
    [
        (FlowDirective.SUSPEND, True),
        (FlowDirective.LEAVE, True),
        (FlowDirective.BREAK, True),
        (FlowDirective.ABORT, True),
        (FlowDirective.SUSPEND, False),
        (FlowDirective.LEAVE, False),
        (FlowDirective.BREAK, False),
        (FlowDirective.ABORT, False),
    ],
)
def test_delay_is_in_past(run, action_if_past, is_past):
    timestamp = timezone.now()
    if is_past:
        timestamp -= timedelta(seconds=20)
    serialized = timestamp.isoformat()
    delta = timezone.timedelta(seconds=5)
    delay = Delay(
        seconds=delta,
        action_if_past=action_if_past,
        base_date_template=f"'{serialized}'",
    )

    action = DelayAction()
    action._set_context(run.state.copy())
    directive = action.run(obj=None, run=run, config=delay)
    if is_past:
        assert directive == FlowDirective(action_if_past)
    else:
        assert directive == FlowDirective.SUSPEND
    assert run.continue_after == timestamp + delta


@pytest.mark.parametrize(
    "key,val,expected",
    [
        ("seconds", timedelta(seconds=30), "30\xa0seconds"),
        ("seconds", timedelta(seconds=61), "1\xa0minute, 1\xa0second"),
        ("seconds", timedelta(seconds=60 * 60 + 5), "1\xa0hour, 5\xa0seconds"),
        ("months", 2, "after 2 month(s)"),
        ("weekday", 0, "on Monday"),
        ("weekday", 6, "on Sunday"),
        ("time", time(hour=5), "at 05:00"),
        (
            "base_date_template",
            "'2025-01-29T00:00:00Z'",
            "'2025-01-29T00:00:00Z': No delay set.",
        ),
    ],
)
def test_delay_representation(key, val, expected):
    delay = Delay(**{key: val})
    assert str(delay) == expected


@pytest.mark.parametrize(
    "deltas,expected",
    [
        ({"seconds": timedelta(seconds=30)}, "2025-01-29T00:00:30Z"),
        ({"seconds": timedelta(seconds=61)}, "2025-01-29T00:01:01Z"),
        ({"seconds": timedelta(seconds=60 * 60 + 5)}, "2025-01-29T01:00:05Z"),
        ({"months": 1}, "2025-02-28T00:00:00Z"),
        ({"weekday": 0}, "2025-02-03T00:00:00Z"),
        ({"weekday": 6}, "2025-02-02T00:00:00Z"),
        ({"time": time(hour=5, minute=29)}, "2025-01-29T05:29:00Z"),
        (
            {
                "months": 2,
                "seconds": timedelta(seconds=60 * 60 * 24 * 7),
                "weekday": 0,
                "time": time(hour=5, minute=29),
            },
            "2025-04-07T05:29:00Z",
        ),
    ],
)
def test_delay_timedelta(deltas, expected):
    base_date = parse("2025-01-29T00:00:00Z")
    delay = Delay(**deltas)

    resulting_date = delay.apply_timedelta(base_date)
    assert resulting_date == parse(expected)


def test_delay_bad_base_template():
    delay = Delay(base_date_template="foo")

    with pytest.raises(
        ValueError, match="Base date must be a datetime or a parsable string"
    ):
        delay.calculate_delay({"foo": 1})


def test_abort_action(run):
    action = AbortAction()
    action._set_context(run.state.copy())
    directive = action.run(obj=None, run=run, config=None)
    assert directive == FlowDirective.ABORT


def test_set_state_action(run):
    run.state = {"foo": "bar", "_internal": "baz"}
    state = State(state={"foo": "bar"})
    action = SetStateAction()
    action._set_context(run.state.copy())
    directive = action.run(obj=None, run=run, config=state)
    assert directive == FlowDirective.CONTINUE
    assert run.state["foo"] == "bar"
    assert run.state["_internal"] == "baz"


def test_set_state_action_evaluate(run):
    run.state = {"foo": "bar", "_internal": "baz"}
    state = State(state={"foo": "foo|add:'bar'"}, evaluate=True)
    action = SetStateAction()
    action._set_context(run.state.copy())
    directive = action.run(obj=None, run=run, config=state)
    assert directive == FlowDirective.CONTINUE
    assert run.state["foo"] == "barbar"
    assert run.state["_internal"] == "baz"


def test_update_state_action(run):
    run.state = {"foo": "bar"}
    state = State(state={"baz": "qux"})
    action = UpdateStateAction()
    action._set_context(run.state.copy())
    directive = action.run(obj=None, run=run, config=state)
    assert directive == FlowDirective.CONTINUE
    assert run.state["baz"] == "qux"
    assert run.state["foo"] == "bar"


def test_empty_for_loop_action(run):
    loop = ForLoop(var_name="i", start=0, end=0, step=1)
    action = ForLoopAction()
    action._set_context(run.state.copy())
    directive = action.run(obj=None, run=run, config=loop)
    assert directive == FlowDirective.CONTINUE
    assert "i" not in run.state


def test_forloop_missing_var(run):
    loop = ForLoop(var_name="i", start=0, end=3, step=1)
    action = ForLoopAction()
    action._set_context(run.state.copy())
    directive = action.run(obj=None, run=run, config=loop)
    assert directive == FlowDirective.ENTER
    assert run.state["i"] == 0

    # Corrupt run state
    del run.state["i"]

    with pytest.raises(KeyError):
        action.return_from_children(obj=None, run=run, config=loop)


def test_for_loop_action(run):
    loop = ForLoop(var_name="i", start=0, end=3, step=1)
    assert str(loop) == "i: 0 to 3 with step 1"
    action = ForLoopAction()
    action._set_context(run.state.copy())
    directive = action.run(obj=None, run=run, config=loop)
    assert directive == FlowDirective.ENTER
    assert run.state["i"] == 0

    directive = action.return_from_children(obj=None, run=run, config=loop)
    assert directive == FlowDirective.ENTER
    assert run.state["i"] == 1

    # Simulate next iteration
    directive = action.return_from_children(obj=None, run=run, config=loop)
    assert directive == FlowDirective.ENTER
    assert run.state["i"] == 2

    # After last iteration
    directive = action.return_from_children(obj=None, run=run, config=loop)
    assert directive == FlowDirective.CONTINUE
    assert "i" not in run.state  # var removed after loop


def test_while_loop_action(run):
    run.state = {"counter": 0}
    loop = Condition(condition="counter < 2")
    action = WhileLoopAction()
    action._set_context(run.state.copy())

    # First iteration
    directive = action.run(obj=None, run=run, config=loop)
    assert directive == FlowDirective.ENTER

    # Simulate increment and next iteration
    run.state["counter"] += 1
    action._set_context(run.state.copy())
    directive = action.return_from_children(obj=None, run=run, config=loop)
    assert directive == FlowDirective.ENTER

    # Simulate increment and next iteration (should exit)
    run.state["counter"] += 1
    action._set_context(run.state.copy())
    directive = action.return_from_children(obj=None, run=run, config=loop)
    assert directive == FlowDirective.CONTINUE


@pytest.mark.django_db
def test_start_flow_action(user):
    parent_flow = Flow.objects.create(name="Parent Flow", active_at=timezone.now())
    run = FlowRun.objects.create(
        flow=parent_flow,
        content_object=user,
        state={"foo": "bar"},
    )
    start_flow = Flow.objects.create(name="Sub Flow", active_at=timezone.now())

    config = StartFlow(start_flow=start_flow, immediate=True)
    assert str(config) == f"{start_flow.name} (Immediate, Pass Object)"

    config = StartFlow(start_flow=start_flow, pass_state=True, pass_object=False)
    assert str(config) == f"{start_flow.name} (Pass State)"

    action = StartFlowAction()
    action._set_context(run.state.copy())
    directive = action.run(obj=user, run=run, config=config)
    assert directive == FlowDirective.CONTINUE
    sub_run = FlowRun.objects.filter(flow=start_flow, parent_run=run).first()
    assert sub_run is not None
    assert sub_run.continue_after is None
    assert sub_run.status == FlowRun.Status.PENDING
    assert sub_run.state == {"foo": "bar"}


@pytest.mark.django_db
def test_condition_config_bad_template(flow):
    cond = Condition(
        flow=flow, depth=1, path="fake", action="IfAction", condition="foo =bad= 'bar'"
    )

    try:
        cond.full_clean()
    except ValidationError as e:
        errors = e.args[0]
        assert "condition" in errors


@pytest.mark.django_db
def test_add_child_to_action(flow):
    state = State.add_root(
        flow=flow,
        action="SetStateAction",
        state={"foo": "bar"},
    )
    condition = Condition(
        flow=flow,
        action="IfAction",
        condition="foo == 'bar'",
    )
    with pytest.raises(ValueError, match="Cannot add child action to"):
        state.add_child(instance=condition)


@pytest.mark.django_db
def test_add_child_wrong_flow(flow):
    if_action = Condition.add_root(
        flow=flow,
        action="IfAction",
        condition="foo == 'bar'",
    )
    other_flow = Flow.objects.create(name="Other flow")
    state = State(
        flow=other_flow,
        action="SetStateAction",
        state={"foo": "bar"},
    )
    with pytest.raises(ValueError, match="Cannot add child action to a different flow"):
        if_action.add_child(instance=state)

    with pytest.raises(ValueError, match="Cannot add child action to a different flow"):
        if_action.add_child(
            flow=other_flow, action="SetStateAction", state={"foo": "bar"}
        )
