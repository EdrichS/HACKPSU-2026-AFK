"""Run every Spark job on the real corpus and the CMS file; write derived/ outputs and check them.

From the repository root:

    uv --directory research run python jobs/run_corpus.py

It reads raw/*.jsonl and raw/manifest.json, and downloads the CMS file into raw/ only if it is
missing. The deduplicated corpus, with its full abstracts, goes to raw/abstracts.jsonl, which git
ignores: the abstracts belong to their publishers. derived/ gets only small aggregates.
"""
import csv
import json
import time
from pathlib import Path

import requests
from pyspark.ml.feature import StopWordsRemover

import corpus_jobs as J
from session import spark

ROOT = Path(__file__).resolve().parents[1]
RAW, OUT = ROOT / "raw", ROOT / "derived"
CMS_URL = "https://data.cms.gov/sites/default/files/2026-10/3fc2159f-c755-4ffc-81d6-fd40bb3e421f/MDS_Frequency_Q3_2026.csv"
CMS_FILE = RAW / "MDS_Frequency_Q3_2026.csv"

# Nametags concepts, answered by boolean retrieval over the inverted index (Lecture 4). A plain
# list is an OR over index terms. A list of alternatives holds groups that are ANDed. Words with a
# second meaning only count next to their context: "lying" (in bed), "masks" (a verb), "visits"
# (clinic visits), "turnover" (protein turnover), "surveillance" (disease surveillance).
# Verb forms only: "recognition" also means object-recognition tests in mouse studies.
RECOG = ["recognize", "recognise", "recognizing", "recognising", "recognized", "recognised", "recognizes", "recognises"]
# People only: "family" alone also means protein families ("Src family kinases").
FAMILY = ["family members", "family member", "relatives", "relative", "spouse", "spouses", "husband", "wife", "son", "daughter",
          "grandchildren", "loved ones", "visitors"]
TECH = ["camera", "cameras", "video", "sensor", "sensors", "gps", "wearable", "wearables", "smart"]
CONCEPTS = {
    "recognizing faces": ["face recognition", "facial recognition", "familiar faces", "familiar face", "face processing", "face identification", "recognize faces", "recognizing faces", "prosopagnosia"],
    "recognizing voices": ["voice recognition", "speaker recognition", "familiar voices", "familiar voice", "voice identification", "phonagnosia"],
    "misidentification": [[["capgras", "misidentification syndrome", "misidentification syndromes"]],
                          [["misidentification", "misidentifications", "misidentify", "misidentified"],
                           ["delusion", "delusions", "delusional", "syndrome", "syndromes", "familiar", "psychosis", "psychotic", "persons", "people"]]],
    "not recognizing family": [[RECOG, FAMILY]],
    "smart glasses": [[["smart glasses", "google glass"]], [["glasses"], ["camera", "cameras", "augmented", "wearable", "smart"]]],
    "wearable camera": ["wearable camera", "wearable cameras", "sensecam", "lifelogging", "life logging"],
    "voice assistant / conversational AI": ["voice assistant", "voice assistants", "conversational agent", "conversational agents", "chatbot", "chatbots", "alexa", "smart speaker", "smart speakers", "language model", "language models"],
    "memory aid": ["memory aid", "memory aids", "memory book", "memory books", "reminder system", "reminder systems", "cognitive prosthesis"],
    "name badges / tags": [[["name badge", "name badges", "name tag", "name tags"]], [["name", "names"], ["badge", "badges"]]],
    "photos / reminiscence": ["reminiscence", "family photos", "photo albums", "life story"],
    "masks / PPE": [[["face masks", "face mask", "personal protective", "protective equipment", "ppe"]], [["masks", "mask"], ["covid", "pandemic", "wearing", "worn"]]],
    "visiting restrictions / separation": [[["visiting restrictions", "visitor restrictions", "visiting ban"]],
                                           [["visits", "visiting", "visitors", "visitation"], ["family", "families", "relatives"], ["covid", "pandemic", "restrictions", "lockdown", "separation"]]],
    "truth-telling / deception": [[["truth telling", "deception", "deceptive", "therapeutic lying", "white lies", "validation therapy"]],
                                  [["lying", "lies"], ["truth", "honesty", "deception", "ethical", "ethics"]]],
    "privacy / consent / surveillance": [[["privacy"]], [["surveillance"], TECH], [["consent"], TECH, ["recording", "recordings", "recorded", "monitoring", "data"]]],
    # "other residents" can't be a bigram ("other" is a stopword), so: bystanders, or privacy + a camera + other people.
    "bystanders / others on camera": [[["bystander", "bystanders"]], [["privacy"], ["camera", "cameras", "video"], ["residents", "staff", "visitors", "roommates"]]],
    "staff turnover / agency staff": [[["staff turnover", "agency staff", "staff shortages", "staffing levels"]],
                                      [["turnover"], ["staff", "workforce", "nurses", "employee", "employees"]]],
}

