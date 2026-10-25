"""Nova: the assistant that answers questions from the database, out loud.

NovaBrain is Claude with three tools that read Postgres (the people, one person's facts, who is in
the room). It plugs into voice_rec.assistant.Assistant, which handles the wake word, barge-in and
speaking. The voices come from voice_rec.assistant too; PrintSpeaker stands in without audio.
"""

import logging
import time
from typing import Iterator

from anthropic import beta_tool

from db import context, people

log = logging.getLogger("live.nova")

MODEL = "claude-opus-5-5"


class NovaBrain:
    def __init__(
        self, client, pool, presence, code_name: str = "Nova", user_name: str = "the user", model: str = MODEL, introduce: bool = True
    ):
        self.client = client
        self.pool = pool
        self.presence = presence
        self.code_name = code_name
        self.user_name = user_name
        self.model = model
        self.introduce = introduce  # her first answer in a visit says who she is (new_visit starts the next)
        self.introduced = False
        self.participants: set[str] = set()  # voice_rec.assistant.Assistant fills this in
        self.system = (
            f"You are {code_name}, the voice assistant of a memory-care app. {user_name} is its user: they wear the "
            f"glasses the camera and microphone are in, have dementia, and may ask who someone is, or about a "
            f"family member or friend. The family registered the people in {user_name}'s life in a database, "
            f"{user_name} included. Your tools read it: look a "
            f"person up before you say anything about them, and treat the database as the only source of truth. "
            f"Never guess or invent a fact; if someone isn't in the database, say kindly that you don't have them, "
            f"then say who is here, so a misheard name never ends in silence. If asked who "
            f"is here, use who_is_here. You are spoken aloud by text-to-speech, so answer the way a warm, patient "
            f"person talks: plain words, short sentences, contractions, no lists, no markdown, no emoji. Two or three "
            f"sentences at most. Never bring up illness or diagnoses. Never mention being an AI unless asked."
        )
        self.tools = self._make_tools()

    # -- the database, as plain methods (tests call these) and as tools (Claude calls these) -------
    def tool_list_people(self) -> str:
        with self.pool.connection() as conn:
            rows = people.list_people(conn)
        if not rows:
            return "Nobody is registered yet."
        return "\n".join(f"- {p.name}, {self._role(p)}: {p.small_context or 'no card yet'}" for p in rows)

    def _role(self, p) -> str:
        from enroll.store import is_user_relationship

        return "the user wearing the glasses" if is_user_relationship(p.relationship) else f"{self.user_name}'s {p.relationship}"

    def tool_person_context(self, name: str) -> str:
        needle = name.strip().lower()
        with self.pool.connection() as conn:
            rows = [p for p in people.list_people(conn) if needle and needle in p.name.lower()]
            facts = {p.id: [f.text for f in context.list_facts(conn, p.id)] for p in rows}
        if not rows:  # often a misheard name: who is here gives her something kind to say instead
            return f"No one called {name.strip()!r} is in the database. Here right now: {self.presence.who_answer()}"
        out = []
        for p in rows:
            here = "here right now" if self.presence.is_present(p.id) else "not seen right now"
            lines = [f"{p.name}, {self._role(p)} ({here})", f"Card: {p.small_context or '(none yet)'}"]
            lines += [f"- {f}" for f in facts[p.id]] or ["- no facts stored yet"]
            out.append("\n".join(lines))
        return "\n\n".join(out)

    def tool_who_is_here(self) -> str:
        return self.presence.who_answer()

    def _make_tools(self):
        brain = self

        @beta_tool
        def list_people() -> str:
            """Everyone registered in the database, with their relationship to the patient and their short card."""
            return brain.tool_list_people()

        @beta_tool
        def person_context(name: str) -> str:
            """Everything stored about one person: relationship, card, every fact (oldest first), and whether they are in the room now.

            Args:
                name: The person's name as spoken. A first name is enough; matching ignores case.
            """
            return brain.tool_person_context(name)

        @beta_tool
        def who_is_here() -> str:
            """Who the camera and the microphone recognise in the room right now."""
            return brain.tool_who_is_here()

        return [list_people, person_context, who_is_here]

    # -- the Assistant's hooks --------------------------------------------------------------------
    def answer(self, question: str, asker: str | None = None, transcript: str = "(nothing yet)") -> str:
        here = ", ".join(f"{p.name} ({p.relationship})" for p in self.presence.present()) or "nobody known"
        prompt = (
            f"Now: {time.strftime('%A %B %d, %Y, %I:%M %p').replace(' 0', ' ')}.\n"
            f"People recognised in the room right now: {here}.\n\n"
            f"Conversation so far:\n{transcript}\n\n"
            f"{asker or self.user_name} just said to you: \"{question}\"\n\n"
            f"Reply out loud. When the question is about a person, look them up first."
        )
        runner = self.client.beta.messages.tool_runner(
            model=self.model,
            max_tokens=800,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=[{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
            tools=self.tools,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "low"},
        )
        final = None
        for message in runner:
            final = message
            for block in message.content:
                if block.type == "tool_use":
                    log.info("%s looked up %s %s", self.code_name, block.name, block.input)
        if final is None:
            return ""
        if final.stop_reason == "refusal":
            return "Sorry, I can't help with that one."
        text = " ".join(b.text for b in final.content if b.type == "text").strip()
        if text and self.introduce and not self.introduced:
            self.introduced = True
            text = f"I'm {self.code_name}, the helper in your glasses. {text}"
        return text

    def new_visit(self) -> None:
        """A visit ended: her next answer says who she is again."""
        self.introduced = False

    def answer_stream(self, transcript: str, asker: str, question: str) -> Iterator[str]:
        """What voice_rec.assistant.Assistant calls; it speaks whatever this yields."""
        yield self.answer(question, asker, transcript) or "Sorry, I couldn't find that."


class PrintSpeaker:
    """Stands in for voice_rec.assistant.Speaker when there is no audio output: prints instead."""

    speaking = False

    def __init__(self, say=print):
        self._say = say
        self.windows: list = []
        self.recent_texts: list = []

    def preload(self, phrases) -> None:
        pass

    def stop(self) -> None:
        pass

    def heard_myself(self, t0: float, t1: float, text: str = "", margin: float = 0.6) -> bool:
        return False

    def say_stream(self, pieces, on_sentence=None) -> str:
        text = "".join(pieces).strip()
        if text and on_sentence:
            on_sentence(text)
        if text:
            self._say(text)
        return text

    def say(self, text: str, on_sentence=None) -> str:
        return self.say_stream([text], on_sentence)


def make_speaker(tts: bool, voice_dir: str | None = None, say=print):
    """The local Supertonic voice if its model is there, else macOS `say`, else printing."""
    if not tts:
        return PrintSpeaker(say)
    from voice_rec.assistant import SayVoice, Speaker, SupertonicVoice

    try:
        engine = SupertonicVoice(voice_dir)
    except (FileNotFoundError, RuntimeError, ImportError) as e:
        log.warning("no Supertonic voice (%s); using the system voice", e)
        try:
            engine = SayVoice()
        except Exception as e2:  # noqa: BLE001
            log.warning("no system voice either (%s); printing instead", e2)
            return PrintSpeaker(say)
    return Speaker(engine)
