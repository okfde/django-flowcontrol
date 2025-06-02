import logging
from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone

import pytest

from flowcontrol.actions import (
    AbortAction,
    BreakAction,
    DelayAction,
    ForLoopAction,
    IfAction,
    LeaveAction,
    SetStateAction,
    StartFlowAction,
    UpdateStateAction,
    WhileLoopAction,
)
from flowcontrol.base import BaseAction, FlowDirective
from flowcontrol.engine import create_flow_run, execute_flow_run, start_flow_run
from flowcontrol.models import FlowRun
from flowcontrol.models.core import Flow
from flowcontrol.registry import action_registry, register_action
from flowcontrol.utils import ActionNode, make_action_tree


@pytest.mark.django_db
def test_forloop_flow(flow, user):
    make_action_tree(
        flow,
        [
            ActionNode(SetStateAction, {"state": {"i": 5}}),
            ActionNode(
                ForLoopAction,
                {"end": 3},
                [
                    ActionNode(
                        UpdateStateAction, {"state": {"i": "i|add:2"}, "evaluate": True}
                    ),
                ],
            ),
        ],
    )
    run = start_flow_run(flow, obj=user)
    assert run is not None
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.COMPLETE
    assert run.state["i"] == 11


@pytest.mark.django_db
def test_whileloop_flow(flow, user):
    make_action_tree(
        flow,
        [
            ActionNode(SetStateAction, {"state": {"i": 0}}),
            ActionNode(
                WhileLoopAction,
                {"condition": "i < 5"},
                [
                    ActionNode(
                        UpdateStateAction, {"state": {"i": "i|add:1"}, "evaluate": True}
                    ),
                ],
            ),
        ],
    )
    run = start_flow_run(flow, obj=user)
    assert run is not None
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.COMPLETE
    assert run.state["i"] == 5


@pytest.mark.django_db
def test_hot_loop_detection(flow, user):
    make_action_tree(
        flow,
        [
            ActionNode(SetStateAction, {"state": {"i": 0}}),
            ActionNode(
                WhileLoopAction,
                {"condition": "True"},
                [
                    ActionNode(
                        UpdateStateAction, {"state": {"i": "i|add:1"}, "evaluate": True}
                    ),
                ],
            ),
        ],
    )
    run = create_flow_run(flow, obj=user)
    max_hot_loop = 5
    execute_flow_run(run, max_hot_loop=max_hot_loop)
    assert run is not None
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.ERRORED
    assert run.state["i"] == 5
    assert f"Loop times {max_hot_loop} exceeded in flow run" in run.log


@pytest.mark.django_db
def test_run_with_no_object(flow):
    make_action_tree(
        flow,
        [
            ActionNode(SetStateAction, {"state": {"i": 0}}),
        ],
    )
    run = start_flow_run(flow)
    assert run is not None
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.COMPLETE
    assert run.state["i"] == 0


@pytest.mark.django_db
def test_run_with_object_gone_missing(flow):
    make_action_tree(
        flow,
        [
            ActionNode(SetStateAction, {"state": {"i": 0}}),
        ],
    )
    user = User.objects.create(username="testuser")
    run = create_flow_run(flow, obj=user)
    user.delete()

    execute_flow_run(run)

    assert run is not None
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.OBSOLETE


@pytest.mark.django_db
def test_if_action(flow):
    make_action_tree(
        flow,
        [
            ActionNode(SetStateAction, {"state": {"i": 0}}),
            ActionNode(
                IfAction,
                {"condition": "True"},
                [
                    ActionNode(
                        UpdateStateAction, {"state": {"i": "i|add:1"}, "evaluate": True}
                    ),
                ],
            ),
            ActionNode(
                UpdateStateAction, {"state": {"i": "i|add:1"}, "evaluate": True}
            ),
        ],
    )
    run = start_flow_run(flow, obj=None)
    assert run is not None
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.COMPLETE
    assert run.state["i"] == 2


@pytest.mark.django_db
def test_bad_if_action(flow):
    make_action_tree(
        flow,
        [
            ActionNode(SetStateAction, {"state": {"i": 0}}),
            ActionNode(
                IfAction,
                {"condition": "i !bad= 5"},
                [
                    ActionNode(
                        UpdateStateAction, {"state": {"i": "i|add:1"}, "evaluate": True}
                    ),
                ],
            ),
            ActionNode(
                UpdateStateAction, {"state": {"i": "i|add:1"}, "evaluate": True}
            ),
        ],
    )
    run = start_flow_run(flow, obj=None)
    assert run is not None
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.ERRORED
    assert run.state["i"] == 0


