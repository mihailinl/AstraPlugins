"""Desktop declarations and contextual routing must survive the real SDK servicer."""
from astra_plugin_sdk import Plugin, UiContribution, DesktopWidget, WidgetFormat, WidgetSurface, WidgetContext, Field
from astra_plugin_sdk.testing import Harness
from astra_plugin_sdk.capability_types import coerce
import pytest

@pytest.mark.parametrize("cls", [DesktopWidget, WidgetFormat, WidgetSurface, WidgetContext])
def test_widget_type_roundtrip_and_field_parity(cls):
    value=cls()
    assert cls.from_proto(value.to_proto()) == value
    assert set(cls.__dataclass_fields__) == {f.name for f in cls._PROTO.DESCRIPTOR.fields}

def test_nested_descriptor_keeps_constraints_config_and_views():
    widget=DesktopWidget(repeatable=True,
        formats=[WidgetFormat(id="list",label="List",url="index.html",max_w=8,min_pixel_width=220)],
        surfaces=[WidgetSurface.modal("settings","Settings","index.html",width=480)],
        config_fields=[Field.text("title","Title",default="My counter")],settings_surface="settings")
    contribution=UiContribution.widget("counter","Counter",widget)
    assert UiContribution.from_proto(contribution.to_proto()) == contribution
    assert contribution.slot == "desktop.widget"
    class Demo(Plugin):
        async def get_ui_contributions(self): return [contribution]
    with Harness(Demo()) as h:
        wire=h.ui_contributions()[0]
        assert wire.desktop_widget.formats[0].max_w == 8
        assert wire.desktop_widget.config_fields[0].default_value == "My counter"
        assert wire.desktop_widget.settings_surface == "settings"

def test_widget_context_reaches_override_and_legacy_calls_still_work():
    class Demo(Plugin):
        async def handle_ui_call(self, method, params_json): return {"legacy":method}
        async def handle_widget_ui_call(self, method, params_json, widget):
            if widget: return {"instance":widget.instance_id,"config":widget.config_json}
            return await super().handle_widget_ui_call(method,params_json,widget)
    with Harness(Demo()) as h:
        assert h.ui_call("ping").json == {"legacy":"ping"}
        for id in ["first","second"]:
            assert h.widget_ui_call("ping",WidgetContext(instance_id=id,config_json='{"title":"'+id+'"}')).json == {"instance":id,"config":'{"title":"'+id+'"}'}
