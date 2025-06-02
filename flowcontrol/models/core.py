from typing import TYPE_CHECKING, Optional

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from treebeard.mp_tree import MP_Node

from ..registry import (
    MAX_ACTION_NAME_LENGTH,
    MAX_TRIGGER_NAME_LENGTH,
    RegisteredTrigger,
    action_registry,
    trigger_registry,
)

if TYPE_CHECKING:
    from ..base import BaseAction


class FlowManager(models.Manager):
    def get_active(self):
        """
        Returns all active flows.
        A flow is considered active if it has an active_at timestamp.
        """
        return self.filter(active_at__lte=timezone.now())


class Flow(models.Model):
    name = models.CharField(
        max_length=100,
        verbose_name=_("Flow Name"),
        help_text=_("Name of the flow"),
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Description of the flow"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        editable=False,
        verbose_name=_("Created At"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        editable=False,
        verbose_name=_("Updated At"),
    )
    active_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Active Since"),
        editable=False,
    )

    max_concurrent = models.PositiveIntegerField(
        default=0, verbose_name=_("Max Concurrent Runs")
    )
    max_per_object = models.PositiveIntegerField(default=0)
    max_concurrent_per_object = models.PositiveIntegerField(default=1)

    objects = FlowManager()

    class Meta:
        verbose_name = _("Flow")
        verbose_name_plural = _("Flows")

    def __str__(self):
        return self.name

    def is_active(self) -> bool:
        return self.active_at and self.active_at <= timezone.now()


class FlowAction(MP_Node):
    flow = models.ForeignKey(
        Flow,
        on_delete=models.CASCADE,
        related_name="actions",
        verbose_name=_("Flow"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At"),
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Optional documentation for this action."),
    )

    action = models.CharField(
        max_length=MAX_ACTION_NAME_LENGTH,
        verbose_name=_("Action Name"),
        help_text=_("Name of the action to be performed"),
    )

    class Meta:
        verbose_name = _("Flow Action")
        verbose_name_plural = _("Flow Actions")

    def __str__(self):
        action_class = self.get_action_class()
        if action_class:
            name = str(action_class.verbose_name)
        else:
            name = self.action
        return name

    def get_action_class(self) -> Optional[type["BaseAction"]]:
        return action_registry.get_action(self.action)

    def get_concrete_action(self) -> Optional["BaseAction"]:
        """
        Returns the instance of the action class associated with this FlowAction.
        """
        action_class = self.get_action_class()
        if not action_class:
            return None
        return action_class()

    def get_config(self):
        action_class = self.get_action_class()
        if not action_class or action_class.model is None:
            return None

        return action_class.model.objects.filter(flowaction_ptr_id=self.id).first()

    def get_siblings(self):
        """
        :returns: A queryset of all the node's siblings, including the node
            itself.
        """
        qs = super().get_siblings()
        return qs.filter(flow=self.flow)

    def add_child(self, **kwargs):
        """
        Add a child action to this action.
        """
        action_class = self.get_action_class()
        if action_class and not action_class.has_children:
            raise ValueError(f"Cannot add child action to {action_class.get_name()}")
        if "flow" in kwargs and kwargs["flow"] != self.flow:
            raise ValueError("Cannot add child action to a different flow")
        if "instance" in kwargs and kwargs["instance"].flow != self.flow:
            raise ValueError("Cannot add child action to a different flow")
        return super().add_child(**kwargs)

    def move(self, target, pos=None):
        """
        Move this action to a new position in the tree.
        """
        if pos and pos.endswith("-child"):
            target_action_class = target.get_action_class()
            if target_action_class and not target_action_class.has_children:
                return

        return super().move(target, pos=pos)


class ActionBase(FlowAction):
    flowaction_ptr = models.OneToOneField(
        FlowAction,
        on_delete=models.CASCADE,
        parent_link=True,
        primary_key=True,
        related_name="%(app_label)s_%(class)s",
    )

    class Meta:
        abstract = True


class FlowRunManager(models.Manager):
    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("flow")
            .prefetch_related("flow__actions")
        )

    def get_runnable(self):
        return self.get_queryset().filter(
            Q(status=FlowRun.Status.PENDING, continue_after__isnull=True)
            | Q(status=FlowRun.Status.WAITING, continue_after__lte=timezone.now())
        )


