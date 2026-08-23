"""TextUtils — Astra plugin with tools, actions, and triggers for text processing.

The Python reference example. It is deliberately small, and deliberately
complete: every failure it can have is a coded `ToolError` the daemon can act
on, everything it says goes through `logging` (which the SDK routes to Astra),
and `tests/` is a worked example of both levels of the SDK test harness.

It is also the worked example of `locales/` from a Python plugin, and of the
line between the two planes — which is a line about *who renders the string*,
not about how important it is:

* **Declared** — `[config] schema` in `plugin.toml` carries `$config.…` keys.
  The daemon resolves them per request, in whatever language the user has set
  *now*, out of the `locales/` copy it took at install. Nothing here re-renders
  and no hook is implemented.
* **Runtime** — `health_check` below. This process produces that sentence, and
  it has a count in it, so it is resolved here with `self.i18n.tn`.
* **Neither** — the action and trigger labels, and the `BadArguments` text. See
  the comments where each one is written; both are deliberate and both would be
  wrong to "fix" by adding a key.

`ru` and `uk` are the translations this example ships. They are the two
languages beyond English that this tree can proof-read, and a confidently wrong
sentence in a language nobody here can review is worse than an English one.
"""

import asyncio
import base64
import logging
import re
from datetime import datetime

from astra_plugin_sdk import (
    BadArguments,
    Field,
    Plugin,
    action,
    tool,
    trigger,
)

log = logging.getLogger(__name__)

CASE_MODES = ("upper", "lower", "title", "snake", "camel")
TRANSFORMS = ("upper", "lower", "title", "reverse", "base64_encode", "base64_decode")


