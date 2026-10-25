"""Check every recorded sentence and quote word for word against its fetched source text.

Reads derived/figures.json and derived/accounts_*.json, fetches each item's text_url (or url),
and writes derived/quote_check.json. A quote passes only if, after normalizing whitespace, case,
curly quotes, dashes and PDF hyphenation, every piece of it (split at ellipses) appears in the
source text, in order. Nothing is fixed silently: a failure is reported, never rewritten.

It needs the network, and it rewrites derived/quote_check.json. From the repository root:

    uv --directory research run python check_quotes.py
"""
import html
import io
import json
import re
import sys
import unicodedata
from pathlib import Path

import requests
from pypdf import PdfReader

DERIVED = Path(__file__).parent / "derived"
_cache: dict[str, str] = {}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[‐-―−]", "-", s)
    s = s.replace("…", "...")
    s = re.sub(r"(\w)-\s+(\w)", r"\1\2", s)  # PDF line-break hyphenation: "recog- nised"
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\(\s+", "(", s)  # tag stripping leaves "( multimedia appendix 2 )"
    s = re.sub(r"\s+([),.;:])", r"\1", s)
    return s.strip().lower()


def pdf_text(content: bytes) -> str:
    """PDF text without running headers and footers: a line (digits ignored) that recurs on 3 or
    more pages is page furniture, and so is a line that is only a page number. A sentence that
    crosses a page break then reads straight through."""
    pages = [(page.extract_text() or "").splitlines() for page in PdfReader(io.BytesIO(content)).pages]
    key = lambda line: re.sub(r"\d+", "", line).strip().lower()
    seen: dict[str, int] = {}
    for lines in pages:
        for k in {key(l) for l in lines if key(l)}:
            seen[k] = seen.get(k, 0) + 1
    keep = [l for lines in pages for l in lines if key(l) and seen[key(l)] < 3]
    return "\n".join(keep)


# Says plainly what is asking. A site that refuses it stays "unreachable"; nothing here poses as a browser.
USER_AGENT = "nametags-research-quote-check/0.1"


class Page:
    """The few fields text_of needs, whichever client fetched the page."""
    def __init__(self, content: bytes, content_type: str):
        self.content, self.headers = content, {"content-type": content_type}
        self.text = content.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.text)


def _captcha(content: bytes) -> bool:
    return len(content) < 60000 and b"recaptcha" in content.lower()


def fetch(url: str) -> Page:
    """One plain, identified GET. A site that refuses scripts (403) or answers with a CAPTCHA is
    reported as unreachable: the checker never tries to get around a block. Those quotes stay
    unverified by script and are labelled so."""
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=90)
    if r.status_code != 200 or _captcha(r.content):
        raise requests.HTTPError(f"unreachable (HTTP {r.status_code}{', CAPTCHA page' if _captcha(r.content) else ''}): {url}")
    return Page(r.content, r.headers.get("content-type", ""))


def text_of(url: str) -> str:
    if url in _cache:
        return _cache[url]
    r = fetch(url)
    kind = r.headers.get("content-type", "")
    if "pdf" in kind or url.lower().endswith(".pdf"):
        raw = pdf_text(r.content)
    elif "json" in kind:
        values: list[str] = []

        def walk(x):
            if isinstance(x, dict):
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
            elif isinstance(x, str):
                values.append(x)

        walk(r.json())
        raw = html.unescape(re.sub(r"<[^>]+>", " ", " ".join(values)))
    else:
        raw = html.unescape(re.sub(r"<[^>]+>", " ", r.text))
    _cache[url] = norm(raw)
    return _cache[url]


def pieces(quote: str) -> list[str]:
    parts = re.split(r"\.\.\.|…|\[\.\.\.\]", quote)
    return [norm(p).strip(" .,;:'\"") for p in parts if len(norm(p).strip(" .,;:'\"")) >= 8]


def check(item: dict, field: str) -> dict:
    quote = item.get(field) or ""
    url = item.get("text_url") or item.get("url")
    out = {"id": item.get("id"), "field": field, "url": url, "quote": quote}
    if not quote or not url:
        return out | {"result": "fail", "why": "no quote or no url"}
    try:
        text = text_of(url)
    except Exception as e:  # report, never guess
        return out | {"result": "unreachable", "why": f"{type(e).__name__}: {e}"[:200]}
    at = 0
    for p in pieces(quote):
        i = text.find(p, at)
        if i < 0:
            return out | {"result": "fail", "why": f"piece not found: {p[:80]!r}"}
        at = i + len(p)
    return out | {"result": "pass"}


def main() -> None:
    jobs = []
    for f, field in [("figures.json", "sentence"), ("accounts_peer.json", "quote"), ("accounts_org.json", "quote"), ("accounts_extra.json", "quote"), ("extra_quotes.json", "quote")]:
        path = DERIVED / f
        if not path.exists():
            print(f"missing {f}", file=sys.stderr)
            continue
        for item in json.loads(path.read_text()):
            if item.get("status") in ("dropped",):
                continue
            jobs.append((f, check(item, field)))
    results = [{"file": f} | r for f, r in jobs]
    (DERIVED / "quote_check.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
    tally: dict[str, int] = {}
    for r in results:
        tally[r["result"]] = tally.get(r["result"], 0) + 1
        if r["result"] != "pass":
            print(f'{r["result"].upper():11} {r["file"]:20} {r["id"]}: {r.get("why", "")}')
    print("tally:", tally)


if __name__ == "__main__":
    main()
