"""Pull the abstract corpus from Europe PMC: one JSON Lines file per theme, plus a manifest.

No API key and no email are sent. Each theme's hit count is measured at pull time, and the pull
fails loudly unless it fetches exactly that many records. Deduplication across themes is Spark
job 0, which must land on the combined query's hit count recorded here.

It needs the network. It overwrites raw/manifest.json, the study's record of what it pulled on
Oct 25, 2026; a fresh pull finds newer papers, so its counts will differ. From the repository root:

    uv --directory research run python pull_corpus.py
"""
import html
import json
import re
import sys
import time
from pathlib import Path

import requests

API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
RAW = Path(__file__).parent / "raw"

D = 'TITLE_ABS:(dementia OR alzheimer*)'
F = 'HAS_ABSTRACT:y AND NOT SRC:PPR'
A1 = 'TITLE_ABS:("assistive technology" OR "assistive technologies" OR "assistive device" OR "assistive devices" OR "smart home" OR "smart homes" OR "ambient assisted living" OR gerontechnology OR telecare OR "memory aid" OR "memory aids" OR "reminder system" OR "reminder systems" OR "cognitive prosthesis" OR "cognitive prostheses" OR "social robot" OR "social robots" OR "companion robot" OR "companion robots" OR "assistive robot" OR "assistive robots" OR "smart glasses" OR "wearable camera" OR "wearable cameras")'
# A2 and A3 were rewritten after a veracity check. Europe PMC search ignores case, so
# "app" also matched APP (amyloid precursor protein), "tablets" matched pills, "sensors" matched
# biosensors and "digital" matched digital PCR, while A3's "memory" matched nearly every Alzheimer's
# abstract. With them, 3,456 of 7,926 "assistive" records (44%) were lab biology naming no assistive
# technology. The ambiguous words now appear only inside unambiguous phrases.
A2 = 'TITLE_ABS:(technology OR technologies OR "mobile app" OR "mobile apps" OR "smartphone app" OR "smartphone apps" OR "mobile application" OR "mobile applications" OR smartphone OR smartphones OR "tablet computer" OR "tablet computers" OR "tablet device" OR "tablet devices" OR ipad OR wearable OR wearables OR robot OR robots OR "virtual reality" OR telehealth OR telemedicine OR "digital health" OR "digital technology" OR "digital technologies" OR "digital intervention" OR "digital interventions" OR "voice assistant" OR "voice assistants" OR "conversational agent" OR "conversational agents" OR chatbot OR chatbots OR "large language model" OR "large language models" OR "smart speaker" OR "smart speakers")'
A3 = 'TITLE_ABS:("daily living" OR "everyday life" OR "independent living" OR independence OR caregiver OR caregivers OR carer OR carers OR "quality of life" OR "people living with dementia" OR "persons with dementia" OR "people with dementia" OR "person with dementia" OR "living with dementia" OR "family members" OR "informal care")'
B = 'TITLE_ABS:("face recognition" OR "facial recognition" OR "face processing" OR "face identification" OR "face memory" OR "face perception" OR "recognition of faces" OR "recognizing faces" OR "face-name" OR "familiar face" OR "familiar faces" OR "famous face" OR "famous faces" OR "person recognition" OR "person identification" OR "voice recognition" OR "speaker recognition" OR "voice identification" OR "familiar voice" OR "familiar voices" OR prosopagnosia OR phonagnosia OR misidentification OR misidentifications OR capgras)'
CS = 'TITLE_ABS:("care home" OR "care homes" OR "nursing home" OR "nursing homes" OR "long-term care" OR "long term care" OR "residential care" OR "residential aged care" OR "aged care")'
CW = 'TITLE_ABS:(staff OR nurses OR "care workers" OR "care worker" OR "care aides" OR "nursing assistants" OR "care assistants" OR "healthcare assistants" OR "personal support workers" OR "direct care workers" OR "healthcare professionals")'
CQ = 'TITLE_ABS:(qualitative OR "focus group" OR "focus groups" OR "semi-structured interviews" OR "interviews" OR "interview study" OR "thematic analysis")'
E = 'TITLE_ABS:(ethics OR ethical OR privacy OR surveillance OR "informed consent" OR autonomy OR dignity OR "data protection")'
T = 'TITLE_ABS:("artificial intelligence" OR "machine learning" OR "deep learning" OR monitoring OR sensor OR sensors OR camera OR cameras OR "video" OR tracking OR GPS OR "smart home" OR "smart homes" OR robot OR robots OR "assistive technology" OR "assistive technologies" OR telecare OR "facial recognition" OR technology OR technologies OR "smart glasses" OR "wearable camera" OR "wearable cameras" OR "voice assistant" OR "voice assistants" OR "conversational agent" OR "conversational agents" OR chatbot OR chatbots OR "large language model" OR "large language models")'
TL = 'TITLE_ABS:(lying OR lie OR lies OR deception OR deceptive OR "therapeutic lying" OR "truth-telling" OR "truth telling" OR "white lie" OR "white lies" OR "validation therapy")'

