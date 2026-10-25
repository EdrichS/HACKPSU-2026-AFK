"""Write docs/research/research-at-scale.md from the files in derived/ and raw/manifest.json.

Nearly every number on the page is read from those files, so re-running the pipeline can't leave a
stale figure behind. The prose is fixed and the numbers are formatted in. Two kinds of exception
are named below: numbers typed in (FIRST_PULL and LAB_BIOLOGY_AFTER_FIX, plus CMS_ROWS from
common.py), and sentences written by reading titles, which are checked against the counts they were
written for (WRITTEN_FOR) so that new data stops the script instead of leaving the prose wrong.
From the repository root:

    uv --directory research run python notes/research_note.py
"""
import csv
import json
from collections import defaultdict

from common import CMS_ROWS, CODE, DERIVED as D, RAW, generated_by, repo_text, short, table, tensions_list, write

m = json.load(open(RAW / "manifest.json"))
s = json.load(open(D / "run_summary.json"))
j0 = json.load(open(D / "job0_counts.json"))
assert s["job0"] == j0, "run_summary.json and job0_counts.json disagree"
co = json.load(open(D / "cooccurrence.json"))
concepts = json.load(open(D / "concepts.json"))
top = json.load(open(D / "top_terms.json"))
em = json.load(open(D / "emerging_terms.json"))
deep = json.load(open(D / "deep_read_list.json"))
final = json.load(open(D / "deep_read_final.json"))
hits = {t["theme"]: t["hit_count"] for t in m["themes"]}
after = {t: co[t][t] for t in co}  # each theme's size after the veracity filters: the co-occurrence diagonal
total = j0["unique_after_filter"]
c = {k: v["papers"] for k, v in concepts["concepts"].items()}

growth = defaultdict(dict)
T = {}
for r in csv.DictReader(open(D / "growth.csv")):
    growth[r["theme"]][int(r["year"])] = int(r["papers"])
    if r["all_dementia_papers"]:
        T[int(r["year"])] = int(r["all_dementia_papers"])
A = growth["assistive"]

cms = list(csv.DictReader(open(D / "cms_dementia_by_state.csv")))
national = next(r for r in cms if r["location"] == "National Total")
cms_gap = max(int(national[f"{i}_residents"]) - sum(int(r[f"{i}_residents"]) for r in cms
                                                    if r["location"] != "National Total" and r[f"{i}_residents"])
              for i in ("alzheimers", "non_alzheimers_dementia"))

# The first pull, discarded after the APP fix: measured on Oct 25, 2026, and no longer in the files.
FIRST_PULL = {"assistive": 7_926, "lab_biology": 3_456, "growth": "×7.5"}
LAB_BIOLOGY_AFTER_FIX = 39  # assistive records still carrying lab-biology markers after the fix
# Counts that the sentences written from reading titles describe.
WRITTEN_FOR = {"recognition x ethics": 6, "recognition x assistive": 11, "smart glasses": 3, "name badges / tags": 1,
               "bystanders / others on camera": 6, "recognizing voices": 25}
now = {"recognition x ethics": co["recognition"]["ethics"], "recognition x assistive": co["recognition"]["assistive"],
       "smart glasses": c["smart glasses"], "name badges / tags": c["name badges / tags"],
       "bystanders / others on camera": c["bystanders / others on camera"], "recognizing voices": c["recognizing voices"]}
assert now == WRITTEN_FOR, f"the counts changed, so review the sentences written for them: {now}"

LABEL = {"assistive": "Assistive technology", "recognition": "Recognizing people", "carehome": "Care-home staff (qualitative)",
         "ethics": "Ethics of technology", "truth": "Truth-telling and deception"}
WHAT = {
    "assistive": "named assistive technologies (smart homes, telecare, memory aids, robots, smart glasses, wearable cameras), or technology words alongside daily-life words",
    "recognition": "face, facial, voice, speaker and person recognition; familiar or famous faces and voices; prosopagnosia; misidentification; Capgras",
    "carehome": "care or nursing homes, with staff, studied by interview, focus group or thematic analysis",
    "ethics": "ethics, privacy, surveillance, consent, autonomy or dignity, alongside AI, monitoring, cameras, sensors, robots, voice assistants",
    "truth": "lying, deception, truth-telling, white lies, validation therapy",
}
# Publishing boilerplate that the emerging-terms job picks up (registered-report identifiers, COREQ, CONSORT).
BOILER = {"identifier irrid", "irrid", "registered report", "report identifier", "international registered", "consolidated",
          "derr", "irrid derr", "smd"}


