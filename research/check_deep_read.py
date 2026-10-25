"""Finalize the deep read: apply the refuters' verdicts, check every supporting sentence word for
word, and check every DOI against Crossref (title, first author, year). No email is sent.

It needs the network, and it rewrites derived/deep_read_final.json. From the repository root:

    uv --directory research run python check_deep_read.py
"""
import difflib
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from check_quotes import check, norm  # noqa: E402

D = Path(__file__).parent / "derived"


def crossref(doi: str) -> dict:
    r = requests.get(f"https://api.crossref.org/works/{doi}", headers={"User-Agent": "nametags-study/0.1"}, timeout=60)
    if r.status_code != 200:
        return {"ok": False, "why": f"Crossref HTTP {r.status_code}"}
    m = r.json()["message"]
    year = None
    for key in ("published-print", "published-online", "issued", "created"):
        parts = (m.get(key) or {}).get("date-parts") or [[None]]
        if parts[0] and parts[0][0]:
            year = parts[0][0]
            break
    authors = [a.get("family", "") for a in m.get("author", [])]
    return {"ok": True, "title": (m.get("title") or [""])[0], "first_author": authors[0] if authors else "",
            "year": year, "venue": (m.get("container-title") or [""])[0]}


def main():
    final, tally = [], {}
    for b in range(4):
        papers = json.load(open(D / f"deep_read_{b}.json"))
        verdicts = {v["id"]: v for v in json.load(open(D / f"deep_read_{b}_verdicts.json"))}
        for p in papers:
            v = verdicts.get(p["id"], {"verdict": "missing"})
            entry = {**p, **(v.get("corrected_fields") or {})} if v["verdict"] == "corrected" else dict(p)
            entry["verdict"], entry["verdict_problems"] = v["verdict"], v.get("problems", [])
            if v["verdict"] in ("confirmed", "corrected"):
                q = check({"id": p["id"], "quote": entry.get("supporting_sentence"), "text_url": entry.get("text_url")}, "quote")
                entry["sentence_check"] = q["result"] + (f": {q['why']}" if q.get("why") else "")
                if entry.get("doi"):
                    c = crossref(entry["doi"])
                    if c["ok"]:
                        sim = difflib.SequenceMatcher(None, norm(c["title"]), norm(entry.get("title", ""))).ratio()
                        fa = norm(c["first_author"]) in norm(str(entry.get("authors", "")))
                        yr = c["year"] is not None and entry.get("year") is not None and abs(int(c["year"]) - int(entry["year"])) <= 1
                        entry["crossref"] = {"title_similarity": round(sim, 2), "first_author_match": fa, "year_within_1": yr,
                                             "crossref_title": c["title"], "crossref_year": c["year"], "crossref_venue": c["venue"]}
                    else:
                        entry["crossref"] = {"error": c["why"]}
            tally[entry["verdict"]] = tally.get(entry["verdict"], 0) + 1
            final.append(entry)
    (D / "deep_read_final.json").write_text(json.dumps(final, indent=2, ensure_ascii=False))
    print("verdicts:", tally)
    for e in final:
        cr = e.get("crossref", {})
        flag = "" if (e["verdict"] == "rejected" or (cr.get("title_similarity", 0) >= 0.85 and cr.get("first_author_match") and cr.get("year_within_1"))) else "  <-- crossref mismatch"
        print(f"{e['verdict']:<10} {str(e.get('sentence_check', '-'))[:28]:<28} {e.get('relevance', ''):<10} {e.get('year')} {e.get('title', '')[:60]}{flag}")


if __name__ == "__main__":
    main()
