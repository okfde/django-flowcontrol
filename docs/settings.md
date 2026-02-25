# Settings

## `FLOWCONTROL_TEMPLATE_FILTERS`

Add template libraries with filters to the engine that evaluates conditions, e.g. int eh built-in action **If Condition** and in the condition for a trigger.

Example:

```python
# in settings.py
FLOWCONTROL_TEMPLATE_FILTERS = [
    "your_module.filters"
]

# in your_module/filters.py
from django import template

register = template.Library()


@register.filter
def is_foobar(input_str: str) -> bool:
    return input_str == "foobar"

```

## `FLOWCONTROL_DISABLE_DEFAULT_FILTERS`

By default `"flowcontrol.filter"` is added to the filters in the condition engine. Setting this to `False` will not add these. Django's default filters are still available.