@pytest.mark.django_db
def test_leave_action(flow):
    make_action_tree(
        flow,
        [
            ActionNode(SetStateAction, {"state": {"i": 0}}),
            ActionNode(
                IfAction,
                {"condition": "True"},
                [
                    ActionNode(LeaveAction),
                    ActionNode(SetStateAction, {"state": {"i": 5}}),
                ],
            ),
            ActionNode(
                UpdateStateAction, {"state": {"i": "i|add:1"}, "evaluate": True}
            ),
        ],
    )
    run = start_flow_run(flow, obj=None)
    assert run is not None
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.COMPLETE
    assert run.state["i"] == 1


@pytest.mark.django_db
@pytest.mark.parametrize("break_condition", [{"condition": ""}, {"condition": "True"}])
def test_break_action(flow, break_condition):
    make_action_tree(
        flow,
        [
            ActionNode(SetStateAction, {"state": {"i": 0}}),
            ActionNode(
                WhileLoopAction,
                {"condition": "True"},
                [
                    ActionNode(SetStateAction, {"state": {"i": 5}}),
                    ActionNode(BreakAction, break_condition),
                ],
            ),
            ActionNode(
                UpdateStateAction, {"state": {"i": "i|add:1"}, "evaluate": True}
            ),
        ],
    )
    run = start_flow_run(flow, obj=None)
    assert run is not None
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.COMPLETE
    assert run.state["i"] == 6


@pytest.mark.django_db
def test_break_action_false(flow):
    make_action_tree(
        flow,
        [
            ActionNode(SetStateAction, {"state": {"i": 0}}),
            ActionNode(
                IfAction,
                {"condition": "True"},
                [
                    ActionNode(BreakAction, {"condition": "False"}),
                    ActionNode(SetStateAction, {"state": {"i": 5}}),
                ],
            ),
            ActionNode(
                UpdateStateAction, {"state": {"i": "i|add:1"}, "evaluate": True}
            ),
        ],
    )
    run = start_flow_run(flow, obj=None)
    assert run is not None
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.COMPLETE
    assert run.state["i"] == 6


@pytest.mark.django_db
def test_stop_action(flow):
    make_action_tree(
        flow,
        [
            ActionNode(SetStateAction, {"state": {"i": 0}}),
            ActionNode(
                WhileLoopAction,
                {"condition": "True"},
                [
                    ActionNode(SetStateAction, {"state": {"i": 5}}),
                    ActionNode(AbortAction),
                ],
            ),
            ActionNode(
                UpdateStateAction, {"state": {"i": "i|add:1"}, "evaluate": True}
            ),
        ],
    )
    run = start_flow_run(flow, obj=None)
    assert run is not None
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.ABORTED
    assert run.state["i"] == 5


@pytest.mark.django_db
def test_enter_with_no_children(flow):
    make_action_tree(
        flow,
        [
            ActionNode(SetStateAction, {"state": {"i": 0}}),
            ActionNode(
                IfAction,
                {"condition": "True"},
            ),
            ActionNode(
                UpdateStateAction, {"state": {"i": "i|add:1"}, "evaluate": True}
            ),
        ],
    )
    run = start_flow_run(flow, obj=None)
    assert run is not None
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.COMPLETE
    assert run.state["i"] == 1


@pytest.mark.django_db
def test_start_flow_action_immediate(flow):
    sub_flow = Flow.objects.create(active_at=timezone.now())

    make_action_tree(
        sub_flow,
        [
            ActionNode(
                UpdateStateAction, {"state": {"i": "i|add:1"}, "evaluate": True}
            ),
        ],
    )

    make_action_tree(
        flow,
        [
            ActionNode(SetStateAction, {"state": {"i": 5}}),
            ActionNode(StartFlowAction, {"start_flow": sub_flow, "immediate": True}),
            ActionNode(
                UpdateStateAction, {"state": {"i": "i|add:1"}, "evaluate": True}
            ),
        ],
    )
    run = start_flow_run(flow)
    assert run is not None
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.COMPLETE
    assert run.state["i"] == 6

    sub_run = FlowRun.objects.filter(flow=sub_flow).first()
    assert sub_run.status == FlowRun.Status.DONE
    assert sub_run.outcome == FlowRun.Outcome.COMPLETE
    # state was not passed
    assert sub_run.state["i"] == ""