def x(a, b):
    return f"×{a / b:.1f}" if b else "n/a"


themes = list(LABEL)
ratios = {t: growth[t].get(2025, 0) / growth[t][2010] for t in ("assistive", "ethics", "carehome", "recognition")}
assert max(ratios, key=ratios.get) == "ethics", ratios  # "grew fastest" below
corpus_rows = [(LABEL[t], WHAT[t], f"{hits[t]:,}", f"{after[t]:,}") for t in themes]
growth_rows = [(LABEL[t], *(growth[t].get(y, 0) for y in (2010, 2015, 2020, 2025)), x(growth[t].get(2025, 0), growth[t][2010]))
               for t in ("assistive", "ethics", "carehome", "recognition")]
growth_rows.append(("All dementia papers (for scale)", *(f"{T[y]:,}" for y in (2010, 2015, 2020, 2025)), x(T[2025], T[2010])))
matrix_rows = [(LABEL[a], *(f"{co[a][b]:,}" for b in themes)) for a in themes]
concept_rows = []
for name, v in sorted(concepts["concepts"].items(), key=lambda kv: -kv[1]["papers"]):
    ex = v["most_cited"][0] if v["most_cited"] else None
    concept_rows.append((name, v["papers"], f"{short(ex['title'], 80)} ({ex['year']})" if ex else "—"))
term_rows = [(LABEL[t], ", ".join(w for w, _ in top[t][:10])) for t in themes]
rising = [f"{t} ({n.get('early', 0)} → {n.get('late', 0)})" for t, _, n in em["rising"] if t not in BOILER]
falling = [f"{t} ({n.get('early', 0)} → {n.get('late', 0)})" for t, _, n in em["falling"] if t not in BOILER]
read_as = {e["id"]: e.get("text_source") for e in final}
read_rows = [(i + 1, p["year"], short(p["title"]), p["why"], read_as.get(p["id"], "not read")) for i, p in enumerate(deep["papers"])]
secs = s["seconds"]

tally = defaultdict(int)
for e in final:
    tally[e["verdict"]] += 1
verdict_line = ", ".join(f"{n} {v}" for v, n in sorted(tally.items()))
order = {"high": 0, "medium": 1, "low": 2, "off-topic": 3}
kept = sorted((e for e in final if e["verdict"] in ("confirmed", "corrected")),
              key=lambda e: (order.get(e.get("relevance"), 4), -(e.get("year") or 0)))
papers = []
for e in kept:
    passed = str(e.get("sentence_check", "")).startswith("pass")
    cr = e.get("crossref", {})
    cr_ok = cr.get("title_similarity", 0) >= 0.85 and cr.get("first_author_match") and cr.get("year_within_1")
    sentence = f"“{e['supporting_sentence']}”" if passed else "not quoted: it did not match its source word for word"
    crossref = ("matches Crossref on title, first author and year" if cr_ok else
                f"Crossref check incomplete (title similarity {cr.get('title_similarity')}, first author "
                f"{cr.get('first_author_match')}, year {cr.get('year_within_1')})")
    papers.append(f"""### {e['title'].rstrip('.')} ({e['year']})

- **Relevance to Nametags:** {e.get('relevance')}. Read from the {e.get('text_source')}.
- **What it shows:** {repo_text(e.get('finding_for_nametags'))}
- **Method and sample:** {repo_text(e.get('method_and_sample'))}
- **Limitation:** {repo_text(e.get('limitation'))}
- **Supporting sentence:** {sentence}
- **Checks:** {'the sentence was matched word for word in its source, by script' if passed else 'sentence not matched'};
  [doi:{e['doi']}](https://doi.org/{e['doi']}) {crossref}. The refuting agent's verdict: {e['verdict']}.""")


def out(name: str) -> str:
    return f"[`{name}`]({CODE}/derived/{name})"


