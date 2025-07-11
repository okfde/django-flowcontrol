import logging
from collections import Counter
from typing import Optional

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from .base import FlowDirective
from .models import Flow, FlowAction, FlowRun, Trigger

logger = logging.getLogger(__name__)

MAX_HOT_LOOPS = 1000


def trigger_flows(
    trigger_name: str,
    obj: Optional[models.Model] = None,
    state: Optional[dict] = None,
    immediate: bool = False,
) -> list[FlowRun]:
    """Triggers flows based on the given trigger name.

    Args:
        trigger_name (str): trigger name to look up in the database.
        obj (Optional[models.Model], optional): object associated with the flow run. Defaults to None.
        state (Optional[dict], optional): Default state of the flow run. Defaults to None.
        immediate (bool, optional): Execute immediately if True. Defaults to False.

    Returns:
        A list of FlowRun instances that were created as a result of the trigger.
    """
    active_triggers = Trigger.objects.get_active_for_trigger_name(trigger_name)
    runs = []
    for trigger in active_triggers:
        flow = trigger.flow
        run = create_flow_run(flow, obj, state=state, trigger=trigger)
        if run is None:
            logger.warning(
                f"Flow run for flow {flow.id} and object {obj} was not triggered due to limits."
            )
            continue
        runs.append(run)

    if immediate:
        for run in runs:
            execute_flow_run(run)
    return runs


def create_flow_run(
    flow: Flow,
    obj: Optional[models.Model] = None,
    state: Optional[dict] = None,
    parent_run: Optional[FlowRun] = None,
    trigger: Optional[Trigger] = None,
) -> Optional[FlowRun]:
    """
    Creates a new flow run from flow when limits allow it.

    Args:
        flow (Flow): The Flow instance to start.
        obj (Optional[models.Model]): The object related to the flow run.
        state (Optional[dict]): Optional initial state for the flow run.
        parent_run (Optional[FlowRun]): Optional parent FlowRun instance if this run is a child of another.
        trigger (Optional[Trigger]): The trigger that initiated this flow run.

    Returns:
        The created FlowRun instance, or None if the run was not created.
    """

    if not flow.is_active():
        raise ValueError("Cannot start a flow run for an inactive flow")

    check_aggs = {}
    if flow.max_concurrent > 0:
        check_aggs["concurrent_count"] = models.Count(
            "id", filter=~models.Q(status=FlowRun.Status.DONE)
        )

    if obj is not None:
        content_type = ContentType.objects.get_for_model(obj)
        object_id = obj.pk

        if flow.max_per_object > 0:
            check_aggs["object_count"] = models.Count(
                "id", filter=models.Q(content_type=content_type, object_id=object_id)
            )
        if flow.max_concurrent_per_object > 0:
            check_aggs["concurrent_object_count"] = models.Count(
                "id",
                filter=models.Q(content_type=content_type, object_id=object_id)
                & ~models.Q(status=FlowRun.Status.DONE),
            )
    if check_aggs:
        run_counts = FlowRun.objects.filter(flow=flow).aggregate(**check_aggs)
        count = run_counts.get("concurrent_count")
        if count and count >= flow.max_concurrent:
            return
        count = run_counts.get("object_count")
        if count and count >= flow.max_per_object:
            return
        count = run_counts.get("concurrent_object_count")
        if count and count >= flow.max_concurrent_per_object:
            return

    run = FlowRun.objects.create(
        flow=flow,
        content_object=obj,
        status=FlowRun.Status.PENDING,
        parent_run=parent_run,
        state=state or {},
        trigger=trigger,
    )

    return run


def start_flow_run(
    flow: Flow,
    obj: Optional[models.Model] = None,
    state: Optional[dict] = None,
    parent_run: Optional[FlowRun] = None,
) -> Optional[FlowRun]:
    """
    Creates a flow run (flow limits allowing) and executes it immediately.

    Args:
        flow (Flow): The Flow instance to start.
        obj (Optional[models.Model]): The object related to the flow run.
        state (Optional[dict]): Optional initial state for the flow run.
        parent_run (Optional[FlowRun]): Optional parent FlowRun instance if this run is a child of another.

    Returns:
        The created FlowRun instance, or None if the run was not created.
    """

    flow_run = create_flow_run(flow, obj=obj, state=state, parent_run=parent_run)
    if flow_run is None:
        logger.warning(
            f"Flow run for flow {flow.id} and object {obj} was not created due to limits."
        )
        return None

    execute_flow_run(flow_run)
    return flow_run


def discard_flowrun(run):
    run.status = FlowRun.Status.DONE
    run.outcome = FlowRun.Outcome.OBSOLETE
    run.done_at = timezone.now()
    run.save()


def abort_flowrun(run):
    run.status = FlowRun.Status.DONE
    run.outcome = FlowRun.Outcome.ABORTED
    run.done_at = timezone.now()
    run.save()


