# Concepts

Here's an introduction to the main concepts of Django Flowcontrol.

## Flows

Flows define a sequence of actions (including possibly sub-sequences per action) that can be executed. A flow can define limits, e.g. on the number of concurrent runs per associated object.

## Actions

Actions are the building blocks of flows. They are arranged in a list with some actions allowing sub-actions. Each action can have its own configuration.

The built-in actions are:

- **If Condition**: Evaluates a condition and executes its sub-actions based on the result.
- **While Loop**: Continually runs its sub-actions when its condition is true.
- **For Loop**: Runs its sub-actions a number of times defined by a start, step and end value.
- **Return to action**: Returns control to the parent action. If there's no parent action, the flow is stopped.
- **Leave branch**: Runs the parent action's next sibling. If there's no parent action, the flow is stopped.
- **Stop Flow**: The flow is stopped.
- **Set state**: Set the flow run's state to the given JSON, optionally evaluating string values as Django template expressions.
- **Update state**: Update the flow run's state to the given JSON optionally evaluating string values as Django template expressions.
- **Start new flow**: Starts a new flow run based on a configured flow. The new run can start immediately or at a later time.
- **Delay**: Suspends the flow run for a configurable amount of time.

You can define your own actions by inheriting from `flowcontrol.base.BaseAction` and registering them with `flowcontrol.registry.register_action`.

## Flow Runs

A flow run is an instance of a flow that is currently being executed. It has a persistent state and can be associated with a model object. They can be waiting and be resumed at a defined later time.

Flows can be paused and set to resume at a later time. In order to resume flow runs, you need to regularly call the `flowcontrol.engine.continue_flowruns` function, e.g. in a cron job or a Celery periodic task. This will check for flow runs that are ready to be resumed and execute them. A celery task is provided for this purpose: `flowcontrol.tasks.continue_flowruns_task`.

## Triggers

Triggers can be defined in Python and can be e.g. Django signal handlers. They are registered with flow control and you can associate them in the Django admin interface with a flow. The flow will then be started when the trigger is executed.