class Status(models.TextChoices):
    PENDING = "pending", _("Pending")
    RUNNING = "running", _("Running")
    WAITING = "waiting", _("Waiting")
    PAUSED = "paused", _("Paused")
    DONE = "done", _("done")


class Outcome(models.TextChoices):
    COMPLETE = "complete", _("Complete")
    ABORTED = "aborted", _("Aborted")
    ERRORED = "errored", _("Errored")
    OBSOLETE = "obsolete", _("Obsolete")


class FlowRun(models.Model):
    Status = Status
    Outcome = Outcome

    flow = models.ForeignKey(
        Flow,
        on_delete=models.CASCADE,
        related_name="runs",
        verbose_name=_("Flow"),
    )
    parent_run = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="child_runs",
        verbose_name=_("Parent Run"),
    )
    trigger = models.ForeignKey(
        "Trigger",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="runs",
        verbose_name=_("Created by trigger"),
    )

    action = models.ForeignKey(
        FlowAction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="runs",
        verbose_name=_("Action"),
    )
    repeat_action = models.BooleanField(
        default=False,
        verbose_name=_("Execute action again on resume"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status,
        default=Status.PENDING,
        verbose_name=_("Status"),
    )
    outcome = models.CharField(
        max_length=20,
        blank=True,
        choices=Outcome,
        default="",
        verbose_name=_("Outcome"),
    )
    log = models.TextField(blank=True, verbose_name=_("Log"))
    created_at = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("Created At"),
    )
    continue_after = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Continue After"),
    )
    done_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Completed At"),
    )

    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True
    )
    object_id = models.PositiveBigIntegerField(null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    state = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("State"),
        encoder=DjangoJSONEncoder,
    )

    objects = FlowRunManager()

    class Meta:
        verbose_name = _("Flow Run")
        verbose_name_plural = _("Flow Runs")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.flow.name} - {self.status}"

    def clean(self):
        """
        Custom validation to ensure that the flow is active when creating a run.
        """
        if self.action and not self.action.flow_id == self.flow_id:
            raise ValidationError(_("Action does not belong to the flow."))

    def append_log(self, message: str):
        """
        Append a message to the flow run log.
        """
        if self.log:
            self.log += "\n"
        self.log += message


def get_trigger_choices():
    """
    Returns a list of tuples containing all available triggers.
    This is used to populate the choices for the trigger field in the Trigger model.
    """
    return trigger_registry.get_trigger_choices()


class TriggerManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("flow")

    def get_active(self):
        """
        Returns all active triggers that are currently listening for events.
        """
        return self.get_queryset().filter(active_at__lte=timezone.now())

    def get_active_for_trigger_name(self, trigger_name: str):
        return (
            self.get_active()
            .filter(trigger=trigger_name, flow__active_at__lte=timezone.now())
            .select_related("flow")
        )


class Trigger(models.Model):
    flow = models.ForeignKey(
        Flow,
        on_delete=models.CASCADE,
        related_name="triggers",
        verbose_name=_("Flow"),
    )

    trigger = models.CharField(
        max_length=MAX_TRIGGER_NAME_LENGTH,
        choices=get_trigger_choices,
        verbose_name=_("Trigger Name"),
        help_text=_("Name of the trigger to listen for"),
    )

    active_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Active Since"),
        help_text=_("The time when this trigger starts being active"),
    )

    objects = TriggerManager()

    class Meta:
        verbose_name = _("Flow Trigger")
        verbose_name_plural = _("Flow Triggers")
        constraints = [
            models.UniqueConstraint(
                fields=["flow", "trigger"],
                name="unique_flow_trigger",
            )
        ]

    def __str__(self):
        trigger = self.get_trigger()
        if trigger:
            return f"{trigger} -> {self.flow.name}"
        return f"{self.trigger}(!) {self.flow.name}"

    def get_trigger(self) -> Optional[type[RegisteredTrigger]]:
        return trigger_registry.get_trigger(self.trigger)

    def is_active(self) -> bool:
        return self.active_at and self.active_at <= timezone.now()
