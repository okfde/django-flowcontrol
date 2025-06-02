from collections import defaultdict

from django import forms
from django.contrib import admin
from django.core.exceptions import (
    PermissionDenied,
)
from django.db.models import Count, Q
from django.forms.models import modelform_factory
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from treebeard.admin import TreeAdmin
from treebeard.forms import movenodeform_factory

from .engine import execute_flow_run
from .models import Flow, FlowAction, FlowRun, Trigger
from .registry import action_registry


@admin.register(Flow)
class FlowAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "edit_actions",
        "created_at",
        "updated_at",
    )

    @admin.display(description=_("Actions"))
    def edit_actions(self, obj):
        return format_html(
            '<a class="button" href="{}">{}</a>',
            reverse("admin:flowcontrol-flow-list_actions", args=[obj.id]),
            _("Edit Actions"),
        )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<path:object_id>/add-action/",
                self.admin_site.admin_view(self.add_action_view),
                name="flowcontrol-flow-add_action",
            ),
            path(
                "<path:object_id>/list-actions/",
                self.admin_site.admin_view(self.changelist_actions_view),
                name="flowcontrol-flow-list_actions",
            ),
            path(
                "<path:object_id>/list-actions/move/",
                self.admin_site.admin_view(self.move_actions_view),
                name="flowcontrol-flow-move_actions",
            ),
            path(
                "<path:object_id>/change-action/<path:action_id>/",
                self.admin_site.admin_view(self.change_action_view),
                name="flowcontrol-flow-change_action",
            ),
            path(
                "actions/<path:action_id>/",
                self.admin_site.admin_view(self.redirect_to_action),
                name="flowcontrol_flowaction_change",
            ),
            path(
                "flowactions/",
                self.admin_site.admin_view(self.redirect_to_flows),
                name="flowcontrol_flowaction_changelist",
            ),
        ]
        return custom_urls + urls

    def redirect_to_flows(self, request):
        """
        Redirect to the change view of a FlowAction.
        This is used to handle the URL structure for actions.
        """
        return redirect("admin:flowcontrol_flow_changelist")

    def redirect_to_action(self, request, action_id):
        """
        Redirect to the change view of a FlowAction.
        This is used to handle the URL structure for actions.
        """
        action = FlowAction.objects.get(id=action_id)
        flow = action.flow
        return redirect("admin:flowcontrol-flow-change_action", flow.id, action.id)

    def get_flowaction_admin(self, flow):
        return FlowActionSubAdmin(
            model=FlowAction, admin_site=self.admin_site, flow=flow
        )

    def move_actions_view(self, request, object_id):
        flow = self.get_object(request, object_id)
        return self.get_flowaction_admin(flow).move_node(request)

    def add_action_view(self, request, object_id, form_url="", extra_context=None):
        flow = self.get_object(request, object_id)
        return self.get_flowaction_admin(flow).add_view(
            request, form_url=form_url, extra_context=extra_context
        )

    def changelist_actions_view(
        self, request, object_id, form_url="", extra_context=None
    ):
        flow = self.get_object(request, object_id)
        return self.get_flowaction_admin(flow).changelist_view(
            request, extra_context=extra_context
        )

    def change_action_view(
        self, request, object_id, action_id, form_url="", extra_context=None
    ):
        flow = self.get_object(request, object_id)
        return self.get_flowaction_admin(flow).change_view(
            request, object_id=action_id, form_url=form_url, extra_context=extra_context
        )


def get_action_choices():
    groups = defaultdict(list)
    for name, klass in action_registry.actions.items():
        group = klass.group
        groups[group].append((name, getattr(klass, "verbose_name", name)))

    groups = sorted(groups.items(), key=lambda x: str(x[0]))

    return [
        (group, sorted(actions, key=lambda x: str(x[1]))) for group, actions in groups
    ]


