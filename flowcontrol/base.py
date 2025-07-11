from enum import IntEnum
from typing import TYPE_CHECKING, Optional

from django.db.models import Model
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from .models.core import FlowRun


class FlowDirective(IntEnum):
    CONTINUE = 0
    ENTER = 1
    LEAVE = 2
    BREAK = 3
    ABORT = 4
    SUSPEND = 5
    SUSPEND_AND_REPEAT = 6


class BaseAction:
    verbose_name = _("Base Action")
    model: Optional[Model] = None
    has_children: bool = False
    name: Optional[str] = None
    group: Optional[str] = None

    description = _("This is a base action class that should be extended.")

    @classmethod
    def get_name(cls) -> str:
        """
        Get the name of the action, uses the class name by default.
        """
        if cls.name is None:
            return cls.__name__
        return cls.name

    def _set_context(self, context):
        self.context = context

    def get_context(self):
        """
        Get the context for the action.
        This method can be overridden in subclasses to provide additional context.

        Returns:
            The context dictionary for the flow run.
        """
        return self.context

    def run(
        self,
        *,
        run: "FlowRun",
        obj: Optional[Model] = None,
        config: Optional[Model] = None,
    ) -> Optional[FlowDirective]:
        """
        Run the action and return a flow directive
        This method should be overridden in subclasses.

        Args:
            run (FlowRun): The FlowRun instance to execute.
            obj (Optional[Model]): The model instance associated with the action.
            config (Optional[Model]): The configuration model instance for the action.

        Returns:
            Optional[FlowDirective]: The flow directive indicating the next action to take.
                                     FlowDirective.CONTINUE is used if None.
        """
        raise NotImplementedError("Subclasses must implement this method.")

    def return_from_children(
        self,
        *,
        run: "FlowRun",
        obj: Optional[Model] = None,
        config: Optional[Model] = None,
    ) -> Optional[FlowDirective]:
        """
        This is run when returning from child actions to a parent action.

        Args:
            run (FlowRun): The FlowRun instance to execute.
            obj (Optional[Model]): The model instance associated with the action.
            config (Optional[Model]): The configuration model instance for the action.

        Returns:
            Optional[FlowDirective]: The flow directive indicating the next action to take.
                                     FlowDirective.CONTINUE is used if None.
        """
        if not self.has_children:
            return
        raise NotImplementedError("Subclasses must implement this method.")
