from django.conf import settings

FLOWCONTROL_DEFAULT_FILTERS = ["flowcontrol.filters"]


def get_flowcontrol_filters():
    disable_filters = bool(
        getattr(settings, "FLOWCONTROL_DISABLE_DEFAULT_FILTERS", False)
    )
    return ([] if disable_filters else FLOWCONTROL_DEFAULT_FILTERS) + getattr(
        settings, "FLOWCONTROL_TEMPLATE_FILTERS", []
    )
