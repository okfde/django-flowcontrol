from django.contrib.admin.sites import AdminSite
from django.urls import reverse

import pytest

from flowcontrol.actions import IfAction, SetStateAction, UpdateStateAction
from flowcontrol.admin import (
    FlowAdmin,
)
from flowcontrol.models import Flow, FlowRun
from flowcontrol.models.core import FlowAction
from flowcontrol.registry import register_trigger
from flowcontrol.utils import ActionNode, make_action_tree


def test_flowadmin_custom_urls_registered(admin_user, rf):
    site = AdminSite()
    admin_obj = FlowAdmin(Flow, site)
    urls = admin_obj.get_urls()
    url_names = [u.name for u in urls]
    assert "flowcontrol-flow-add_action" in url_names
    assert "flowcontrol-flow-list_actions" in url_names
    assert "flowcontrol-flow-move_actions" in url_names


def test_flowaction_redirects(admin_user, client, flow_action):
    client.force_login(admin_user)
    flowaction_changelist_url = reverse("admin:flowcontrol_flowaction_changelist")
    resp = client.get(flowaction_changelist_url)
    assert resp.status_code == 302
    flow_changelist_url = reverse("admin:flowcontrol_flow_changelist")
    assert flow_changelist_url in resp.url
    flowaction_change_url = reverse(
        "admin:flowcontrol_flowaction_change", args=(flow_action.id,)
    )
    resp = client.get(flowaction_change_url)
    assert resp.status_code == 302
    flow_changeaction_url = reverse(
        "admin:flowcontrol-flow-change_action",
        args=(flow_action.flow.id, flow_action.id),
    )
    assert flow_changeaction_url in resp.url


def test_flowadmin_flow(admin_user, client, flow):
    client.force_login(admin_user)
    resp = client.get(reverse("admin:flowcontrol_flow_change", args=(flow.id,)))
    assert resp.status_code == 200


def test_flowadmin_flow_actions(admin_user, client, flow_with_all_actions, flow_action):
    client.force_login(admin_user)
    resp = client.get(reverse("admin:flowcontrol_flow_changelist"))
    assert resp.status_code == 200

    resp = client.get(
        reverse("admin:flowcontrol-flow-add_action", args=(flow_with_all_actions.id,))
    )
    assert resp.status_code == 200

    resp = client.get(
        reverse("admin:flowcontrol-flow-list_actions", args=(flow_with_all_actions.id,))
    )
    assert resp.status_code == 200

    resp = client.get(
        reverse(
            "admin:flowcontrol-flow-change_action",
            args=(flow_with_all_actions.id, flow_action.id),
        )
    )
    assert resp.status_code == 200

    flow_action.action = "bad-action"
    flow_action.save()
    resp = client.get(
        reverse(
            "admin:flowcontrol-flow-change_action",
            args=(flow_with_all_actions.id, flow_action.id),
        )
    )
    assert resp.status_code == 200

    resp = client.get(
        reverse(
            "admin:flowcontrol-flow-change_action",
            args=(flow_with_all_actions.id, "non-existing"),
        )
    )
    assert resp.status_code == 302


@pytest.mark.parametrize(
    "save_button,next_url",
    [
        ("_save", "/list-actions/"),
        ("_continue", "/change-action/"),
        ("_addanother", "/add-action/"),
    ],
)
def test_flowadmin_flow_add_action(
    admin_user, user, client, flow, save_button, next_url
):
    user.is_staff = True
    user.save()
    client.force_login(user)

    resp = client.post(
        reverse(
            "admin:flowcontrol-flow-add_action",
            args=(flow.id,),
        ),
        data={
            "flow": str(flow.id),
            "action": "BreakAction",
            "_next": "Next",
        },
    )
    assert resp.status_code == 403

    client.force_login(admin_user)

    resp = client.post(
        reverse(
            "admin:flowcontrol-flow-add_action",
            args=(flow.id,),
        ),
        data={
            "flow": str(flow.id),
            "action": "BreakAction",
            "_next": "Next",
        },
    )
    assert resp.status_code == 200
    assert flow.actions.count() == 0

    resp = client.post(
        reverse(
            "admin:flowcontrol-flow-add_action",
            args=(flow.id,),
        ),
        data={
            "flow": str(flow.id),
            "action": "BreakAction",
            "description": "Test Action",
            "_position": "first-child",
            **{save_button: "Button title"},
        },
    )

    assert resp.status_code == 302
    assert next_url in resp.url
    assert flow.actions.count() == 1


