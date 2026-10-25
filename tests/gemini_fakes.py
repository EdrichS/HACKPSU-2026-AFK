"""A stand-in for google.genai.Client, shared by the Gemini tests. No network."""

import json
from types import SimpleNamespace


class FakeGemini:
    """Answers the facts call and the card call separately, telling them apart by their schema.

    Each reply is a dict (sent back as JSON), a raw string, or an exception to raise.
    """

    def __init__(self, facts=..., card=...):
        self.replies = {
            "facts": {"new_facts": []} if facts is ... else facts,
            "card": {"small_context": "Card"} if card is ... else card,
        }
        self.calls = []  # (kind, kwargs)
        self.models = self

    def generate_content(self, **kwargs):
        kind = "facts" if "new_facts" in kwargs["config"].response_json_schema["properties"] else "card"
        self.calls.append((kind, kwargs))
        reply = self.replies[kind]
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(text=reply if isinstance(reply, str) or reply is None else json.dumps(reply))

    def kinds(self):
        return [kind for kind, _ in self.calls]

    def contents(self, kind):
        return next(kw["contents"] for k, kw in self.calls if k == kind)
