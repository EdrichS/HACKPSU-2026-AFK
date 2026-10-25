"""Who is in the room. Sightings by face and by voice merge on the person's id."""

import threading
import time
from dataclasses import dataclass

from contract.live import UNKNOWN_TEXT, PresentPerson, who_text


@dataclass
class Sighting:
    person: PresentPerson
    first: float
    last: float
    hits: int = 0
    confirmed: bool = False
    announced: float = 0.0
    away: bool = False  # left since the last announcement
    via: str = ""


class Presence:
    """A voice match counts at once; a face needs `confirm_hits` sightings within `confirm_window`
    seconds, so one odd frame never names anyone. Someone unseen for `gone_after` seconds has left.
    Each person is announced once on arrival, and again only if they left and come back at least
    `reannounce` seconds after the last announcement (the app must never repeat itself at someone).
    An unmatched face that stays in view for `unknown_after` seconds gets the unknown sentence,
    at most once per `unknown_cooldown`; voices never trigger it.
    """

    def __init__(
        self,
        confirm_hits: int = 2,
        confirm_window: float = 3.0,
        gone_after: float = 20.0,
        reannounce: float = 300.0,
        unknown_after: float = 4.0,
        unknown_cooldown: float = 60.0,
        clock=time.monotonic,
        user_id: int | None = None,
    ):
        self.user_id = user_id  # the wearer: always here, never announced, never in who_answer
        self.confirm_hits = confirm_hits
        self.confirm_window = confirm_window
        self.gone_after = gone_after
        self.reannounce = reannounce
        self.unknown_after = unknown_after
        self.unknown_cooldown = unknown_cooldown
        self._clock = clock
        self._people: dict[int, Sighting] = {}
        self._unknown_since: float | None = None
        self._unknown_said: float | None = None
        self._lock = threading.Lock()

    def saw(self, person: PresentPerson, via: str) -> str | None:
        """Record a sighting. Returns the sentence to speak when this sighting is an arrival."""
        if person.person_id == self.user_id:
            return None
        now = self._clock()
        with self._lock:
            s = self._people.get(person.person_id)
            if s is None:
                s = self._people[person.person_id] = Sighting(person, now, now)
            elif now - s.last > self.gone_after:
                s.hits, s.confirmed, s.away = 0, False, True
            s.person = person  # the card may have changed since
            s.hits = s.hits + 1 if now - s.last <= self.confirm_window else 1
            s.last, s.via = now, via
            if via == "voice" or s.hits >= self.confirm_hits:
                s.confirmed = True
            if not s.confirmed:
                return None
            if s.announced == 0.0 or (s.away and now - s.announced >= self.reannounce):
                s.announced, s.away = now, False
                return who_text([person])
            return None

    def present(self) -> list[PresentPerson]:
        """Everyone confirmed and seen recently, in order of arrival."""
        now = self._clock()
        with self._lock:
            here = [s for s in self._people.values() if s.confirmed and now - s.last <= self.gone_after]
            return [s.person for s in sorted(here, key=lambda s: s.first)]

    def is_present(self, person_id: int) -> bool:
        return any(p.person_id == person_id for p in self.present())

    def who_answer(self) -> str:
        return who_text(self.present())

    @property
    def unknown_confirmed(self) -> bool:
        """An unmatched face has been in view long enough to count as unknown (not just unsure)."""
        with self._lock:
            return self._unknown_since is not None and self._clock() - self._unknown_since >= self.unknown_after

    def unknown_face(self, in_view: bool) -> str | None:
        """Call on every processed frame with whether an unmatched face is in view."""
        now = self._clock()
        with self._lock:
            if not in_view:
                self._unknown_since = None
                return None
            if self._unknown_since is None:
                self._unknown_since = now
                return None
            if now - self._unknown_since < self.unknown_after:
                return None
            if self._unknown_said is not None and now - self._unknown_said < self.unknown_cooldown:
                return None
            self._unknown_said = now
            return UNKNOWN_TEXT
