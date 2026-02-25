import pytest

from flowcontrol.utils import evaluate_if


@pytest.mark.parametrize(
    "condition,context,result",
    [
        ["obj.slug|startswith:'test'", {"obj": {"slug": "test"}}, True],
        ["obj.slug|startswith:''", {"obj": {"slug": "test"}}, True],
        ["obj.slug|startswith:'bad'", {"obj": {"slug": "test"}}, False],
        ["obj.slug|startswith:'bad'", {"obj": {"slug": None}}, False],
        ["obj.slug|startswith:'bad'", {}, False],
    ],
)
def test_startswith_filter(condition: str, context: dict, result: bool):
    assert evaluate_if(condition, context) is result


def test_disable_default_filters(settings):
    settings.FLOWCONTROL_DISABLE_DEFAULT_FILTERS = True
    with pytest.raises(ValueError):
        evaluate_if("obj.slug|startswith:'test'", {"obj": {"slug": "test"}})


@pytest.fixture
def fake_filter_module():
    import sys

    from django import template

    class fakemodule:
        register = template.Library()

    def foobar(needle):
        return "foobar"

    fakemodule.register.filter(foobar)

    module_path = "flowcontrol.foobar"
    sys.modules[module_path] = fakemodule
    yield module_path
    del sys.modules[module_path]


def test_add_more_filters(settings, fake_filter_module):

    settings.FLOWCONTROL_TEMPLATE_FILTERS = [fake_filter_module]
    assert evaluate_if("obj.slug|foobar == 'foobar'", {"obj": {"slug": "test"}}) is True
