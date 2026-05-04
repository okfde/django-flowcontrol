import inspect
import json
from typing import Iterator

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext as _

from .utils import get_engine


class ConditionExpressionWidget(forms.Textarea):
    """
    A widget that renders a boolean expression widget.
    """

    template_name = "flowcontrol/widgets/condition_expression.html"

    class Media:
        js = ["flowcontrol/js/condition.js"]

    def __init__(self, content_type=None, attrs=None):
        self.content_type = content_type
        super().__init__(attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["config_id"] = f"{self.attrs.get('id', '')}_config"
        context["config"] = json.dumps(
            {
                "operators": [
                    {"value": "and", "label": _("and")},
                    {"value": "or", "label": _("or")},
                ],
                "filters": get_filters(),
                "operand_types": [
                    {"value": "object", "label": _("Object")},
                    {"value": "state", "label": _("Flow State")},
                    {"value": "string", "label": _("String value")},
                    {"value": "number", "label": _("Number value")},
                ],
                "object_attributes": get_object_attributes(self.content_type),
                "comparisons": [
                    {"value": "true", "label": _("is truthy")},
                    {"value": "false", "label": _("is falsy")},
                    {"value": "==", "label": _("is equal")},
                    {"value": "!=", "label": _("is not equal")},
                    {"value": ">", "label": _("greater")},
                    {"value": ">=", "label": _("greater or equal")},
                    {"value": "<", "label": _("less")},
                    {"value": "<=", "label": _("less or equal")},
                    {"value": "in", "label": _("is contained in")},
                    {"value": "not in", "label": _("is not contained in")},
                ],
            }
        )
        return context


def get_object_attributes(ct: ContentType | None) -> dict[str, str]:
    """
    Returns a list of attribute names for the given content type's model class.
    This is used to provide autocomplete suggestions for condition expressions.
    """
    result = [{"value": "", "label": _("(object itself)")}]
    if ct is None:
        return result
    model = ct.model_class()
    if not model:
        return result
    return result + [
        {"value": field.name, "label": field.name} for field in model._meta.get_fields()
    ]


def get_filters() -> list[dict[str, str]]:
    return sorted(yield_filters(), key=lambda x: x["name"])


def yield_filters() -> Iterator[dict[str, str]]:
    engine = get_engine()
    for lib in engine.template_builtins:
        for key in lib.filters:
            params = inspect.signature(lib.filters[key]).parameters
            argument = None
            if len(params) >= 2:
                second_key = list(params.keys())[1]
                param_annotation = params[second_key].annotation
                if param_annotation:
                    argument = param_annotation.__name__
                if argument == "_empty":
                    argument = "any"
            yield {"name": key, "argument": argument}