class TextUtils(Plugin):
    """Text processing plugin: word count, case conversion, regex, transforms."""

    def __init__(self):
        super().__init__()
        self.max_text_length = 10000
        self.operations_count = 0
        self._last_fired_minute: str = ""
        self._time_task: asyncio.Task | None = None

    # -- Tools (auto-registered via @tool) --

    @tool("Count words, characters, and lines in text.")
    async def word_count(self, text: str):
        self._check_length(text)
        self.operations_count += 1
        return {
            "words": len(text.split()),
            "characters": len(text),
            "lines": text.count("\n") + (1 if text else 0),
        }

    @tool("Convert text case: upper, lower, title, snake, camel.")
    async def case_convert(self, text: str, mode: str):
        self._check_length(text)
        if mode not in CASE_MODES:
            # BAD_ARGUMENTS, not INTERNAL: the model is the caller here, and this
            # code is what tells it to try again with a different `mode` rather
            # than to give up and apologise to the user.
            #
            # And that is also why it is NOT in `locales/`: the reader is the
            # model, not the user, and `mode` is an English identifier either
            # way. Translating it would narrow the audience of the one sentence
            # whose whole job is to be understood by the caller.
            raise BadArguments(f"unknown mode {mode!r}; use one of {', '.join(CASE_MODES)}")
        self.operations_count += 1
        return self._convert_case(text, mode)

    @tool("Test a regex pattern against text and return matches.")
    async def regex_match(self, text: str, pattern: str):
        self._check_length(text)
        try:
            compiled = re.compile(pattern)
        except re.error as e:
            raise BadArguments(f"{pattern!r} is not a valid regular expression: {e}")
        self.operations_count += 1
        matches = compiled.findall(text)
        return {"pattern": pattern, "matches": matches, "count": len(matches)}

    # -- Action (auto-registered via @action) --
    #
    # LITERAL ENGLISH, deliberately, on every label below. `key("…")` would put
    # a `$key` on the wire and the daemon would resolve it per request — on a
    # daemon that has that resolver. The newest Astra RELEASE resolves `$` in
    # `[config] schema` and nowhere else, so a key here renders as the literal
    # text `$action.transform.label` in the command editor, which is a label a
    # user cannot act on. `min_astra_version` is the only thing that stops an
    # older daemon installing this plugin, and there is no release to name in
    # it yet.
    #
    # Which gate catches it, because the answer is not the obvious one:
    # `astra-plugin check`'s E17 refuses this in `[[ui.contributions]]` and
    # CANNOT see the labels below — an action is registered over gRPC at run
    # time and appears in no manifest. `astra-plugin test`'s `labels survive a
    # language round trip` probe is the one that can, because it starts the
    # process and asks. That probe is not on the release path, which runs
    # `check --strict` and `build`; the assertion in this plugin's own suite
    # (`test_the_command_editor_labels_are_literal_english_and_not_keys`) is
    # the copy that travels with the code.

    @action(
        "Transform Text",
        icon_svg='<svg viewBox="0 0 24 24"><path d="M3 7h18M3 12h18M3 17h12" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/></svg>',
        fields=[
            Field.dropdown("operation", "Operation", options=[
                ("upper", "UPPERCASE"),
                ("lower", "lowercase"),
                ("title", "Title Case"),
                ("reverse", "Reverse"),
                ("base64_encode", "Base64 Encode"),
                ("base64_decode", "Base64 Decode"),
            ], default="upper"),
            Field.textarea_with_variables("input_text", "Input Text",
                                          placeholder="Enter text to transform..."),
            Field.text("store_in", "Store Result In",
                       placeholder="variable_name",
                       description="Variable name to store the result",
                       conditions=[Field.condition("operation", "not_empty")]),
        ],
        ai_available=True,
        ai_description="Transform text using various operations like uppercase, reverse, base64",
        ai_primary_field="input_text",
    )
    async def transform_text(self, operation: str = "upper", input_text: str = "", **_):
        if operation not in TRANSFORMS:
            raise BadArguments(
                f"unknown operation {operation!r}; use one of {', '.join(TRANSFORMS)}"
            )
        self._check_length(input_text)
        self.operations_count += 1
        if operation == "upper":
            return input_text.upper()
        if operation == "lower":
            return input_text.lower()
        if operation == "title":
            return input_text.title()
        if operation == "reverse":
            return input_text[::-1]
        if operation == "base64_encode":
            return base64.b64encode(input_text.encode()).decode()
        try:
            return base64.b64decode(input_text.encode(), validate=True).decode()
        except Exception as e:
            raise BadArguments(f"that is not valid Base64: {e}")

    # -- Trigger (auto-registered via @trigger) --

    @trigger(
        "Scheduled Time",
        icon_svg='<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 7v5l3 3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
        fields=[
            Field.text("time", "Time", default="09:00", placeholder="HH:MM",
                        description="Time to trigger (24h format, e.g. 14:30)"),
        ],
    )
    def on_time(self):
        pass

    async def tick(self, now: str | None = None) -> bool:
        """One iteration of the schedule check. Returns whether it fired.

        Split out of the loop so a test can drive it with a fixed clock. A
        `while True: await sleep(30)` body is untestable, and "untestable" is how
        a trigger that fires twice a minute ships.
        """
        if "on_time" not in self.active_triggers:
            return False  # nobody listening, skip
        now = now or datetime.now().strftime("%H:%M")
        if now == self._last_fired_minute:
            return False  # already fired for this minute
        self._last_fired_minute = now
        try:
            await self.fire_trigger("on_time", {"time": now})
        except Exception as e:
            # The daemon refusing `fire_trigger` (a missing `[permissions]`
            # entry, a restart mid-call) must not kill the loop — the next
            # minute should still get a chance.
            log.error("on_time trigger failed: %s", e)
            return False
        return True

    async def _time_loop(self):
        while True:
            await asyncio.sleep(30)
            await self.tick()

    # -- Lifecycle --

    async def on_config_changed(self, config: dict):
        raw = config.get("max_text_length", 10000)
        try:
            self.max_text_length = max(1, int(raw))
        except (TypeError, ValueError):
            # A config hook has nowhere to report a failure, and refusing to
            # start over one bad field would take the whole plugin down. Keep
            # the last good value and say so.
            log.warning("max_text_length=%r is not a number; keeping %d", raw, self.max_text_length)
        if self._time_task is None:
            self._time_task = asyncio.create_task(self._time_loop())

    async def on_shutdown(self):
        if self._time_task is not None:
            self._time_task.cancel()
            self._time_task = None

    async def health_check(self):
        # RUNTIME plane. This sentence is produced by THIS process, and it
        # carries a count — which is the half the daemon structurally cannot
        # do for us, because it does not know the number. `tn` picks the row:
        # `en` has two, `ru` and `uk` have four, and `{n}` is passed rather
        # than formatted in, because a count that formats itself is a count
        # the translator cannot move to the other side of the noun.
        n = self.operations_count
        return True, self.i18n.tn("health.ok", n, n=str(n))

    # -- Helpers --

    def _check_length(self, text: str) -> None:
        if len(text) > self.max_text_length:
            raise BadArguments(
                f"text is {len(text)} characters; this plugin is configured to "
                f"accept at most {self.max_text_length}"
            )

    @staticmethod
    def _convert_case(text: str, mode: str) -> str:
        if mode == "upper":
            return text.upper()
        if mode == "lower":
            return text.lower()
        if mode == "title":
            return text.title()
        if mode == "snake":
            s = re.sub(r"([A-Z])", r"_\1", text).lower()
            s = re.sub(r"[\s\-]+", "_", s)
            return s.strip("_")
        # camel
        words = re.split(r"[\s_\-]+", text)
        if not words:
            return ""
        return words[0].lower() + "".join(w.capitalize() for w in words[1:])


if __name__ == "__main__":
    TextUtils().run()
