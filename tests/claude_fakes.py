"""A stand-in for anthropic.Anthropic, shared by the context tests. No network."""

import json
from types import SimpleNamespace


class FakeClaude:
    """Answers the facts call and the card call separately, telling them apart by their schema.

    Each reply is a dict (sent back as JSON text, as structured output does), a raw string, None,
    or an exception to raise.
    """

    def __init__(self, facts=..., card=...):
        self.replies = {
            "facts": {"new_facts": []} if facts is ... else facts,
            "card": {"small_context": "Card"} if card is ... else card,
        }
        self.calls = []  # (kind, kwargs)
        self.messages = self

    def create(self, **kwargs):
        kind = "facts" if "new_facts" in kwargs["output_config"]["format"]["schema"]["properties"] else "card"
        self.calls.append((kind, kwargs))
        reply = self.replies[kind]
        if isinstance(reply, Exception):
            raise reply
        text = reply if isinstance(reply, str) or reply is None else json.dumps(reply)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn")

    def kinds(self):
        return [kind for kind, _ in self.calls]

    def contents(self, kind):
        return next(kw["messages"][0]["content"] for k, kw in self.calls if k == kind)