@pytest.mark.django_db
def test_start_flow_action_limit(flow):
    sub_flow = Flow.objects.create(active_at=timezone.now(), max_concurrent=1)

    already = FlowRun.objects.create(flow=sub_flow)

    make_action_tree(
        sub_flow,
        [
            ActionNode(
                UpdateStateAction, {"state": {"i": "i|add:1"}, "evaluate": True}
            ),
        ],
    )

    make_action_tree(
        flow,
        [
            ActionNode(SetStateAction, {"state": {"i": 5}}),
            ActionNode(StartFlowAction, {"start_flow": sub_flow, "immediate": True}),
            ActionNode(
                UpdateStateAction, {"state": {"i": "i|add:1"}, "evaluate": True}
            ),
        ],
    )
    run = start_flow_run(flow)
    assert run is not None
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.COMPLETE
    assert run.state["i"] == 6

    sub_run = FlowRun.objects.filter(flow=sub_flow).get()
    assert sub_run == already


@pytest.mark.django_db
def test_flow_run_suspend_resume(flow):
    make_action_tree(
        flow,
        [
            ActionNode(SetStateAction, {"state": {"i": 0}}),
            ActionNode(DelayAction),
            ActionNode(
                UpdateStateAction, {"state": {"i": "i|add:1"}, "evaluate": True}
            ),
        ],
    )
    run = start_flow_run(flow)
    assert run is not None
    assert run.status == FlowRun.Status.WAITING
    assert run.outcome == ""
    assert run.state["i"] == 0

    execute_flow_run(run)
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.COMPLETE
    assert run.state["i"] == 1


@pytest.mark.django_db
def test_nested_break(flow):
    make_action_tree(
        flow,
        [
            ActionNode(SetStateAction, {"state": {"i": 0}}),
            ActionNode(
                IfAction,
                {"condition": "True"},
                [
                    ActionNode(
                        IfAction, {"condition": "True"}, [ActionNode(BreakAction)]
                    ),
                ],
            ),
            ActionNode(
                UpdateStateAction, {"state": {"i": "i|add:1"}, "evaluate": True}
            ),
        ],
    )
    run = start_flow_run(flow)
    assert run is not None
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.COMPLETE
    assert run.state["i"] == 1


def test_inactive_flow(flow):
    flow.active_at = None
    with pytest.raises(
        ValueError, match="Cannot start a flow run for an inactive flow"
    ):
        create_flow_run(flow)


@pytest.mark.django_db
def test_active_flow_manager_method():
    active_flow = Flow.objects.create(name="Active", active_at=timezone.now())
    Flow.objects.create(name="Inactive", active_at=None)
    Flow.objects.create(
        name="Soon active", active_at=timezone.now() + timedelta(hours=5)
    )
    active_flows = Flow.objects.get_active()
    assert len(active_flows) == 1
    assert active_flows[0] == active_flow


def test_flow_limit_max_concurrent(flow):
    flow.max_concurrent = 1

    run = create_flow_run(flow)
    assert run is not None

    run = create_flow_run(flow)
    assert run is None


def test_flow_limit_max_per_object(flow, user):
    flow.max_per_object = 1

    run = start_flow_run(flow, obj=user)
    assert run is not None
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.COMPLETE

    run = start_flow_run(flow, obj=user)
    assert run is None


def test_flow_limit_max_concurrent_per_object(flow, user):
    flow.max_concurrent_per_object = 1

    run = start_flow_run(flow, obj=user)
    assert run is not None
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.COMPLETE

    run = create_flow_run(flow, obj=user)
    assert run is not None
    assert run.status == FlowRun.Status.PENDING

    run = create_flow_run(flow, obj=user)
    assert run is None


@pytest.mark.django_db
def test_suspend_no_continue_timestamp(flow):
    @register_action
    class BadSuspend(BaseAction):
        def run(self, *args, **kwargs):
            return FlowDirective.SUSPEND

    make_action_tree(
        flow,
        [
            ActionNode(BadSuspend),
        ],
    )
    run = start_flow_run(flow)
    assert run is not None
    run.refresh_from_db()
    assert run.status == FlowRun.Status.WAITING
    assert run.outcome == ""
    assert run.continue_after is not None


@pytest.mark.django_db
def test_action_exception(flow):
    @register_action
    class BadAction(BaseAction):
        def run(self, *args, **kwargs):
            raise KeyError

    make_action_tree(
        flow,
        [
            ActionNode(BadAction),
        ],
    )
    run = start_flow_run(flow)
    assert run is not None
    run.refresh_from_db()
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.ERRORED
    assert "KeyError" in run.log
    run.done_at = None
    run.status = FlowRun.Status.PENDING
    execute_flow_run(run)