# The tf-idf query: what Nametags does (weight 3) and where it is used (weight 1).
QUERY = {t: 3.0 for t in ["face recognition", "facial recognition", "voice recognition", "speaker recognition", "familiar faces",
                          "recognize family", "misidentification", "smart glasses", "wearable camera", "voice assistant",
                          "conversational agent", "memory aid", "assistive technology"]}
QUERY |= {t: 1.0 for t in ["care home", "nursing home", "family members", "visitors", "staff", "privacy", "consent",
                           "deception", "truth telling"]}


def timed(label, fn, log):
    t0 = time.time()
    out = fn()
    log[label] = round(time.time() - t0, 1)
    return out


def main():
    OUT.mkdir(exist_ok=True)
    manifest = json.loads((RAW / "manifest.json").read_text())
    s = spark("nametags-corpus")
    sc = s.sparkContext
    stop = frozenset(StopWordsRemover.loadDefaultStopWords("english"))
    secs: dict = {}

    raw = sc.textFile(",".join(str(RAW / f"{t}.jsonl") for t in J.THEMES)).map(json.loads)
    docs, counts = timed("job0", lambda: J.job0_dedup(raw), secs)
    assert counts["unique_before_filter"] == manifest["union_hit_count"], (counts, manifest["union_hit_count"])
    by_id = {r["id"]: r for r in docs.collect()}
    with (RAW / "abstracts.jsonl").open("w") as f:  # full abstracts: git-ignored, never in derived/
        for r in by_id.values():
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (OUT / "job0_counts.json").write_text(json.dumps(counts, indent=2))

    growth = timed("job1", lambda: J.job1_growth(docs), secs)
    per_year = {int(k): v for k, v in manifest["all_dementia_per_year"].items()}
    with (OUT / "growth.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["theme", "year", "papers", "all_dementia_papers", "share_per_1000", "partial_year"])
        for (tag, year), n in sorted(growth.items()):
            total = per_year.get(year)
            w.writerow([tag, year, n, total, round(1000 * n / total, 3) if total else "", year == 2026])
    assert sum(growth.values()) == sum(len(r["tags"]) for r in by_id.values() if r.get("year")), "growth does not reconcile"

    top = timed("job2", lambda: J.job2_top_terms(docs, stop, k=15), secs)
    (OUT / "top_terms.json").write_text(json.dumps(top, indent=2, ensure_ascii=False))

    index = timed("job3_build", lambda: J.job3_inverted_index(docs, stop).cache(), secs)
    vocab = timed("job3_count", lambda: index.count(), secs)
    post = timed("job3_lookup", lambda: J.concept_postings(index, CONCEPTS), secs)
    concepts_out = {}
    for name, ids in post.items():
        best = sorted(ids, key=lambda i: -(by_id[i].get("cited_by") or 0))[:5]
        concepts_out[name] = {"papers": len(ids), "terms": CONCEPTS[name],
                              "most_cited": [{"id": i, "title": by_id[i]["title"], "year": by_id[i]["year"], "doi": by_id[i].get("doi"),
                                              "cited_by": by_id[i].get("cited_by")} for i in best]}
    (OUT / "concepts.json").write_text(json.dumps({"vocabulary_terms": vocab, "concepts": concepts_out}, indent=2, ensure_ascii=False))

    ranked = timed("job4", lambda: J.job4_tfidf(docs, stop, QUERY, k=30), secs)
    reading = [{"rank": n + 1, "score": round(sc_, 4), **{k: by_id[i].get(k) for k in ("id", "title", "year", "journal", "doi", "pmcid", "open_access", "cited_by", "tags")}}
               for n, (i, sc_) in enumerate(ranked)]
    (OUT / "reading_list.json").write_text(json.dumps({"query": QUERY, "ranked": reading}, indent=2, ensure_ascii=False))

    co = timed("job5", lambda: J.job5_cooccurrence(docs), secs)
    matrix = {a: {b: co.get((a, b), 0) for b in J.THEMES} for a in J.THEMES}
    assert matrix["recognition"]["ethics"] == manifest["recognition_and_ethics_hit_count"], (matrix["recognition"]["ethics"], manifest["recognition_and_ethics_hit_count"])
    assert matrix["recognition"]["assistive"] == manifest["recognition_and_assistive_hit_count"], (matrix["recognition"]["assistive"], manifest["recognition_and_assistive_hit_count"])
    (OUT / "cooccurrence.json").write_text(json.dumps(matrix, indent=2))

    if not CMS_FILE.exists():
        r = requests.get(CMS_URL, timeout=180)
        r.raise_for_status()
        CMS_FILE.write_bytes(r.content)
    cms_rows = s.read.csv(str(CMS_FILE), header=True).rdd.map(lambda row: row.asDict())
    cms = timed("job6", lambda: J.job6_cms(cms_rows), secs)
    assert all(v[2] == 1 for v in cms.values()), "a state has more than one row per item"
    pa = (cms[("Pennsylvania", "non_alzheimers_dementia")][:2], cms[("Pennsylvania", "alzheimers")][:2])
    assert pa == ((38.35, 25526), (10.61, 7060)), pa
    # The file carries a "National Total" row: never sum it with the states. The states (minus
    # suppressed cells) must add up to it, within a handful of residents.
    national = {item: cms[("National Total", item)] for item in J.ITEMS.values()}
    for item in J.ITEMS.values():
        states = sum(v[1] for (loc, it), v in cms.items() if it == item and loc != "National Total" and v[1] is not None)
        assert abs(states - national[item][1]) <= 25, (item, states, national[item])
    with (OUT / "cms_dementia_by_state.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["location", "alzheimers_pct", "alzheimers_residents", "non_alzheimers_dementia_pct", "non_alzheimers_dementia_residents"])
        for loc in sorted({k[0] for k in cms}):
            a, d = cms.get((loc, "alzheimers")), cms.get((loc, "non_alzheimers_dementia"))
            w.writerow([loc, a and a[0], a and a[1], d and d[0], d and d[1]])

    emerging = timed("job7", lambda: J.job7_emerging(docs, stop), secs)
    (OUT / "emerging_terms.json").write_text(json.dumps(emerging, indent=2, ensure_ascii=False))

    suppressed = sorted(f"{loc} ({item})" for (loc, item), v in cms.items() if v[0] is None)
    summary = {"job0": counts, "vocabulary_terms": vocab, "seconds": secs,
               "cms_locations": len({k[0] for k in cms}), "cms_suppressed_cells": suppressed, "pa": pa,
               "cms_national": {item: {"pct": v[0], "residents": v[1]} for item, v in national.items()},
               "recognition_x_ethics": matrix["recognition"]["ethics"], "recognition_x_assistive": matrix["recognition"]["assistive"],
               "concept_papers": {k: v["papers"] for k, v in concepts_out.items()},
               "reading_top5": [(x["rank"], x["year"], x["title"][:70]) for x in reading[:5]]}
    (OUT / "run_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    s.stop()


if __name__ == "__main__":
    main()