def error_flowrun(run, message=""):
    run.status = FlowRun.Status.DONE
    run.outcome = FlowRun.Outcome.ERRORED
    run.done_at = timezone.now()
    run.append_log(message)
    run.save()


def suspend_flowrun(run):
    if run.continue_after is None:
        run.continue_after = timezone.now()

    run.status = FlowRun.Status.WAITING
    run.save()


def complete_flowrun(run):
    run.status = FlowRun.Status.DONE
    run.outcome = FlowRun.Outcome.COMPLETE
    run.done_at = timezone.now()
    run.save()


def continue_flowruns():
    runnable = FlowRun.objects.get_runnable()

    for runnable_run in runnable:
        execute_flow_run(runnable_run)


def execute_flow_run(run, max_hot_loop: int = MAX_HOT_LOOPS) -> Optional[FlowRun]:
    """
    Executes the flow run, processing its actions.

    Args:
        run (FlowRun): The FlowRun instance to execute.
        max_hot_loop (int): Maximum number of times an action can be executed in a loop before aborting.

    Returns:
        The updated FlowRun instance or None if the run was not executed due to its status.
    """

    if run.status not in (FlowRun.Status.PENDING, FlowRun.Status.WAITING):
        logger.warning(
            f"Flow run {run.id} is not in a valid state to execute: {run.status}"
        )
        return

    obj = None
    if run.content_type_id and run.object_id:
        obj = run.content_object
        if obj is None:
            logger.warning(
                f"Flow run {run.id} references an object that does not exist: "
                f"{run.content_type_id}, {run.object_id}, aborting execution."
            )
            discard_flowrun(run)
            return

    skip_execution = False
    if run.status == FlowRun.Status.WAITING:
        if run.continue_after is None:
            raise ValueError("Flow run is waiting but has no continue_after time set")
        if run.action is None:
            raise ValueError("Flow run is waiting but has no action set")
        if timezone.now() < run.continue_after:
            # Still waiting, do not execute yet
            return
        skip_execution = not run.repeat_action
        run.repeat_action = False
        run.continue_after = None
    else:
        if not run.action:
            run.action = run.flow.actions.first()

    run.status = FlowRun.Status.RUNNING
    run.save()

    loop_counter = Counter()
    action = run.action
    returning = False

    while True:
        if action is None:
            # No action to execute, complete the flow run
            complete_flowrun(run)
            return

        if not skip_execution:
            run.action = action
            try:
                directive = execute_action(run, action, obj, returning=returning)
            except Exception as exception:
                logger.exception("Error executing action %s", action)
                error_flowrun(run, repr(exception))
                return
        else:
            skip_execution = False
            directive = FlowDirective.CONTINUE

        if directive == FlowDirective.CONTINUE:
            sibling = action.get_next_sibling()
            if sibling is None:
                # No more actions to execute in this branch
                action = action.get_parent()
                returning = True
            else:
                action = sibling
                returning = False
        elif directive == FlowDirective.ENTER:
            loop_counter[action.id] += 1
            if loop_counter[action.id] > max_hot_loop:
                logger.warning(
                    f"Action {action} ({action.id}) entered more than {max_hot_loop} times in flow run {run.id}. Aborting."
                )
                error_flowrun(
                    run,
                    message=f"Loop times {max_hot_loop} exceeded in flow run at {action} ({action.id}).",
                )
                return
            child = action.get_first_child()
            if child is None:
                logger.warning(
                    "Action %s has no children but is issuing ENTER directive.", action
                )
                action = action
                returning = True
            else:
                action = child
                returning = False
        elif directive == FlowDirective.LEAVE:
            action = action.get_parent()
            returning = True
        elif directive == FlowDirective.BREAK:
            action = action.get_parent()
            skip_execution = True
            returning = False
        elif directive == FlowDirective.ABORT:
            abort_flowrun(run)
            return
        elif directive == FlowDirective.SUSPEND:
            suspend_flowrun(run)
            return
        elif directive == FlowDirective.SUSPEND_AND_REPEAT:
            run.repeat_action = True
            suspend_flowrun(run)
            return


class ActionMissingError(Exception):
    """Raised when an action is missing or not found."""

    pass


def execute_action(
    run: FlowRun, action: FlowAction, obj: models.Model, returning: bool = False
) -> FlowDirective:
    concrete_action = action.get_concrete_action()
    if concrete_action is None:
        raise ActionMissingError(f"Action {action} is missing or not found.")

    config = action.get_config()
    context = run.state.copy()
    context.update(
        {
            "object": obj,
            "obj": obj,
        }
    )
    concrete_action._set_context(context)

    method = concrete_action.run
    if returning:
        method = concrete_action.return_from_children

    directive = method(
        obj=obj,
        run=run,
        config=config,
    )

    if directive is None:
        return FlowDirective.CONTINUE
    if not isinstance(directive, FlowDirective):
        raise TypeError(
            f"Action {action} returned an invalid directive: {directive}. "
            "Expected a FlowDirective value or None."
        )
    return directive