THEME_CORE = {
    "assistive": f"({A1} OR ({A2} AND {A3}))",
    "recognition": B,
    "carehome": f"({CS} AND {CW} AND {CQ})",
    "ethics": f"({E} AND {T})",
    "truth": TL,
}
THEMES = {name: f"{D} AND {core} AND {F}" for name, core in THEME_CORE.items()}
UNION = f"{D} AND (" + " OR ".join(THEME_CORE.values()) + f") AND {F}"
# Counts measured while planning (before the extra glasses / voice-assistant / truth terms).
PLANNING = {"assistive": None,  # was 7,889 with the contaminated A2/A3
             "recognition": 692, "carehome": 1254, "ethics": 1055, "truth": None}

TAG = re.compile(r"<[^>]+>")


def get(params, tries=4):
    for i in range(tries):
        try:
            r = requests.get(API, params=params, timeout=60)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            if i == tries - 1:
                raise
            wait = 2 ** i
            print(f"  retry in {wait}s after: {e}", file=sys.stderr)
            time.sleep(wait)


def hit_count(query):
    return get({"query": query, "format": "json", "resultType": "idlist", "pageSize": 1})["hitCount"]


def clean(text):
    return " ".join(html.unescape(TAG.sub(" ", text or "")).split())


def record(r, theme):
    journal = ((r.get("journalInfo") or {}).get("journal") or {}).get("title")
    mesh = [m.get("descriptorName") for m in (r.get("meshHeadingList") or {}).get("meshHeading", [])]
    return {
        "id": f'{r.get("source")}:{r.get("id")}',
        "pmid": r.get("pmid"),
        "pmcid": r.get("pmcid"),
        "doi": r.get("doi"),
        "title": clean(r.get("title")),
        "abstract": clean(r.get("abstractText")),
        "year": int(r["pubYear"]) if str(r.get("pubYear", "")).isdigit() else None,
        "journal": journal,
        "cited_by": r.get("citedByCount", 0),
        "keywords": (r.get("keywordList") or {}).get("keyword", []),
        "mesh": [m for m in mesh if m],
        "open_access": r.get("isOpenAccess") == "Y",
        "language": r.get("language"),
        "theme": theme,
    }


def pull(theme, query):
    expected = hit_count(query)
    out = RAW / f"{theme}.jsonl"
    cursor, n, started = "*", 0, time.time()
    with out.open("w") as f:
        while True:
            page = get({"query": query, "format": "json", "resultType": "core",
                        "pageSize": 1000, "cursorMark": cursor})
            results = page.get("resultList", {}).get("result", [])
            for r in results:
                f.write(json.dumps(record(r, theme), ensure_ascii=False) + "\n")
            n += len(results)
            nxt = page.get("nextCursorMark")
            print(f"  {theme}: {n}/{expected}", file=sys.stderr)
            if not results or not nxt or nxt == cursor:
                break
            cursor = nxt
            time.sleep(0.3)
    if n != expected:
        sys.exit(f"{theme}: pulled {n} records but the hit count was {expected}; stopping")
    return {"theme": theme, "hit_count": expected, "pulled": n, "planning_count": PLANNING[theme],
            "seconds": round(time.time() - started, 1), "file": out.name}


def per_year():
    years = {}
    for y in range(1990, 2027):
        years[y] = hit_count(f"{D} AND {F} AND PUB_YEAR:{y}")
        time.sleep(0.2)
    return years


def main():
    RAW.mkdir(exist_ok=True)
    manifest = {"pulled_at": time.strftime("%Y-%m-%d %H:%M %Z"), "api": API, "themes": [],
                "queries": THEMES, "union_query": UNION}
    for theme, query in THEMES.items():
        manifest["themes"].append(pull(theme, query))
    manifest["union_hit_count"] = hit_count(UNION)
    manifest["recognition_and_ethics_hit_count"] = hit_count(f"{D} AND {B} AND ({E} AND {T}) AND {F}")
    manifest["recognition_and_assistive_hit_count"] = hit_count(f"{D} AND {B} AND {THEME_CORE['assistive']} AND {F}")
    manifest["all_dementia_per_year"] = per_year()
    (RAW / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({k: v for k, v in manifest.items() if k not in ("queries", "union_query", "all_dementia_per_year")}, indent=2))


if __name__ == "__main__":
    main()
