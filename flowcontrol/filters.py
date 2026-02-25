from django import template

register = template.Library()


@register.filter
def startswith(needle: str, prefix: str) -> bool:
    if needle is None:
        return False
    needle = str(needle)
    return needle.startswith(prefix)
