import logging

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from flowcontrol.engine import execute_flow_run

from .base import BaseAction, FlowDirective
from .models.config import Condition, Delay, ForLoop, StartFlow, State
from .registry import register_action

logger = logging.getLogger(__name__)


class ConditionBase(BaseAction):
    model = Condition
    has_children = True
    group = _("Control flow")

    def run(self, *, run, obj, config) -> FlowDirective:
        if config and config.check_condition(self.get_context()):
            return FlowDirective.ENTER
        return FlowDirective.CONTINUE


@register_action
class IfAction(ConditionBase):
    verbose_name = _("If Condition")
    description = _("This action runs a block of actions if a condition is true.")

    def return_from_children(self, *, run, obj, config=None) -> FlowDirective:
        return FlowDirective.CONTINUE


@register_action
class WhileLoopAction(ConditionBase):
    verbose_name = _("While Loop")
    description = _("This action runs a block of actions while a condition is true.")

    def return_from_children(self, **kwargs) -> FlowDirective:
        return self.run(**kwargs)


@register_action
class DelayAction(BaseAction):
    verbose_name = _("Delay")
    description = _("This action suspends the flow for some time.")
    group = _("Control flow")
    model = Delay

    def run(self, *, run, obj, config: Delay) -> FlowDirective:
        now = timezone.now()
        run.continue_after = config.calculate_delay(self.get_context())
        if run.continue_after < now:
            return FlowDirective(config.action_if_past)
        return FlowDirective.SUSPEND


@register_action
class StartFlowAction(BaseAction):
    verbose_name = _("Start new flow")
    description = _("This action starts another flow.")
    group = _("Control flow")
    model = StartFlow

    def run(self, *, run, obj, config: StartFlow) -> FlowDirective:
        from .engine import create_flow_run

        state = None
        if config.pass_state:
            state = run.state
        pass_obj = None
        if config.pass_object:
            pass_obj = obj

        sub_run = create_flow_run(
            flow=config.start_flow,
            obj=pass_obj,
            state=state,
            parent_run=run,
        )
        if sub_run is None:
            logger.warning("Failed to start sub run for %s", config.start_flow)

        if sub_run and config.immediate:
            execute_flow_run(sub_run)

        return FlowDirective.CONTINUE


@register_action
class SetStateAction(BaseAction):
    verbose_name = _("Set state")
    description = _("Replace run state.")
    group = _("State manipulation")
    model = State

    def run(self, *, run, obj, config=None) -> FlowDirective:
        context = self.get_context()
        state = config.get_resulting_object(context)
        # Add internal state variables that start with "_"
        state.update({k: v for k, v in run.state.items() if k.startswith("_")})
        run.state = state
        return FlowDirective.CONTINUE


@register_action
class UpdateStateAction(BaseAction):
    verbose_name = _("Update state")
    description = _("Update run state.")
    group = _("State manipulation")
    model = State

    def run(self, *, run, obj, config) -> FlowDirective:
        context = self.get_context()

        state = config.get_resulting_object(context)
        run.state.update(state)
        return FlowDirective.CONTINUE


@register_action
class ForLoopAction(BaseAction):
    verbose_name = _("For Loop")
    description = _("Loop with a number of times.")
    group = _("Control flow")
    model = ForLoop
    has_children = True

    def _get_key(self, config):
        if config.var_name:
            return config.var_name
        return f"_for_loop_{config.id}"

    def run(self, *, run, obj, config: ForLoop) -> FlowDirective:
        key = self._get_key(config)
        if key not in run.state:
            run.state[key] = config.start

        if run.state[key] >= config.end:
            del run.state[key]
            return FlowDirective.CONTINUE
        return FlowDirective.ENTER

    def return_from_children(self, *, run, obj, config: ForLoop) -> FlowDirective:
        key = self._get_key(config)
        if key not in run.state:
            logger.warning("ForLoopAction: key %s not found in run state", key)
            raise KeyError(f"ForLoopAction: key {key} not found in run state")
        run.state[key] += config.step
        if run.state[key] >= config.end:
            del run.state[key]
            return FlowDirective.CONTINUE
        return FlowDirective.ENTER


class ConditionalDirective(BaseAction):
    model = Condition
    true_directive: FlowDirective

    def run(self, *, run, obj, config: Condition) -> FlowDirective:
        if config and config.condition:
            if config.check_condition(self.get_context()):
                return self.true_directive
            return FlowDirective.CONTINUE
        return self.true_directive


@register_action
class LeaveAction(ConditionalDirective):
    verbose_name = _("Return to parent action")
    description = _("This action returns control to the parent action.")
    group = _("Control flow")

    true_directive = FlowDirective.LEAVE


@register_action
class BreakAction(ConditionalDirective):
    verbose_name = _("Leave branch")
    description = _("This action moves control to the parent action's next sibling.")
    group = _("Control flow")

    true_directive = FlowDirective.BREAK


@register_action
class AbortAction(BaseAction):
    verbose_name = _("Stop Flow")
    description = _("This action stops the flow.")
    group = _("Control flow")

    def run(self, *, run, obj, config=None) -> FlowDirective:
        return FlowDirective.ABORT
