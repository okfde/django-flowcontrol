# django-flowcontrol

Django Flowcontrol is a Django app that allows creating and running flows of actions including branching and looping logic.

- Actions are defined in Python code and can have optional per-instance configuration. The app provides built-in actions for conditional logic, loops, and state management.
- Flows with their actions and triggers are defined in the Django admin.
- A running instance of a flow – a flow run – has persistent state and can have an optional model object associated with it.