PAGE = f"""# Research at scale

A Spark analysis of {m['union_hit_count']:,} dementia papers from Europe PMC, pulled {m['pulled_at']}: how fast the
research around Nametags is growing, where it leaves gaps, and what {len(final)} closely read papers say. Part of the
[evidence summary](README.md). The study is framed with the course CSCI 436 (Big Data Management and Analytics), and
the [pipeline map](pipeline.md) shows how the data moved from collection to these pages.

{generated_by("notes/research_note.py")}

## The short version

- **The field around Nametags is growing fast.** Papers on assistive technology for dementia went from {A[2010]} in 2010
  to {A[2025]} in 2025 ({x(A[2025], A[2010])}). All dementia papers grew {x(T[2025], T[2010])} over the same years.
- **What Nametags does sits in a gap between queries.** Of {co['recognition']['recognition']} abstracts matching the
  recognition query (faces, voices, misidentification), {co['recognition']['assistive']} also match the
  assistive-technology query, {co['recognition']['ethics']} the ethics-of-technology query, and
  {co['recognition']['carehome']} the care-home-staff interview query.
  - **These are query overlaps, not topics.** The {co['recognition']['ethics']} ethics matches include a psilocybin
    review and an MRI de-identification tool. Only one of those {co['recognition']['ethics']}, McCarron et al. 2019, is
    about technology that recognizes people. The {co['recognition']['assistive']} assistive overlaps include more prior
    art, such as Fardoun et al. 2017.
  - **What holds:** research on the problem and research on the tools barely meet.
- **Its newest parts barely show up.** Out of {total:,} abstracts, these match each concept's terms:
  - smart glasses: {c['smart glasses']} (one of them is about audio glasses);
  - wearable cameras: {c['wearable camera']};
  - privacy with cameras and other people: {c['bystanders / others on camera']} (none uses the word *bystander*);
  - voice-recognition terms: {c['recognizing voices']}. By title, most of these are about speech technology, such as
    voice-controlled cognitive screeners; only a handful study how people with dementia recognize voices.

![Line chart: papers per year on dementia technology and on all dementia research, each indexed to its 2010 count](charts/growth-index.svg)

## The corpus

Five Europe PMC queries over titles and abstracts, restricted to records with an abstract and with preprints excluded.
The exact query strings are in [`pull_corpus.py`]({CODE}/pull_corpus.py) and in [`raw/manifest.json`]({CODE}/raw/manifest.json),
which also records each query's hit count at pull time. The pull checks that it got exactly as many records as each
query's hit count.

{table(["Theme", "What the query matches", "Europe PMC hits", "Kept after veracity checks"], corpus_rows)}

- **Combined and deduplicated:** {j0['unique_before_filter']:,} papers. This is exactly the combined query's hit count,
  which job 0 checks.
- **After the veracity filters below:** {total:,} papers.

## Veracity: four problems found in the data and fixed

CSCI 436's fourth V, veracity, asks whether the data can be trusted. Each of these problems was found by checking the
output, not assumed.

1. **APP is a protein.** Europe PMC search ignores case, so the assistive query's word `app` also matched APP, the
   amyloid precursor protein.
   - The query's `memory` matched nearly every Alzheimer's abstract, so mouse-model papers poured in.
   - In the first pull, {FIRST_PULL['lab_biology']:,} of {FIRST_PULL['assistive']:,} assistive records
     ({FIRST_PULL['lab_biology'] / FIRST_PULL['assistive']:.0%}) were lab biology that named no assistive technology.
     Their top words were *amyloid* and *mice*.
   - The fix: `app` now appears only inside phrases like `mobile app`, and the same goes for tablets (pills), sensors
     (biosensors) and `digital` (digital PCR).
   - The theme fell to {hits['assistive']:,} records, of which {LAB_BIOLOGY_AFTER_FIX} (about
     {LAB_BIOLOGY_AFTER_FIX / hits['assistive']:.1%}) still carry lab-biology markers.
   - Fixing it changed the headline growth figure from {FIRST_PULL['growth']} to {x(A[2025], A[2010])}: the biology
     papers had been inflating the 2010 baseline.
2. **`lies` is also a verb.** The truth-telling query includes the words `lie` and `lies`, which mostly match sentences
   like *the novelty lies in…*. The same goes for *lying in bed*.
   - A filter in job 0's map step keeps the truth tag only when real truth-telling language is present.
   - It removed {j0['truth_tags_removed']:,} tags, keeping {after['truth']} of {hits['truth']:,}.
3. **Ethics boilerplate.** {j0['ethics_tags_removed']} ethics records were there only because the abstract says *ethics
   committee approval* or *written informed consent*. The same map-step filter removed them.
4. **The CMS file contains a national row.** The nursing-home file has a `National Total` row among the states, so
   summing all rows double-counts the country.
   - The states reconcile with that row within {cms_gap} resident{'' if cms_gap == 1 else 's'}, and job 6 checks it.
   - Puerto Rico and the Virgin Islands are suppressed by CMS, shown as `*`. They're kept as missing, not dropped.

## Growth

{table(["Theme", "2010", "2015", "2020", "2025", "2025 vs 2010"], growth_rows)}

The ethics of dementia technology grew fastest, from {growth['ethics'][2010]} to {growth['ethics'][2025]} papers. By
contrast, research on recognizing people grew only at the field's pace.

## The gap

![Bar chart: of the abstracts matching the recognition query, how many also match each other query](charts/recognition-gap.svg)

Papers in both themes. The diagonal is each theme's size after the veracity filters.

{table(["", *[LABEL[t] for t in themes]], matrix_rows)}

Europe PMC's own intersection counts agree, and job 5 checks both: recognizing people with assistive technology gives
{m['recognition_and_assistive_hit_count']} papers, and recognizing people with ethics of technology gives
{m['recognition_and_ethics_hit_count']}.

## How much research touches each Nametags feature

![Bar chart: how many abstracts match each Nametags concept](charts/concepts.svg)

**How the counts work.** These come from boolean retrieval over the inverted index (job 3), as in Lecture 4 of the
course. Words with a second meaning only count next to their context:
- `masks` only with COVID or wearing;
- `visits` only with family and restrictions;
- `turnover` only with staff;
- `surveillance` and `consent` only with cameras or sensors;
- `misidentification` only with delusion, syndrome or familiar people.

The full term lists are in [`jobs/run_corpus.py`]({CODE}/jobs/run_corpus.py).

**Caveats:**
- **Not recognizing family:** this concept is still noisy. The index matches words anywhere in an abstract, not within
  one sentence, so it is listed below but left out of the chart.
- **Name badges:** the single match is a 1992 study about remembering famous *names*, so effectively nothing studies
  name badges.

{table(["Concept", "Papers", "Most-cited match"], concept_rows)}

## What each theme talks about

Word count, as in the course's Hadoop Lab 1: each word or word pair is counted once per paper, after removing English
stopwords and the words nearly every abstract here shares (dementia, patients, study and the like).

{table(["Theme", "Top 10 terms"], term_rows)}

## Rising and falling terms, 2011–18 against 2019–25

The counts are papers per era: {em['era_sizes'].get('early', 0):,} papers in 2011–18 and
{em['era_sizes'].get('late', 0):,} in 2019–25. Publishing boilerplate (registered-report identifiers, COREQ and CONSORT
phrases) is left out.

- **Rising:** {"; ".join(rising)}.
- **Falling:** {"; ".join(falling)}.

Two shifts stand out: COVID became a research topic in its own right, and AI and deep learning arrived. Meanwhile, the
recognition theme's older neuroimaging vocabulary (fusiform, famous faces, fMRI) is fading.

## The reading list

**Selection rule:** {repo_text(deep['selection_rule'])}.

**Dropped:**
{chr(10).join(f"- rank {k}: {v}" for k, v in deep['dropped'].items())}

{table(["#", "Year", "Title", "Why", "Read from"], read_rows)}

## What the {len(final)} papers say (verified)

Four AI agents read the papers, using the open full text where there is one and the abstract otherwise. Four other
agents then tried to refute each entry: {verdict_line}. Two checks back that up:
- every supporting sentence below was matched word for word in its source by script;
- every DOI was checked against Crossref for title, first author and year.

The entries refer to the study's open tensions by number:

{tensions_list()}

{chr(10).join(p + chr(10) for p in papers)}
## The jobs, in MapReduce form

Every job is written as map, then shuffle, then reduce, with Spark RDDs
([`jobs/corpus_jobs.py`]({CODE}/jobs/corpus_jobs.py)). Each was first run on hand-made abstracts with known answers
([`tests/known_answers.py`]({CODE}/tests/known_answers.py), covering all eight jobs). They ran on an Apple M1 laptop with
8 GB of memory, in Spark local mode with 4 cores.

| Job | Map | Reduce | Output | Seconds |
|---|---|---|---|---|
| 0. Deduplicate | `(id, (record, {{theme}}))`, then the veracity filters | merge the theme sets | `raw/abstracts.jsonl` (not committed) and {out('job0_counts.json')} | {secs['job0']} |
| 1. Growth | `((theme, year), 1)` | sum | {out('growth.csv')} | {secs['job1']} |
| 2. Word count (Lab 1) | `((theme, term), 1)`, once per paper | sum, top 15 | {out('top_terms.json')} | {secs['job2']} |
| 3. Inverted index (Lecture 4) | `(term, id)` | group into postings | {out('concepts.json')}, {s['vocabulary_terms']:,} terms | {secs['job3_count']} + {secs['job3_lookup']} lookup |
| 4. Tf-idf reading list | `((id, term), 1)`, joined with idf | cosine against the Nametags query | {out('reading_list.json')} | {secs['job4']} |
| 5. Co-occurrence | `((theme₁, theme₂), 1)` | sum | {out('cooccurrence.json')} | {secs['job5']} |
| 6. Nursing homes (CMS) | `((state, item), (pct, residents))` | one row per key | {out('cms_dementia_by_state.csv')} | {secs['job6']} |
| 7. Emerging terms | `((term, era), 1)` | sum, smoothed log ratio | {out('emerging_terms.json')} | {secs['job7']} |

No Hadoop cluster ran, and no Hadoop MapReduce job: these are MapReduce-shaped jobs on Spark, and the optional Hadoop
Streaming run was cut. {total:,} abstracts don't need Spark; the same code could run on a cluster (not tested on one).

## The CSCI 436 lens

| Idea from the course | In this study | In Nametags itself |
|---|---|---|
| Volume | {m['union_hit_count']:,} abstracts and {CMS_ROWS:,} rows of CMS data. Honestly small: one laptop is enough | Tiny per home: a few hundred face and voice samples. Large only if it ran across every care home |
| Velocity | Batch: pulled once, analyzed in seconds | Data in motion: camera frames up to 3 per second and audio in chunks, matched as they arrive |
| Variety | Text, metadata, keywords; a CSV of state statistics | Images, audio, 128- and 192-number embeddings, transcripts, facts, the card |
| Veracity | Four real data-quality problems, found and fixed above | Recognition is uncertain by nature, so cutoffs, margins and *not sure* are veracity controls |
| Data at rest vs in motion | The corpus is at rest (OLAP-style analysis) | The live path is in motion (RTAP-style); enrolled samples and facts are at rest |
| MapReduce / Spark | All eight jobs are written for Spark, so the same code could run on a cluster (not tested on one) | Not needed: matching is one SQL query over a few hundred rows |
| Relational vs NoSQL, CAP | — | Postgres with pgvector on one node: consistency over partition tolerance, because a wrong name is worse than no name. [`DEPLOY.md`](../../DEPLOY.md) moves it to a server, which brings availability and network partitions into play |

## Reproduce

From the repository root, with uv and Java 17 installed:

```bash
uv --directory research run python tests/known_answers.py
uv --directory research run python charts.py
uv --directory research run python notes/research_note.py
uv --directory research run python notes/evidence_notes.py
uv --directory research run python check_note_quotes.py
```

The Spark jobs also need the corpus files in `research/raw/`, which are not committed. With them,
`uv --directory research run python jobs/run_corpus.py` rewrites `research/derived/`. Without them,
`uv --directory research run python pull_corpus.py` pulls the corpus again, but Europe PMC keeps growing, so a fresh
pull gives different counts from the study's, which stay recorded in `research/raw/manifest.json`.
[`research/README.md`]({CODE}/README.md) has the details.
"""

if __name__ == "__main__":
    print("wrote", write("research-at-scale.md", PAGE))