@pytest.mark.django_db
def test_action_return_none(flow):
    @register_action
    class NoneAction(BaseAction):
        def run(self, *args, **kwargs):
            return None

    make_action_tree(
        flow,
        [
            ActionNode(NoneAction),
        ],
    )
    run = start_flow_run(flow)
    assert run is not None
    run.refresh_from_db()
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.COMPLETE


@pytest.mark.django_db
def test_action_bad_directive(flow):
    @register_action
    class BadDirectiveAction(BaseAction):
        def run(self, *args, **kwargs):
            return 1000

    make_action_tree(
        flow,
        [
            ActionNode(BadDirectiveAction),
        ],
    )
    run = start_flow_run(flow)
    assert run is not None
    run.refresh_from_db()
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.ERRORED
    assert "TypeError" in run.log
    assert "Expected a FlowDirective value" in run.log


@pytest.mark.django_db
def test_missing_action(flow, temp_registry):
    @register_action
    class ActionGonMissing(BaseAction):
        pass

    make_action_tree(
        flow,
        [
            ActionNode(ActionGonMissing),
        ],
    )
    # Remove from registry
    action_registry.actions = {}

    run = start_flow_run(flow)
    assert run is not None
    run.refresh_from_db()
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.ERRORED
    assert "ActionMissingError" in run.log
    assert "Action ActionGonMissing is missing or not found" in run.log


def test_execute_done_flow(caplog, flow_run):
    flow_run.status = FlowRun.Status.DONE
    with caplog.at_level(logging.WARNING):
        execute_flow_run(flow_run)
    assert f"Flow run {flow_run.id} is not in a valid state to execute" in caplog.text


def test_execute_flow_waiting_no_continue_after(flow_run):
    flow_run.status = FlowRun.Status.WAITING
    flow_run.continue_after = None
    with pytest.raises(
        ValueError, match="Flow run is waiting but has no continue_after time set"
    ):
        execute_flow_run(flow_run)


def test_execute_flow_waiting_no_action(flow_run):
    flow_run.status = FlowRun.Status.WAITING
    flow_run.continue_after = timezone.now()
    flow_run.action = None
    with pytest.raises(ValueError, match="Flow run is waiting but has no action set"):
        execute_flow_run(flow_run)


def test_execute_flow_waiting_too_early(flow_run, flow_action):
    flow_run.status = FlowRun.Status.WAITING
    flow_run.continue_after = timezone.now() + timedelta(hours=5)
    flow_run.action = flow_action

    execute_flow_run(flow_run)

    assert flow_run.status == FlowRun.Status.WAITING


def test_runnable_flow_runs(flow):
    run1 = FlowRun.objects.create(
        flow=flow, status=FlowRun.Status.PENDING, continue_after=None
    )
    run2 = FlowRun.objects.create(
        flow=flow, status=FlowRun.Status.WAITING, continue_after=timezone.now()
    )
    FlowRun.objects.create(flow=flow, status=FlowRun.Status.DONE)
    # Broken states
    FlowRun.objects.create(
        flow=flow, status=FlowRun.Status.WAITING, continue_after=None
    )
    FlowRun.objects.create(
        flow=flow, status=FlowRun.Status.PENDING, continue_after=timezone.now()
    )

    runs = FlowRun.objects.get_runnable()
    assert len(runs) == 2
    assert {run1, run2} == set(runs)


@pytest.mark.django_db
def test_suspend_and_repeat(flow, temp_registry):
    @register_action
    class SuspendAndRepeatAction(BaseAction):
        def run(self, *, run, obj=None, config=None):
            run.state["i"] = run.state.get("i", 0) + 1
            if run.state.get("i", 0) < 3:
                return FlowDirective.SUSPEND_AND_REPEAT
            return FlowDirective.CONTINUE

    make_action_tree(
        flow,
        [
            ActionNode(SuspendAndRepeatAction),
        ],
    )
    run = create_flow_run(flow)

    execute_flow_run(run)
    assert run is not None
    assert run.status == FlowRun.Status.WAITING
    assert run.state["i"] == 1
    assert run.continue_after is not None
    assert run.repeat_action

    execute_flow_run(run)
    assert run is not None
    assert run.status == FlowRun.Status.WAITING
    assert run.state["i"] == 2
    assert run.continue_after is not None
    assert run.repeat_action

    execute_flow_run(run)
    assert run is not None
    assert run.status == FlowRun.Status.DONE
    assert run.outcome == FlowRun.Outcome.COMPLETE
    assert run.state["i"] == 3
    assert run.continue_after is None
    assert not run.repeat_action
