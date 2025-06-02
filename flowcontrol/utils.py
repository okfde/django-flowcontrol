from datetime import timedelta
from typing import Any, NamedTuple

from django.core.exceptions import ValidationError
from django.template import Context
from django.template.base import Parser
from django.template.defaulttags import TemplateIfParser
from django.template.engine import Engine
from django.utils import timezone
from django.utils.text import smart_split
from django.utils.timesince import timesince
from django.utils.translation import ngettext_lazy

from .models.core import FlowAction


def evaluate_expression(expression: str, context: dict) -> Any:
    template_literal = make_expression(expression)
    return template_literal.eval(Context(context))


def make_expression(expression: str) -> Any:
    engine = Engine.get_default()
    parser = Parser("", engine.template_libraries, engine.template_builtins)
    return TemplateIfParser(parser, list(smart_split(expression))).parse()


def validate_template_condition(condition: str) -> None:
    """
    Validate that the condition is a valid Django template variable expression.
    Raises ValueError if the condition is invalid.
    """
    try:
        make_expression(condition)
    except Exception as e:
        raise ValidationError(f"Invalid condition '{condition}': {e}") from e


def evaluate_if(condition: str, context: dict) -> bool:
    """
    Evaluate a condition string in the context of a given dictionary.
    The condition should be a valid Django template variable expression.
    """
    try:
        return bool(evaluate_expression(condition, context))
    except Exception as e:
        raise ValueError(f"Error evaluating condition '{condition}': {e}") from e


def readable_timedelta(duration: timedelta):
    now = timezone.now()
    past = now - duration
    result = timesince(past, now=now, depth=6)
    if result.startswith("0\xa0"):
        result = ""
    seconds = duration.seconds % 60
    if seconds:
        if result:
            result += ", "
        result += ngettext_lazy("{num}\xa0second", "{num}\xa0seconds", "num").format(
            num=seconds
        )
    return result


class ActionNode(NamedTuple):
    action_class: type
    kwargs: dict = {}
    children: list["ActionNode"] = []


def make_action_tree(flow, node_list: list[ActionNode], parent_action=None):
    for tree_node in node_list:
        action_class, kwargs, children = tree_node
        action = (action_class.model or FlowAction)(
            flow=flow, action=action_class.get_name(), **kwargs
        )
        if parent_action is None:
            action = type(action).add_root(instance=action)
        else:
            action = parent_action.add_child(instance=action)

        make_action_tree(flow, children, action)
