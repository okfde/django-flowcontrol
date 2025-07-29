# API

## Actions and Flow Control

### `flowcontrol.base.FlowDirective`

- `FlowDirective.CONTINUE`: Run the next action in the sequence.
- `FlowDirective.ENTER`: Run the sub-actions of the current action.
- `FlowDirective.LEAVE`: Run the parent action again (like `continue` in a loop)
- `FlowDirective.BREAK`: Run the parent action's next sibling (like `break` in a loop).
- `FlowDirective.ABORT`: Stop the flow run.
- `FlowDirective.SUSPEND`: Pause the execution of the flow run and continue with the action's next sibling at the time of the run's `continue_after` field.
- `FlowDirective.SUSPEND_AND_REPEAT`: Pause the execution of the flow run and re-run the action at the time of the run's `continue_after` field.

### `flowcontrol.base.BaseAction`

Inherit from this for your own actions:

::: flowcontrol.base.BaseAction

### `flowcontrol.registry.register_action`

::: flowcontrol.registry.register_action

## Flow Triggers

The function to register a trigger returns a function that can be called to start the associated flows. It's optional to use these functions, you can also call the `flowcontrol.engine.trigger_flows` directly.

### `flowcontrol.registry.register_trigger`

::: flowcontrol.registry.register_trigger

### `flowcontrol.registry.register_trigger_as_signal_handler`

::: flowcontrol.registry.register_trigger_as_signal_handler

### `flowcontrol.engine.trigger_flows`

::: flowcontrol.engine.trigger_flows

## Flow Control Engine

### `flowcontrol.engine.create_flowrun`

::: flowcontrol.engine.create_flowrun

### `flowcontrol.engine.start_flowrun`

::: flowcontrol.engine.start_flowrun

### `flowcontrol.engine.execute_flowrun`

::: flowcontrol.engine.execute_flowrun

### `flowcontrol.engine.cancel_flowrun`

::: flowcontrol.engine.cancel_flowrun

### `flowcontrol.engine.continue_flowruns`

::: flowcontrol.engine.continue_flowruns
