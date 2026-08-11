"""`@ui_call` and `@ui_page`: registering decorators, not builders (§5.8)."""

import pytest

from astra_plugin_sdk import (
    NotConfigured,
    Plugin,
    ui_call,
    ui_effect,
    ui_overlay,
    ui_page,
)
from astra_plugin_sdk.testing import Harness


@ui_page("stats", "Stats", "http://127.0.0.1:8123/stats.html", icon_svg="<svg/>")
@ui_effect("http://127.0.0.1:8123/snow.html", audio=True)
@ui_overlay("clock", "http://127.0.0.1:8123/clock.html", url_width=120, url_height=40)
class _Panelled(Plugin):
    def __init__(self):
        super().__init__()
        self.operations = 0

    @ui_call
    async def get_stats(self, since: str = ""):
        return {"operations": self.operations, "since": since}

    @ui_call("reset-stats")
    async def reset_stats(self):
        self.operations = 0
        return {"ok": True}

    @ui_call
    async def needs_key(self):
        raise NotConfigured("api_key")

    @ui_call
    async def anything(self, **params):
        return {"got": sorted(params)}


class _Plain(Plugin):
    pass


def test_a_decorated_page_is_declared_without_any_further_code():
    """The bug §5.8 names: a builder whose return value nobody plumbed."""
    with Harness(_Panelled()) as h:
        contributions = {c.id: c for c in h.ui_contributions()}
    assert set(contributions) == {"stats", "effect", "clock"}
    assert contributions["stats"].slot == "page.custom"
    assert contributions["stats"].label == "Stats"
    assert contributions["stats"].icon_svg == "<svg/>"
    assert contributions["effect"].transparent and not contributions["effect"].pointer_events
    assert contributions["effect"].props["audio"] == "true"
    assert (contributions["clock"].width, contributions["clock"].height) == (120, 40)


def test_decorator_order_is_the_order_the_ui_gets():
    with Harness(_Panelled()) as h:
        assert [c.id for c in h.ui_contributions()] == ["stats", "effect", "clock"]


def test_a_plugin_with_no_decorators_declares_nothing():
    with Harness(_Plain()) as h:
        assert h.ui_contributions() == []


def test_contributions_do_not_leak_between_plugin_classes():
    """A class-level list appended in place would give every plugin every page."""

    @ui_page("only-mine", "Mine", "u")
    class _One(Plugin):
        pass

    class _Two(Plugin):
        pass

    with Harness(_One()) as h1, Harness(_Two()) as h2:
        assert [c.id for c in h1.ui_contributions()] == ["only-mine"]
        assert h2.ui_contributions() == []


def test_a_subclass_inherits_its_parents_pages_without_doubling_them():
    @ui_page("base", "Base", "u")
    class _Base(Plugin):
        pass

    @ui_page("child", "Child", "u")
    class _Child(_Base):
        pass

    with Harness(_Child()) as h:
        assert [c.id for c in h.ui_contributions()] == ["child", "base"]
    with Harness(_Base()) as h:
        assert [c.id for c in h.ui_contributions()] == ["base"]


# ── @ui_call ────────────────────────────────────────────────────────────────


def test_a_ui_call_is_reachable_by_its_method_name():
    with Harness(_Panelled()) as h:
        assert h.ui_call("get_stats", since="today").json == {
            "operations": 0,
            "since": "today",
        }


def test_a_ui_call_can_be_named_something_python_cannot_spell():
    with Harness(_Panelled()) as h:
        assert h.ui_call("reset-stats").json == {"ok": True}


def test_a_handler_taking_kwargs_gets_the_whole_payload():
    with Harness(_Panelled()) as h:
        assert h.ui_call("anything", a=1, b=2).json == {"got": ["a", "b"]}


def test_an_unknown_method_is_NOT_FOUND_and_lists_what_there_is():
    with Harness(_Panelled()) as h:
        result = h.ui_call("nope")
    assert not result.success
    assert result.code == "NOT_FOUND"
    assert "get_stats" in result.error


def test_a_plugin_with_no_ui_calls_says_so_usefully():
    with Harness(_Plain()) as h:
        result = h.ui_call("anything")
    assert result.code == "NOT_FOUND"
    assert "@ui_call" in result.error


def test_a_ui_call_failure_carries_the_config_field_the_panel_links_to():
    with Harness(_Panelled()) as h:
        result = h.ui_call("needs_key")
    assert result.code == "NOT_CONFIGURED"
    assert result.config_field == "api_key"


def test_ui_page_on_a_method_says_to_move_it_to_the_class():
    with pytest.raises(TypeError, match="CLASS"):

        class _Wrong(Plugin):
            @ui_page("x", "X", "u")
            async def handler(self):
                ...


def test_an_override_of_handle_ui_call_still_wins():
    """Manual routing has to keep working; the default is a default."""

    class _Manual(Plugin):
        async def handle_ui_call(self, method, params_json):
            return {"result_json": f'{{"method":"{method}"}}'}

    with Harness(_Manual()) as h:
        assert h.ui_call("whatever").json == {"method": "whatever"}
