"""Match an utterance against enrolled speakers by cosine similarity."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .config import DEFAULT_THRESHOLD, SAMPLE_RATE
from .embedder import SpeakerEmbedder
from .store import SpeakerStore


@dataclass
class Match:
    speaker: str | None  # None when nobody clears the threshold
    score: float  # best cosine similarity
    ranked: list[tuple[str, float]] = field(default_factory=list)  # all speakers, best first
    centered_margin: float | None = None  # lead of the winner in the centered space, when used
    text: str | None = None  # transcript, when transcription is on

    @property
    def is_known(self) -> bool:
        return self.speaker is not None

    @property
    def best_guess(self) -> str | None:
        return self.ranked[0][0] if self.ranked else None

    @property
    def runner_up(self) -> tuple[str, float] | None:
        return self.ranked[1] if len(self.ranked) > 1 else None

    @property
    def margin(self) -> float:
        """Gap between the best and second-best speaker (how unambiguous the call is)."""
        if self.centered_margin is not None:
            return self.centered_margin
        if len(self.ranked) < 2:
            return self.score
        return self.ranked[0][1] - self.ranked[1][1]

    def to_dict(self) -> dict:
        d = {
            "speaker": self.speaker,
            "known": self.is_known,
            "score": round(self.score, 4),
            "margin": round(self.margin, 4),
            "ranked": [(n, round(s, 4)) for n, s in self.ranked],
        }
        if self.text is not None:
            d["text"] = self.text
        return d


class Recognizer:
    """Accepts the best-scoring speaker when the score clears `threshold`, or when it
    is within `rescue_floor` of it and leads the runner-up by `rescue_margin`: with a
    small enrolled set, a clear winner a little under the bar is almost always right.

    With three or more enrolled speakers the *ranking* is done in a centered space
    (the mean of all stored embeddings subtracted from profiles and probe alike).
    That removes what every voice has in common, which is a lot after speech
    separation, and pulls look-alike speakers apart. The raw cosine of the winner is
    still what is compared against the threshold, so thresholds keep their meaning."""

    def __init__(
        self,
        embedder: SpeakerEmbedder,
        store: SpeakerStore,
        threshold: float = DEFAULT_THRESHOLD,
        rescue_margin: float = 0.20,
        rescue_floor: float = 0.10,
    ):
        self.embedder = embedder
        self.store = store
        self.threshold = threshold
        self.rescue_margin = rescue_margin
        self.rescue_floor = rescue_floor

    def identify_embedding(self, emb: np.ndarray, threshold: float | None = None, domain: str = "clean") -> Match:
        thr = self.threshold if threshold is None else threshold
        names, centroids = self.store.centroids(domain)
        if not names:
            return Match(None, 0.0, [])
        scores = centroids @ emb
        mu = self.store.grand_mean(domain)
        centered_margin = None
        if mu is not None:
            means = self.store.means(domain) - mu
            means /= np.linalg.norm(means, axis=1, keepdims=True) + 1e-9
            probe = emb - mu
            probe /= np.linalg.norm(probe) + 1e-9
            disc = means @ probe
            order = np.argsort(-disc)
            centered_margin = float(disc[order[0]] - disc[order[1]]) if len(order) > 1 else float(disc[order[0]])
        else:
            order = np.argsort(-scores)
        ranked = [(names[i], float(scores[i])) for i in order]
        best_name, best = ranked[0]
        margin = centered_margin if centered_margin is not None else (best - ranked[1][1] if len(ranked) > 1 else best)
        accepted = best >= thr or (best >= thr - self.rescue_floor and margin >= self.rescue_margin)
        return Match(best_name if accepted else None, best, ranked, centered_margin)

    def identify(
        self, samples: np.ndarray, sample_rate: int = SAMPLE_RATE, threshold: float | None = None, domain: str = "clean"
    ) -> Match:
        return self.identify_embedding(self.embedder.embed(samples, sample_rate), threshold, domain)


# --------------------------------------------------------------------------- simultaneous talkers
@dataclass
class Talker:
    speaker: str | None  # None = a voice that is present but not enrolled
    score: float
    share: float  # fraction of the mixture's energy carried by this talker's stream
    ranked: list[tuple[str, float]] = field(default_factory=list)
    audio: np.ndarray | None = field(default=None, repr=False, compare=False)  # this talker's separated stream
    text: str | None = None  # filled in when transcription is on

    @property
    def is_known(self) -> bool:
        return self.speaker is not None

    def to_dict(self) -> dict:
        d = {
            "speaker": self.speaker,
            "known": self.is_known,
            "score": round(self.score, 4),
            "share": round(self.share, 3),
            "ranked": [(n, round(s, 4)) for n, s in self.ranked[:3]],
        }
        if self.text is not None:
            d["text"] = self.text
        return d


@dataclass
class MultiMatch:
    talkers: list[Talker]  # loudest first
    mixture: Match  # what the plain single-speaker path says about the whole mix
    details: list[dict] = field(default_factory=list)  # per separated stream, for --debug

    @property
    def names(self) -> list[str]:
        return [t.speaker or "Unknown" for t in self.talkers]

    @property
    def n_talkers(self) -> int:
        return len(self.talkers)

    def to_dict(self) -> dict:
        return {
            "n_talkers": self.n_talkers,
            "talkers": [t.to_dict() for t in self.talkers],
            "mixture": self.mixture.to_dict(),
        }


class MultiRecognizer:
    """Separate a mixture into streams, identify each, and decide who is really talking.

    Rules (tuned on synthetic and recorded two-voice mixtures, see scripts/eval_mixtures.py):
    * separated streams carry artifacts, so they are scored against each speaker's
      post-separation voiceprint (store domain "sep") with `stream_threshold`;
    * a stream carrying less than `min_share` of the energy is a dead output, dropped;
    * two streams naming the same person collapse into one (the separator split one voice);
    * an unmatched stream whose closest speaker was already found in another stream is
      residue of that speaker, not a new talker;
    * an unmatched stream whose top candidate clearly leads the runner-up is accepted
      as that candidate (closed sets are the normal case);
    * an unmatched stream counts as an Unknown talker only if it is loud enough
      (`unknown_min_share`);
    * if the whole mixture confidently identifies someone who no stream matched, the
      Unknown stream that ranked them first is them;
    * never more talkers than the separator has outputs (the loudest win);
    * if separation finds one voice but the whole mix ranks a second enrolled speaker
      at `pair_hint` or above, the separator missed a talker: report both;
    * the streams' story must agree with the whole mix: if no claimed talker scores at
      least the threshold on the un-separated audio, the claims are artifacts (typically
      a stranger split in two) and the whole-mix answer is reported instead;
    * when only one talker is left, the plain whole-mix result is reported: for a
      single voice it is strictly better evidence than a separated stream.
    Long inputs are processed in `chunk_seconds` pieces and the names merged.
    """

    def __init__(
        self,
        recognizer: Recognizer,
        separator,
        stream_threshold: float | None = None,
        min_share: float = 0.10,
        unknown_min_share: float = 0.30,
        chunk_seconds: float = 6.0,
        min_seconds: float = 1.5,
        rescue_margin: float = 0.15,
        rescue_floor: float = 0.10,
        pair_hint: float = 0.45,
    ):
        # If separation finds one voice but the whole mix ranks a second enrolled
        # speaker this high (clean-speech runner-ups for one voice stay under ~0.35),
        # the separator missed a talker and the runner-up is reported too.
        self.pair_hint = pair_hint
        self.rec = recognizer
        self.sep = separator
        # A stream just under the bar is still accepted when its top candidate leads the
        # runner-up by `rescue_margin` and scores at least stream_threshold - rescue_floor.
        self.rescue_margin = rescue_margin
        self.rescue_floor = rescue_floor
        # Separation-domain voiceprints share the separator's artifacts, which lifts
        # impostor scores as well, so the bar for a separated stream sits *above* the
        # clean-speech threshold (measured: genuine p10 0.80, impostor max 0.59).
        if stream_threshold is not None:
            self.stream_threshold = stream_threshold
        elif recognizer.store.has_sep_profiles():
            self.stream_threshold = min(0.95, recognizer.threshold + 0.07)
        else:  # clean voiceprints only: separated streams score lower against them
            self.stream_threshold = max(0.30, recognizer.threshold - 0.07)
        self.min_share = min_share
        self.unknown_min_share = unknown_min_share
        self.chunk_seconds = chunk_seconds
        self.min_seconds = min_seconds  # shorter utterances skip separation (too little context)

    @staticmethod
    def _cat(a: np.ndarray | None, b: np.ndarray | None) -> np.ndarray | None:
        if a is None:
            return b
        if b is None:
            return a
        return np.concatenate([a, b])

    @classmethod
    def _merge(cls, into: dict, key, cand: Talker) -> None:
        prev = into.get(key)
        if prev is None:
            into[key] = cand
        else:
            best = prev if prev.score >= cand.score else cand
            # same person in two streams of one chunk: keep the louder stream's audio
            audio = prev.audio if (prev.share >= cand.share and prev.audio is not None) else cand.audio
            into[key] = Talker(key, best.score, prev.share + cand.share, best.ranked, audio)

    def _identify_chunk(self, x: np.ndarray) -> list[Talker]:
        streams = self.sep.separate(x)
        energies = np.array([float(np.mean(np.square(s))) for s in streams])
        total = energies.sum()
        shares = energies / total if total > 0 else np.zeros_like(energies)
        matches: list[tuple[Match, float, np.ndarray]] = []
        for stream, share in zip(streams, shares):
            if share < self.min_share:
                self._details.append({"share": float(share), "ranked": [], "note": "dead"})
                continue
            try:
                m = self.rec.identify(stream, threshold=self.stream_threshold, domain="sep")
            except ValueError:
                continue
            if m.ranked:
                matches.append((m, float(share), stream))
                self._details.append({"share": float(share), "ranked": m.ranked[:3], "note": m.speaker or "under bar"})
        found = {m.speaker for m, _, _ in matches if m.is_known}

        def residue_of(m: Match) -> str | None:
            # closest speaker already found, or a near tie between the top two with one found
            if m.best_guess in found:
                return m.best_guess
            if len(m.ranked) > 1 and m.ranked[1][0] in found and m.margin < 0.05:
                return m.ranked[1][0]
            return None

        talkers: dict[str | None, Talker] = {}
        for m, share, stream in matches:
            owner = None if m.is_known else residue_of(m)
            if m.is_known:
                self._merge(talkers, m.speaker, Talker(m.speaker, m.score, share, m.ranked, stream))
            elif owner is not None:  # residue of someone we already have
                self._merge(talkers, owner, Talker(owner, 0.0, share, m.ranked, None))
            elif (
                m.score >= self.stream_threshold - self.rescue_floor
                and m.margin >= self.rescue_margin
                and share >= self.min_share * 2
            ):
                self._merge(talkers, m.best_guess, Talker(m.best_guess, m.score, share, m.ranked, stream))
                found.add(m.best_guess)
            elif share >= self.unknown_min_share:
                self._merge(talkers, None, Talker(None, m.score, share, m.ranked, stream))
        return sorted(talkers.values(), key=lambda t: -t.share)

    def identify(self, samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> MultiMatch:
        x = np.asarray(samples, dtype=np.float32)
        mixture = self.rec.identify(x, sample_rate)
        self._details: list[dict] = []
        if len(x) < self.min_seconds * SAMPLE_RATE:
            only = [Talker(mixture.speaker, mixture.score, 1.0, mixture.ranked, x)] if mixture.ranked else []
            return MultiMatch(only, mixture)
        # equal-length pieces of at most chunk_seconds (a short leftover tail separates badly)
        n_chunks = max(1, int(np.ceil(len(x) / (self.chunk_seconds * SAMPLE_RATE))))
        pieces = np.array_split(x, n_chunks)
        merged: dict[str | None, Talker] = {}
        seen: dict[str | None, int] = {}
        share_sum: dict[str | None, float] = {}
        audio: dict[str | None, np.ndarray | None] = {}
        for piece in pieces:
            for t in self._identify_chunk(piece):
                seen[t.speaker] = seen.get(t.speaker, 0) + 1
                share_sum[t.speaker] = share_sum.get(t.speaker, 0.0) + t.share
                audio[t.speaker] = self._cat(audio.get(t.speaker), t.audio)
                prev = merged.get(t.speaker)
                if prev is None or t.score > prev.score:
                    merged[t.speaker] = t
        if None in merged:
            unknown = merged[None]
            named = {k for k in merged if k is not None}
            top = [n for n, _ in unknown.ranked[:2]]
            near_tie = len(unknown.ranked) > 1 and unknown.ranked[0][1] - unknown.ranked[1][1] < 0.05
            if seen[None] * 2 < n_chunks or (top and top[0] in named) or (near_tie and top[1] in named):
                # an Unknown in a minority of chunks, or one whose closest match is already
                # named from another chunk, is residue rather than a third voice
                del merged[None]
        talkers = [Talker(k, t.score, share_sum[k] / n_chunks, t.ranked, audio.get(k)) for k, t in merged.items()]
        talkers.sort(key=lambda t: -t.share)
        max_talkers = getattr(self.sep, "num_sources", None) or 2
        if len(talkers) > max_talkers:  # the separator cannot hear more voices than it has outputs
            talkers = talkers[:max_talkers]
        if talkers and mixture.ranked:
            raw = dict(mixture.ranked)
            claimed = [t.speaker for t in talkers if t.speaker is not None]
            if claimed and max(raw.get(n, 0.0) for n in claimed) < self.rec.threshold:
                talkers = []  # nobody the streams named is audible in the whole mix: drop the claims
        if mixture.is_known and mixture.speaker not in {t.speaker for t in talkers}:
            for i, t in enumerate(talkers):
                if t.speaker is None and t.ranked and t.ranked[0][0] == mixture.speaker:
                    talkers[i] = Talker(mixture.speaker, max(t.score, mixture.score), t.share, t.ranked)
                    break
            else:
                if not talkers:
                    talkers = [Talker(mixture.speaker, mixture.score, 1.0, mixture.ranked)]
        if len(talkers) <= 1 and mixture.ranked:
            # one voice (or nothing usable): the un-separated audio is the better evidence
            talkers = [Talker(mixture.speaker, mixture.score, 1.0, mixture.ranked, x)]
            if mixture.is_known and len(mixture.ranked) > 1:
                second, score = max(mixture.ranked[1:], key=lambda r: r[1])
                if score >= self.pair_hint:
                    talkers.append(Talker(second, score, 0.0, mixture.ranked, x))
        return MultiMatch(talkers, mixture, self._details)


def separated_embeddings(embedder, separator, utterances: list[np.ndarray], chunk_seconds: float = 6.0) -> list[np.ndarray]:
    """Embeddings of a speaker's voice after a round trip through the separator.

    Used at enrollment so separated streams are compared against a voiceprint that
    carries the same artifacts. Takes the dominant output stream of each piece.
    """
    out: list[np.ndarray] = []
    n = int(chunk_seconds * SAMPLE_RATE)
    for u in utterances:
        u = np.asarray(u, dtype=np.float32)
        pieces = [u[i : i + n] for i in range(0, len(u), n)]
        if len(pieces) > 1 and len(pieces[-1]) < SAMPLE_RATE:
            pieces[-2] = np.concatenate([pieces[-2], pieces[-1]])
            pieces.pop()
        for piece in pieces:
            if len(piece) < SAMPLE_RATE:
                continue
            streams = separator.separate(piece)
            dominant = max(streams, key=lambda s: float(np.mean(np.square(s))))
            win = 3 * SAMPLE_RATE  # the whole stream plus 3 s windows of it: more, varied support
            views = [dominant] + [dominant[i : i + win] for i in range(0, len(dominant) - win + 1, win)]
            for v in views:
                try:
                    out.append(embedder.embed(v))
                except ValueError:
                    continue
    return out