def test_flowadmin_flow_move_action(admin_user, client, flow):
    make_action_tree(
        flow,
        [
            ActionNode(SetStateAction, {"state": {"i": 0}}),
            ActionNode(
                IfAction,
                {"condition": "True"},
                [
                    ActionNode(
                        UpdateStateAction, {"state": {"i": "i|add:2"}, "evaluate": True}
                    ),
                ],
            ),
        ],
    )
    client.force_login(admin_user)

    root_nodes = FlowAction.get_root_nodes().filter(flow=flow)
    assert len(root_nodes) == 2
    assert root_nodes[0].action == "SetStateAction"
    assert root_nodes[1].action == "IfAction"

    move_node = flow.actions.get(action="IfAction")
    target_node = flow.actions.get(action="SetStateAction")
    resp = client.post(
        reverse(
            "admin:flowcontrol-flow-move_actions",
            args=(flow.id,),
        ),
        data={
            "node_id": str(move_node.id),
            "parent_id": "0",
            "sibling_id": str(target_node.id),
            "as_child": "0",
        },
    )
    assert resp.status_code == 200

    root_nodes = FlowAction.get_root_nodes().filter(flow=flow)
    assert len(root_nodes) == 2
    assert root_nodes[0].action == "IfAction"
    assert root_nodes[1].action == "SetStateAction"

    # Try illegal move
    # Move IfAction as child of SetStateAction
    move_node = flow.actions.get(action="IfAction")
    target_node = flow.actions.get(action="SetStateAction")
    resp = client.post(
        reverse(
            "admin:flowcontrol-flow-move_actions",
            args=(flow.id,),
        ),
        data={
            "node_id": str(move_node.id),
            "parent_id": "0",
            "sibling_id": str(target_node.id),
            "as_child": "1",
        },
    )
    assert resp.status_code == 200

    root_nodes = FlowAction.get_root_nodes().filter(flow=flow)
    assert len(root_nodes) == 2
    assert root_nodes[0].action == "IfAction"
    assert root_nodes[1].action == "SetStateAction"

    # Do legal move
    # Move SetStateAction as child of IfAction
    move_node = flow.actions.get(action="SetStateAction")
    target_node = flow.actions.get(action="IfAction")
    resp = client.post(
        reverse(
            "admin:flowcontrol-flow-move_actions",
            args=(flow.id,),
        ),
        data={
            "node_id": str(move_node.id),
            "parent_id": "0",
            "sibling_id": str(target_node.id),
            "as_child": "1",
        },
    )
    assert resp.status_code == 200

    root_nodes = FlowAction.get_root_nodes().filter(flow=flow)
    assert len(root_nodes) == 1
    assert root_nodes[0].action == "IfAction"


def test_flowrunadmin(admin_user, client, flow_run):
    client.force_login(admin_user)
    resp = client.get(reverse("admin:flowcontrol_flowrun_changelist"))
    assert resp.status_code == 200


def test_flowrunadmin_add(admin_user, client):
    client.force_login(admin_user)
    resp = client.get(reverse("admin:flowcontrol_flowrun_add"))
    assert resp.status_code == 200


def test_flowrunadmin_change(admin_user, client, flow_run):
    client.force_login(admin_user)
    resp = client.get(reverse("admin:flowcontrol_flowrun_change", args=(flow_run.id,)))
    assert resp.status_code == 200


def test_flowrunadmin_execute_flow_run_calls_execute(admin_user, client, flow_run):
    client.force_login(admin_user)

    assert flow_run.status == FlowRun.Status.PENDING
    assert flow_run.outcome == ""
    assert flow_run.done_at is None

    response = client.post(
        reverse("admin:flowcontrol_flowrun_changelist"),
        data={"action": "execute_flow_run", "_selected_action": [flow_run.id]},
    )
    assert response.status_code == 302

    flow_run.refresh_from_db()
    assert flow_run.status == FlowRun.Status.DONE
    assert flow_run.outcome == FlowRun.Outcome.COMPLETE
    assert flow_run.done_at is not None


def test_triggeradmin(admin_user, client, trigger):
    client.force_login(admin_user)
    resp = client.get(reverse("admin:flowcontrol_trigger_changelist"))
    assert resp.status_code == 200


def test_triggeradmin_label(admin_user, client, trigger, temp_registry):
    label = "Nice trigger label"
    register_trigger(trigger.trigger, label=label)
    client.force_login(admin_user)
    resp = client.get(reverse("admin:flowcontrol_trigger_changelist"))
    assert resp.status_code == 200
    assert label in str(resp.content)


def test_triggeradmin_no_label(admin_user, client, trigger, temp_registry):
    register_trigger(trigger.trigger)
    client.force_login(admin_user)
    resp = client.get(reverse("admin:flowcontrol_trigger_changelist"))
    assert resp.status_code == 200
    assert trigger.trigger in str(resp.content)


def test_triggeradmin_add(admin_user, client):
    client.force_login(admin_user)
    resp = client.get(reverse("admin:flowcontrol_trigger_add"))
    assert resp.status_code == 200


def test_triggeradmin_change(admin_user, client, trigger):
    client.force_login(admin_user)
    resp = client.get(reverse("admin:flowcontrol_trigger_change", args=(trigger.id,)))
    assert resp.status_code == 200
