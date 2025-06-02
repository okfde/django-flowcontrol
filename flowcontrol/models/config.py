from datetime import datetime

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from dateutil.parser import parse
from dateutil.relativedelta import relativedelta

from ..base import FlowDirective
from ..utils import (
    evaluate_expression,
    evaluate_if,
    readable_timedelta,
    validate_template_condition,
)
from .core import ActionBase, Flow


class Condition(ActionBase):
    condition = models.TextField(
        blank=True,
        default="",
        verbose_name="Condition Expression",
        help_text="A Django template variable expression. Context contains `object` and flow run state.",
        validators=[validate_template_condition],
    )

    def __str__(self):
        return self.condition

    def check_condition(self, context):
        """
        Check if the condition is met based on the provided context.
        This method should be overridden in subclasses to implement specific logic.
        """
        if not self.condition:
            return False
        return evaluate_if(self.condition, context)


class Delay(ActionBase):
    WEEKDAYS = [
        (0, _("Monday")),
        (1, _("Tuesday")),
        (2, _("Wednesday")),
        (3, _("Thursday")),
        (4, _("Friday")),
        (5, _("Saturday")),
        (6, _("Sunday")),
    ]
    base_date_template = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Base Date Template"),
        help_text=_(
            "Template expression from which the delay will be calculated, defaults to time of invocation."
        ),
    )
    months = models.SmallIntegerField(
        null=True,
        blank=True,
        default=None,
        verbose_name=_("Delay for number of months"),
        help_text=_("Number of months to delay before proceeding to the next action."),
    )
    seconds = models.DurationField(
        default=None,
        null=True,
        blank=True,
        verbose_name="Wait Time (seconds)",
        help_text="Number of seconds before proceeding to the next action.",
    )
    weekday = models.PositiveSmallIntegerField(
        choices=WEEKDAYS,
        null=True,
        blank=True,
        default=None,
        verbose_name=_("Delay Until this weekday"),
        help_text=_("Only continue after reaching this time."),
    )
    time = models.TimeField(
        null=True,
        blank=True,
        default=None,
        verbose_name="Delay Until this time",
        help_text="Continue after reaching this time.",
    )
    action_if_past = models.PositiveSmallIntegerField(
        choices=[
            (int(FlowDirective.SUSPEND), _("Continue from now")),
            (int(FlowDirective.LEAVE), _("Return to parent")),
            (int(FlowDirective.BREAK), _("Break to next parent's sibling")),
            (int(FlowDirective.ABORT), _("Abort run")),
        ],
        default=0,
        verbose_name=_("Action if past delay"),
        help_text=_(
            "What to do if the delay is already past when the action is executed."
        ),
    )

    def __str__(self):
        """
        Return a string representation of the delay action.
        If weekday and time are set, include them in the string.
        """
        parts = []
        if self.months:
            parts.append(_("after {months} month(s)").format(months=self.months))
        if self.seconds:
            parts.append(readable_timedelta(self.seconds))
        if self.weekday is not None:
            parts.append(_("on {weekday}").format(weekday=self.get_weekday_display()))
        if self.time:
            parts.append(_("at {time}").format(time=self.time.strftime("%H:%M")))
        delay = str(", ".join(parts) if parts else _("No delay set."))
        if self.base_date_template:
            return f"{self.base_date_template}: {delay}"
        return delay

    def calculate_delay(self, context):
        if self.base_date_template:
            base_date = evaluate_expression(self.base_date_template, context)
            if isinstance(base_date, str):
                # Attempt to parse the base date from a string
                base_date = parse(base_date)
            elif not isinstance(base_date, datetime):
                raise ValueError(
                    f"Base date must be a datetime or a parsable string, got {type(base_date)}"
                )
        else:
            base_date = timezone.now()

        return self.apply_timedelta(base_date)

    def apply_timedelta(self, date):
        if self.months:
            date += relativedelta(months=self.months)
        if self.seconds:
            date += relativedelta(seconds=self.seconds.total_seconds())
        if self.weekday is not None:
            date += relativedelta(weekday=self.weekday)
        if self.time is not None:
            date += relativedelta(
                hour=self.time.hour, minute=self.time.minute, second=self.time.second
            )
        return date


class StartFlow(ActionBase):
    start_flow = models.ForeignKey(
        Flow,
        on_delete=models.PROTECT,
        related_name="start_actions",
        verbose_name="Flow to Start",
        help_text="The flow that will be started by this action.",
    )
    immediate = models.BooleanField(
        default=False,
        verbose_name="Immediate Start",
        help_text="If checked, the flow will start running in this action.",
    )
    pass_object = models.BooleanField(
        default=True,
        verbose_name="Pass object",
        help_text="If checked, the object of the parent run will be used for this flow.",
    )
    pass_state = models.BooleanField(
        default=False,
        verbose_name="Pass State",
        help_text="If checked, the state of the parent flow run will be passed in.",
    )

    def __str__(self):
        """
        Returns a string representation of the start flow action.
        If `immediate` is True, it indicates that the flow will start immediately.
        """
        flags = []
        if self.immediate:
            flags.append("Immediate")
        if self.pass_object:
            flags.append("Pass Object")
        if self.pass_state:
            flags.append("Pass State")
        flags = ", ".join(flags)
        flags = f" ({flags})" if flags else ""
        return f"{self.start_flow.name}{flags}"


class State(ActionBase):
    state = models.JSONField(
        default=dict,
        verbose_name="State",
        help_text="A JSON object representing the state to set.",
        encoder=DjangoJSONEncoder,
    )
    evaluate = models.BooleanField(
        default=False,
        verbose_name="Evaluate as expressions",
        help_text="If checked, object string values will be evaluated as Django template expressions.",
    )

    def __str__(self):
        return f"State: {self.state}{' (Evaluate)' if self.evaluate else ''}"

    def get_resulting_object(self, context):
        """
        Returns the state object to be set.
        If `evaluate` is True, it evaluates the state as a Django template expression.
        """
        if self.evaluate:
            return {
                key: evaluate_expression(value, context)
                if isinstance(value, str)
                else value
                for key, value in self.state.items()
            }
        return self.state.copy()


class ForLoop(ActionBase):
    """
    Represents a for loop action that iterates over a list of items.
    The loop will execute its children for each item in the list.
    """

    var_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Variable Name",
        help_text="The name of the variable that will hold the current item in the loop.",
    )
    start = models.PositiveIntegerField(
        default=0,
        verbose_name="Start Index",
        help_text="The index to start iterating from.",
    )
    end = models.PositiveIntegerField(
        default=0,
        verbose_name="End Index",
        help_text="The index to stop iterating at (exclusive).",
    )
    step = models.PositiveIntegerField(
        default=1,
        verbose_name="Step",
        help_text="The step size for each iteration.",
    )

    def __str__(self):
        loop = f"{self.start} to {self.end} with step {self.step}"
        if self.var_name:
            return f"{self.var_name}: {loop}"
        return loop
