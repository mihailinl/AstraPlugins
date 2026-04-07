"""TextUtils — Astra plugin with tools, actions, and triggers for text processing."""

import asyncio
import base64
import re
from datetime import datetime

from astra_plugin_sdk import Plugin, tool, action, trigger, Field


class TextUtils(Plugin):
    """Text processing plugin: word count, case conversion, regex, transforms."""

    def __init__(self):
        super().__init__()
        self.max_text_length = 10000
        self.operations_count = 0
        self._last_fired_minute: str = ""

    # -- Tools (auto-registered via @tool) --

    @tool("Count words, characters, and lines in text.")
    async def word_count(self, text: str):
        if len(text) > self.max_text_length:
            raise ValueError(f"Text exceeds max length ({self.max_text_length})")
        self.operations_count += 1
        return {
            "words": len(text.split()),
            "characters": len(text),
            "lines": text.count("\n") + (1 if text else 0),
        }

    @tool("Convert text case: upper, lower, title, snake, camel.")
    async def case_convert(self, text: str, mode: str):
        self.operations_count += 1
        return self._convert_case(text, mode)

    @tool("Test a regex pattern against text and return matches.")
    async def regex_match(self, text: str, pattern: str):
        self.operations_count += 1
        matches = re.findall(pattern, text)
        return {"pattern": pattern, "matches": matches, "count": len(matches)}

    # -- Action (auto-registered via @action) --

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
        self.operations_count += 1
        if operation == "upper":
            return input_text.upper()
        elif operation == "lower":
            return input_text.lower()
        elif operation == "title":
            return input_text.title()
        elif operation == "reverse":
            return input_text[::-1]
        elif operation == "base64_encode":
            return base64.b64encode(input_text.encode()).decode()
        elif operation == "base64_decode":
            return base64.b64decode(input_text.encode()).decode()
        else:
            raise ValueError(f"Unknown operation: {operation}")

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

    async def _time_loop(self):
        """Background loop: fire on_time trigger every minute when time matches."""
        while True:
            await asyncio.sleep(30)
            if "on_time" not in self.active_triggers:
                continue  # nobody listening, skip
            now = datetime.now().strftime("%H:%M")
            if now != self._last_fired_minute:
                self._last_fired_minute = now
                try:
                    await self.fire_trigger("on_time", {"time": now})
                except Exception as e:
                    print(f"on_time trigger error: {e}")

    # -- Lifecycle --

    async def on_config_changed(self, config: dict):
        self.max_text_length = config.get("max_text_length", 10000)
        if not hasattr(self, "_time_task"):
            self._time_task = asyncio.create_task(self._time_loop())

    async def health_check(self):
        return True, f"ok — {self.operations_count} operations processed"

    # -- Helpers --

    @staticmethod
    def _convert_case(text: str, mode: str) -> str:
        if mode == "upper":
            return text.upper()
        elif mode == "lower":
            return text.lower()
        elif mode == "title":
            return text.title()
        elif mode == "snake":
            s = re.sub(r"([A-Z])", r"_\1", text).lower()
            s = re.sub(r"[\s\-]+", "_", s)
            return s.strip("_")
        elif mode == "camel":
            words = re.split(r"[\s_\-]+", text)
            if not words:
                return ""
            return words[0].lower() + "".join(w.capitalize() for w in words[1:])
        return text


if __name__ == "__main__":
    TextUtils().run()
