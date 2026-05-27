from django import template
from django.contrib.contenttypes.models import ContentType

from ..models import FlowRun

register = template.Library()


@register.filter
def get_flowruns(obj):
    ct = ContentType.objects.get_for_model(obj)
    return FlowRun.objects.filter(content_type=ct, object_id=obj.pk).select_related(
        "flow", "trigger", "action", "waiting_trigger"
    )
