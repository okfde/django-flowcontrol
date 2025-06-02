from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory
from django.utils import timezone

import pytest

from flowcontrol.actions import SetStateAction
from flowcontrol.models import Flow, FlowRun, Trigger
from flowcontrol.registry import action_registry
from flowcontrol.utils import ActionNode, make_action_tree


@pytest.fixture
def flow(db):
    return Flow.objects.create(name="Test Flow", active_at=timezone.now())


@pytest.fixture
def user(db):
    return User.objects.create(username="testuser")


@pytest.fixture
def trigger(flow):
    return Trigger.objects.create(
        flow=flow, trigger="trigger_name", active_at=timezone.now()
    )


@pytest.fixture
def flow_run(flow, user):
    ct = ContentType.objects.get_for_model(user)
    return FlowRun.objects.create(
        flow=flow,
        content_type=ct,
        object_id=user.pk,
        state={},
        status=FlowRun.Status.PENDING,
    )


@pytest.fixture
def admin_user(django_user_model):
    return django_user_model.objects.create_superuser(
        username="admin", email="admin@example.com", password="password"
    )


@pytest.fixture
def flow_action(db, flow):
    make_action_tree(
        flow,
        [
            ActionNode(SetStateAction, {"state": {"foo": "bar"}}),
        ],
    )
    return flow.actions.first()


DEFAULT_CONFIG = {
    "StartFlowAction": lambda: {
        "start_flow": Flow.objects.create(name="Empty Flow", active_at=timezone.now())
    },
}


@pytest.fixture
def flow_with_all_actions(flow):
    make_action_tree(
        flow,
        [
            ActionNode(klass, DEFAULT_CONFIG.get(name, lambda: {})())
            for name, klass in action_registry.actions.items()
        ],
    )
    return flow


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture
def temp_registry():
    """
    Fixture to provide a temporary action registry for testing.
    This allows tests to run without affecting the global action registry.
    """
    from flowcontrol.registry import action_registry, trigger_registry

    original_actions = action_registry.actions.copy()
    original_triggers = trigger_registry.triggers.copy()
    yield
    action_registry.actions = original_actions
    trigger_registry.triggers = original_triggers
