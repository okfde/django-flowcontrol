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
        Get the name of the action.
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
        Run the action on the given object.
        This method should be overridden in subclasses.
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
        Run the action on the given object.
        This method should be overridden in subclasses.
        """
        if not self.has_children:
            return
        raise NotImplementedError("Subclasses must implement this method.")
