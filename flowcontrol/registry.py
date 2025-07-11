from dataclasses import dataclass
from typing import Callable, Optional

from django.db.models import Model

from .base import BaseAction

MAX_TRIGGER_NAME_LENGTH = 100
MAX_ACTION_NAME_LENGTH = 100


class ActionRegistry:
    def __init__(self):
        self.actions: dict[str, BaseAction] = {}

    def register(self, action_class: BaseAction):
        name = action_class.get_name()
        if not name:
            raise ValueError("Action name cannot be empty")
        if len(name) > MAX_ACTION_NAME_LENGTH:
            raise ValueError(
                f"Action name is too long, must be less than {MAX_ACTION_NAME_LENGTH + 1} characters"
            )
        if name in self.actions:
            raise ValueError(f"Action {name} is already registered")

        self.actions[name] = action_class

    def get_action(self, action_name):
        return self.actions.get(action_name)


action_registry = ActionRegistry()


def register_action(action_class):
    """Decorator to register an action class.

    Args:
        action_class (BaseAction): The action class to register.

    Returns:
        BaseAction: The registered action class.
    """
    action_registry.register(action_class)
    return action_class


@dataclass
class RegisteredTrigger:
    name: str
    model: Model | None
    label: str = ""
    description: str = ""

    def __str__(self):
        label = ""
        if self.label:
            label = f"{self.label} ({self.name})"
        else:
            label = self.name

        return f"{self.model._meta.label}: {label}" if self.model else label


class TriggerRegistry:
    def __init__(self):
        self.triggers: dict[str, Model] = {}

    def register(self, name, model_class, label="", description=""):
        if not name:
            raise ValueError("Trigger name cannot be empty")
        if len(name) > MAX_TRIGGER_NAME_LENGTH:
            raise ValueError(
                f"Trigger name is too long, must be less than {MAX_ACTION_NAME_LENGTH + 1} characters"
            )
        if name in self.triggers:
            raise ValueError(f"Trigger {name} is already registered")

        self.triggers[name] = RegisteredTrigger(
            name=name, model=model_class, label=label, description=description
        )

    def get_trigger(self, name):
        return self.triggers.get(name)

    def get_trigger_choices(self):
        return [(trigger.name, str(trigger)) for trigger in self.triggers.values()]


trigger_registry = TriggerRegistry()


def register_trigger(
    name: str, model: Optional[type] = None, label="", description=""
) -> Callable[[Optional[Model], Optional[dict], bool], None]:
    """Register the trigger name

    Args:
        name (str): Name of the trigger
        model (Optional[type], optional): The Django model object this trigger provides. Defaults to None.
        label (str, optional): A human readable label. Defaults to "".
        description (str, optional): A human readable description. Defaults to "".

    Returns:
        A function that can be used to execute the trigger.
    """
    trigger_registry.register(
        name=name, model_class=model, label=label, description=description
    )

    def trigger_function(
        obj: Optional[Model] = None,
        state: Optional[dict] = None,
        immediate: bool = False,
    ):
        from .engine import trigger_flows

        trigger_flows(name, obj, state=state, immediate=immediate)

    return trigger_function


def register_trigger_as_signal_handler(
    name: str, model: Optional[type] = None, label="", description=""
) -> Callable[[Model], None]:
    """
    Register a trigger and return a Django signal handler function.

    This is a shortcut to register a trigger and returns a function that can be used as a signal handler.

    Example:

    ```python
    post_save.connect(register_trigger_as_signal_handler("mymodel_postsave"))
    ```

    Args:
        name (str): Name of the trigger
        model (Optional[type], optional): The Django model object this trigger provides. Defaults to None.
        label (str, optional): A human readable label. Defaults to "".
        description (str, optional): A human readable description. Defaults to "".

    Returns:
        A Django signal handler function that triggers the associated flows with the sender as the associated object.
    """
    trigger_registry.register(
        name=name, model_class=model, label=label, description=description
    )

    def trigger_function(sender, **kwargs):
        from .engine import trigger_flows

        trigger_flows(name, sender)

    return trigger_function