class ChooseFlowActionForm(forms.ModelForm):
    flow = forms.ModelChoiceField(
        queryset=Flow.objects.all(),
        widget=forms.HiddenInput(),
        required=True,
        label=_("Flow"),
        help_text=_("The flow to which the action will be added."),
    )
    action = forms.ChoiceField(
        choices=None,
        label=_("Action Type"),
        help_text=_("Select the type of action to add to the flow."),
    )

    class Meta:
        model = FlowAction
        fields = ("action",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["action"].choices = get_action_choices()

    def get_action_class(self):
        action_name = self.cleaned_data.get("action")
        return action_registry.get_action(action_name)


class FlowActionSubAdmin(TreeAdmin):
    add_form_template = "flowcontrol/admin/flowaction_add.html"
    change_list_template = "flowcontrol/admin/flowaction_changelist.html"
    save_as = False
    save_on_top = False
    save_as_continue = False

    choose_action_key = "action"
    exclude = ("path", "depth", "numchild")

    list_display = ("action_name", "description_label", "config", "run_count")

    def __init__(self, model, admin_site, flow):
        self.flow = flow
        super().__init__(model, admin_site)

    @admin.display(description=_("Action"))
    def action_name(self, obj):
        return format_html(
            '<a href="{href}">{name}</a>',
            href=reverse(
                "admin:flowcontrol-flow-change_action", args=[self.flow.id, obj.id]
            ),
            name=str(obj),
        )

    @admin.display(description=_("Description"))
    def description_label(self, obj):
        # This disables sorting of description column
        return obj.description

    @admin.display(description=_("Configuration"))
    def config(self, obj):
        config = obj.get_config()
        if not config:
            return mark_safe("<em>-</em>")
        return str(config)

    @admin.display(description=_("Runs waiting on this action"))
    def run_count(self, obj):
        return obj.run_count

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.filter(flow=self.flow)
        qs = qs.annotate(
            run_count=Count(
                "runs", distinct=True, filter=Q(runs__status=FlowRun.Status.WAITING)
            )
        )
        return qs

    def get_object(self, request, object_id, from_field=None):
        obj = super().get_object(request, object_id, from_field)
        if obj is None:
            return None
        config = obj.get_config()
        if config is None:
            return obj
        return config

    def chosen_action_class(self, request):
        form = ChooseFlowActionForm(data=request.POST or request.GET)
        if form.is_valid():
            return form.get_action_class()

    def get_adminform_for_model(self, request, model, action, obj):
        if obj is None:
            form_class = movenodeform_factory(model)
        else:
            form_class = modelform_factory(model, exclude=("depth", "path", "numchild"))
        form_class.base_fields["flow"].initial = self.flow
        form_class.base_fields["flow"].widget = forms.HiddenInput()
        form_class.base_fields["action"].initial = action
        form_class.base_fields["action"].widget = forms.HiddenInput()
        return form_class

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj:
            action_class = obj.get_action_class()
        else:
            action_class = self.chosen_action_class(request)
        if action_class:
            # If we have a specific action class, return its admin form
            return self.get_adminform_for_model(
                request, action_class.model or FlowAction, action_class.get_name(), obj
            )
        form_class = type(ChooseFlowActionForm.__name__, (ChooseFlowActionForm,), {})
        form_class.base_fields["flow"].initial = self.flow
        return form_class

    def save_model(self, request, new_object, form, change=False, **kwargs):
        """
        Save the FlowAction instance with the flow set.
        """
        return super().save_model(request, new_object, form, change, **kwargs)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context.update({"flow": self.flow})
        return super().changelist_view(request, extra_context=extra_context)

    def add_view(self, request, form_url="", extra_context=None):
        extra_context = extra_context or {}
        if not self.has_add_permission(request):
            raise PermissionDenied
        action_class = self.chosen_action_class(request)

        if not action_class:
            title = _("Choose action to add to flow '{flow}'").format(
                flow=self.flow.name
            )
        else:
            title = _("Add '{action}' action to flow '{flow}'").format(
                action=action_class.verbose_name, flow=self.flow.name
            )
        extra_context.update(
            {"title": title, "flow": self.flow, "action": action_class}
        )
        return super().add_view(request, form_url=form_url, extra_context=extra_context)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return super().change_view(
            request, object_id, form_url=form_url, extra_context=extra_context
        )

    def response_add(self, request, obj, post_url_continue=None):
        """
        Handle the response after adding a new FlowAction.
        Redirects to the flow's action list if successful.
        """
        return self.response_change(request, obj)

    def response_change(self, request, obj):
        """
        Handle the response after changing a FlowAction.
        Redirects to the flow's action list if successful.
        """
        if "_addanother" in request.POST:
            return redirect("admin:flowcontrol-flow-add_action", self.flow.id)
        elif "_continue" in request.POST:
            return redirect(
                "admin:flowcontrol-flow-change_action", self.flow.id, obj.id
            )
        else:
            return redirect("admin:flowcontrol-flow-list_actions", self.flow.id)


@admin.register(FlowRun)
class FlowRunAdmin(admin.ModelAdmin):
    add_form = modelform_factory(
        FlowRun, exclude=("status", "outcome", "action", "parent_run", "created_at")
    )

    list_display = (
        "flow",
        "content_object",
        "status",
        "outcome",
        "created_at",
        "continue_after",
        "done_at",
    )
    list_filter = ("status", "outcome")
    search_fields = ("flow__name",)
    readonly_fields = (
        "created_at",
        "done_at",
        "parent_run",
        "trigger",
    )

    actions = ["execute_flow_run"]

    @admin.display(description=_("Content Object"))
    def content_object(self, obj):
        return obj.content_object

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return (
                self.readonly_fields
                + (
                    "action",
                    "status",
                    "outcome",
                )
                if obj
                else self.readonly_fields
            )
        return self.readonly_fields

    def get_form(self, request, obj=None, **kwargs):
        """
        Use special form during foo creation
        """
        if obj is None:
            return self.add_form
        return super().get_form(request, obj, **kwargs)

    @admin.action(description=_("Execute selected flow runs"))
    def execute_flow_run(self, request, queryset):
        """
        Custom action to execute selected flow runs.
        This is a placeholder for the actual execution logic.
        """
        for run in queryset:
            run.done_at = None
            run.status = FlowRun.Status.PENDING
            execute_flow_run(run)


@admin.register(Trigger)
class TriggerAdmin(admin.ModelAdmin):
    list_display = (
        "trigger_label",
        "flow",
        "is_active",
        "active_at",
    )
    list_filter = ("flow",)
    search_fields = ("trigger", "flow__name")

    @admin.display(description=_("Trigger"))
    def trigger_label(self, obj):
        trigger = obj.get_trigger()
        if trigger:
            label = str(trigger)
        else:
            label = f"{obj.trigger} (missing!)"
        return format_html(
            '<a href="{href}">{name}</a>',
            href=reverse("admin:flowcontrol_trigger_change", args=[obj.id]),
            name=label,
        )

    @admin.display(description=_("Active"), boolean=True)
    def is_active(self, obj):
        return obj.is_active()

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("flow")
