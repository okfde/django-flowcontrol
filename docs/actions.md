# Define your own actions

An Action is Python class with a `run` method that takes the parameters `run`, `obj`, and `config`. The `run` method should return a `FlowDirective` to control the flow execution.

```python
from flowcontrol.base import BaseAction
from flowcontrol.registry import register_action

@register_action  # <-- The action needs to be registered
class MyAction(BaseAction):
    name = "My Action"
    description = "This is my custom action."
    # Optional group name for categorizing actions in the admin interface
    group = "My Custom Actions"
    # Set to True if this action can have sub-actions
    has_children = True

    def run(
        self,
        *,
        run: FlowRun,
        obj: Optional[Model] = None,
        config: Optional[Model] = None,
    ) -> FlowDirective:
        # your action logic goes here
        # You can acces the flow run's context with `self.get_context()`

        # Return a FlowDirective to control the further flow execution
        return FlowDirective.CONTINUE

    def return_from_children(
        self,
        *,
        run: "FlowRun",
        obj: Optional[Model] = None,
        config: Optional[Model] = None,
    ) -> Optional[FlowDirective]:
        # Optional method to handle when control flow is returned from sub-actions.
        return FlowDirective.CONTINUE
```

## Action Configuration

The action can have an optional configuration model that stores per flow configuration. They are normal Django models but need to be inherited from `flowcontrol.core.ActionBase` and **MUST NOT** define the following fields:

- `id`
- `path`
- `depth`
- `numchild`
- `flow`
- `created_at`
- `description`
- `action`
- `flowaction_ptr`

Here's an example of how to define a configuration model for your action:

```python
from flowcontrol.base import BaseAction
from flowcontrol.registry import register_action

from myapp.models import MyActionConfig

class MyAction(BaseAction):
    name = "My Action"
    description = "This is my custom action."
    model = MyActionConfig

    def run(self, run, obj=None, config=None):
        ...

# in you models.py

from flowcontrol.core import ActionBase

class MyActionConfig(ActionBase):
    config_value = models.IntegerField(default=0)

```
