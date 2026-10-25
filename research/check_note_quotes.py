"""Check that every quotation in the research pages comes from the verified pool.

The pool is every quote or sentence that was matched word for word in its source by script: the
"pass" entries in derived/quote_check.json (accounts, figures, extra quotes) and the deep read's
supporting sentences whose check passed (derived/deep_read_final.json). Nothing else joins it.

What counts as a quotation:
- text in double quotes, straight or curly, of 12 characters or more;
- a blockquote, minus its attribution line ("— Author 2020"). A GitHub alert (> [!NOTE]) or a
  blockquote that opens with a bold label (> **Key point:** ...) is our own text, not a quotation.

A quotation passes if each piece of it (split at ellipses) appears in the pool. Code blocks and
inline code are skipped. Strings that are not quotes of a source (Nametags' own wording, headings,
titles) are listed in ALLOW, so they are skipped on purpose and never by accident.

With no arguments it checks every page in docs/research/ and the repository's README.md. From the
repository root:

    uv --directory research run python check_note_quotes.py
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from check_quotes import norm  # noqa: E402

D = Path(__file__).parent / "derived"
REPO = Path(__file__).resolve().parent.parent
PAGES = REPO / "docs" / "research"
README = REPO / "README.md"
# Nametags' own wording (announcements, Nova's rules, the consent screen), headings and titles.
ALLOW = ("I'm Nova", "Here's", "That's", "David, your", "Maria, your", "When the face fails", "Never guess",
         "The visit and", "The user", "Who is this", "Never mention", "Never bring up", "Never put death",
         "Never say a wrong name", "the only source of truth", "I don't recognize this person", "I agree to have my face",
         "Only used for", "Nova, who is", "Hey Nova", "Do people with dementia", "Recognition of familiar people with a mobile",
         "a non-drug support", "Nametags is a non-drug support", "Your grandson is here", "Yes, that's David", "It's David",
         "Found while planning", "recall coach", "reality orientation", "To Have One Extra Eye", "Nova, who's")
ALERT = re.compile(r"\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]", re.I)
# Every quoted string, short ones too, so quote marks pair up left to right; short ones are dropped later.
QUOTED = re.compile(r'"([^"\n]+)"|“([^”\n]+)”')


def pool() -> str:
    passed = {(c["file"], c["id"]) for c in json.load(open(D / "quote_check.json")) if c["result"] == "pass"}
    texts = []
    for f, field in [("accounts_peer.json", "quote"), ("accounts_org.json", "quote"), ("accounts_extra.json", "quote"),
                     ("extra_quotes.json", "quote"), ("figures.json", "sentence")]:
        texts += [x[field] for x in json.load(open(D / f)) if (f, x["id"]) in passed]
    texts += [e["supporting_sentence"] for e in json.load(open(D / "deep_read_final.json"))
              if str(e.get("sentence_check", "")).startswith("pass")]
    return norm(" || ".join(texts)).replace('"', "'")


def without_code(text: str) -> str:
    text = re.sub(r"^```.*?^```[^\n]*$", "", text, flags=re.M | re.S)
    return re.sub(r"`[^`\n]*`", "", text)


def blockquotes(text: str) -> list[str]:
    """The text of each blockquote that is a quotation, its lines joined."""
    out, block = [], []
    for line in text.splitlines() + [""]:
        m = re.match(r"\s*>\s?(.*)$", line)
        if m:
            block.append(m.group(1).strip())
            continue
        if block:
            first = next((b for b in block if b), "")
            if not (ALERT.match(first) or first.startswith("**")):
                body = " ".join(b for b in block if b and not b.startswith(("—", "–", "--")))
                if not body.startswith(('"', "“")):  # a quote in quote marks is checked as a quoted string
                    out.append(body)
            block = []
    return out


def quoted_strings(text: str) -> list[str]:
    flat = re.sub(r"\n\s+(?=[^-\s*#|>])", " ", text)       # list items wrapped over several lines
    flat = re.sub(r"\n>[ \t]?(?=[^\s>—–-])", " ", flat)     # blockquotes wrapped over several lines
    return [q for a, b in QUOTED.findall(flat) if len(q := a or b) >= 12]


def label(path: Path) -> str:
    """A page's path from the repository root, so the two README.md files can be told apart."""
    try:
        return str(path.resolve().relative_to(REPO))
    except ValueError:
        return path.name


def main(paths: list[Path]) -> None:
    blob, bad = pool(), 0
    for path in paths:
        text = without_code(path.read_text())
        found = [("quoted", q) for q in quoted_strings(text)] + [("blockquote", b) for b in blockquotes(text)]
        seen = set()
        for kind, q in found:
            if q.startswith(ALLOW) or "{" in q:
                continue
            for piece in re.split(r"…|\.\.\.", q):
                p = norm(piece).replace('"', "'").strip(" .,;:'")
                if len(p) >= 12 and p not in blob and p not in seen:
                    seen.add(p)
                    bad += 1
                    print(f"NOT VERIFIED ({kind}) in {label(path)}: {piece.strip()[:110]!r}")
        n_q = sum(1 for k, _ in found if k == "quoted")
        print(f"{label(path)}: {n_q} quoted strings and {len(found) - n_q} blockquotes checked")
    print(f"{len(paths)} pages, {bad} quotations not in the verified pool")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main([Path(p) for p in sys.argv[1:]] or [*sorted(PAGES.glob("*.md")), README])
