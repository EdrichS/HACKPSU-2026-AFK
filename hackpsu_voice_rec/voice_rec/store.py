"""Persistent store of enrolled speakers (a JSON file of embeddings)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np


class ModelMismatch(RuntimeError):
    pass


class SpeakerStore:
    """Each speaker has clean-speech embeddings and, optionally, embeddings of their
    voice *after* it has been through the separation model (`sep_embeddings`).
    Separated streams carry artifacts, so they are matched against the latter."""

    def __init__(self, path: Path, model_name: str, dim: int, sep_model: str | None = None):
        self.path = Path(path)
        self.model_name = model_name
        self.dim = dim
        self.sep_model = sep_model
        self.sep_model_mismatch: str | None = None  # the file's sep model, if it differs from ours
        self._speakers: dict[str, dict] = {}
        self._load()

    # -- persistence -------------------------------------------------------
    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text())
        if raw.get("model") != self.model_name:
            raise ModelMismatch(
                f"{self.path} holds embeddings from model {raw.get('model')!r}, but the current "
                f"model is {self.model_name!r}. Either pass --model for the original, or run "
                f"`voicerec reset --yes` and re-enroll."
            )
        file_sep_model = raw.get("sep_model")
        keep_sep = True
        if self.sep_model is None:
            self.sep_model = file_sep_model
        elif file_sep_model is not None and file_sep_model != self.sep_model:
            self.sep_model_mismatch = file_sep_model
            keep_sep = False
        for name, rec in raw.get("speakers", {}).items():
            sep = rec.get("sep_embeddings") or []
            self._speakers[name] = {
                "embeddings": np.asarray(rec["embeddings"], dtype=np.float32).reshape(-1, self.dim),
                "sep_embeddings": np.asarray(sep if keep_sep else [], dtype=np.float32).reshape(-1, self.dim),
                "created": rec.get("created"),
                "updated": rec.get("updated"),
            }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = {
            "model": self.model_name,
            "dim": self.dim,
            "sep_model": self.sep_model,
            "speakers": {
                name: {
                    "embeddings": np.round(rec["embeddings"], 6).tolist(),
                    "sep_embeddings": np.round(rec["sep_embeddings"], 6).tolist(),
                    "created": rec["created"],
                    "updated": rec["updated"],
                }
                for name, rec in self._speakers.items()
            },
        }
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(raw))
        tmp.replace(self.path)

    # -- mutation ----------------------------------------------------------
    def add(
        self,
        name: str,
        embeddings: list[np.ndarray],
        replace: bool = False,
        sep_embeddings: list[np.ndarray] | None = None,
    ) -> None:
        embs = np.stack([np.asarray(e, dtype=np.float32) for e in embeddings])
        if embs.shape[1] != self.dim:
            raise ValueError(f"Embedding dim {embs.shape[1]} != store dim {self.dim}")
        seps = (
            np.stack([np.asarray(e, dtype=np.float32) for e in sep_embeddings])
            if sep_embeddings
            else np.zeros((0, self.dim), dtype=np.float32)
        )
        now = time.time()
        if name in self._speakers and not replace:
            rec = self._speakers[name]
            rec["embeddings"] = np.concatenate([rec["embeddings"], embs])
            rec["sep_embeddings"] = np.concatenate([rec["sep_embeddings"], seps])
            rec["updated"] = now
        else:
            self._speakers[name] = {"embeddings": embs, "sep_embeddings": seps, "created": now, "updated": now}
        self.save()

    def remove(self, name: str) -> bool:
        if name not in self._speakers:
            return False
        del self._speakers[name]
        self.save()
        return True

    def clear(self) -> None:
        self._speakers = {}
        if self.path.exists():
            self.path.unlink()

    # -- queries -----------------------------------------------------------
    def names(self) -> list[str]:
        return sorted(self._speakers)

    def __len__(self) -> int:
        return len(self._speakers)

    def __contains__(self, name: str) -> bool:
        return name in self._speakers

    def samples(self, name: str) -> np.ndarray:
        return self._speakers[name]["embeddings"]

    def info(self, name: str) -> dict:
        rec = self._speakers[name]
        return {
            "name": name,
            "samples": len(rec["embeddings"]),
            "sep_samples": len(rec["sep_embeddings"]),
            "created": rec["created"],
            "updated": rec["updated"],
        }

    def centroid(self, name: str, domain: str = "clean") -> np.ndarray:
        """Mean embedding. domain="sep" uses the post-separation voiceprint when the
        speaker has one, otherwise falls back to the clean one."""
        rec = self._speakers[name]
        embs = rec["sep_embeddings"] if domain == "sep" and len(rec["sep_embeddings"]) else rec["embeddings"]
        c = embs.mean(axis=0)
        n = np.linalg.norm(c)
        return c / n if n > 0 else c

    def centroids(self, domain: str = "clean") -> tuple[list[str], np.ndarray]:
        """All speakers' L2-normalised mean embeddings as (names, matrix[k, dim])."""
        names = self.names()
        if not names:
            return [], np.zeros((0, self.dim), dtype=np.float32)
        return names, np.stack([self.centroid(n, domain) for n in names])

    def has_sep_profiles(self) -> bool:
        return bool(self._speakers) and all(len(r["sep_embeddings"]) for r in self._speakers.values())

    def _domain_samples(self, name: str, domain: str) -> np.ndarray:
        rec = self._speakers[name]
        return rec["sep_embeddings"] if domain == "sep" and len(rec["sep_embeddings"]) else rec["embeddings"]

    def means(self, domain: str = "clean") -> np.ndarray:
        """Un-normalised mean embedding per speaker, in names() order."""
        names = self.names()
        if not names:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.stack([self._domain_samples(n, domain).mean(axis=0) for n in names])

    def grand_mean(self, domain: str = "clean") -> np.ndarray | None:
        """Mean of every stored sample in this domain: the component shared by all
        voices (and, for "sep", by the separator's artifacts). None with fewer than
        three speakers, where centering would just pit two people against each other."""
        if len(self._speakers) < 3:
            return None
        allx = np.concatenate([self._domain_samples(n, domain) for n in self.names()])
        return allx.mean(axis=0)
