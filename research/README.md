# Nametags research pipeline

The code and data behind the [Nametags evidence summary](../docs/research/README.md). It pulls dementia research from
Europe PMC and nursing-home statistics from CMS, cleans and checks both, runs eight MapReduce-shaped jobs on Spark, and
writes the charts and three of the pages in [`docs/research/`](../docs/research/). The
[pipeline map](../docs/research/pipeline.md) tells the whole story, from collection to delivery.

In short:

1. **Collect.** [`pull_corpus.py`](pull_corpus.py) runs five Europe PMC queries (no key and no email) and checks that it
   fetched exactly each query's hit count. [`jobs/run_corpus.py`](jobs/run_corpus.py) downloads the CMS file if it is
   missing.
2. **Clean and analyze.** Eight Spark jobs in [`jobs/corpus_jobs.py`](jobs/corpus_jobs.py), each written as
   map → shuffle → reduce over RDDs: deduplication with veracity filters, growth per year, word count, an inverted
   index with boolean retrieval, a tf-idf reading list, theme co-occurrence, nursing homes by state, and emerging
   terms. No Hadoop cluster and no Hadoop MapReduce job ran; Spark runs in local mode.
3. **Check.** Known-answer tests for every job, a word-for-word check of every quote against its source, and a Crossref
   check of every DOI in the close reading.
4. **Deliver.** [`charts.py`](charts.py) draws the charts, and the generators in [`notes/`](notes/) write
   `problem-size.md`, `care-worker-accounts.md` and `research-at-scale.md`. Most numbers on those pages are read from
   the files here. These are typed into the generators instead:
   - `CMS_ROWS` in `notes/common.py`: 133,920, the rows in the CMS file, which is downloaded, not committed.
   - `FIRST_PULL` in `notes/research_note.py`: 7,926 assistive records, 3,456 of them lab biology, and growth of ×7.5,
     measured on the first pull, which was discarded after the APP fix.
   - `LAB_BIOLOGY_AFTER_FIX` in `notes/research_note.py`: 39, the assistive records still carrying lab-biology markers
     after the fix, counted on the re-pull during the study. No script here recounts them.
   - The Cohen-Mansfield et al. (2014) figures in `notes/evidence_notes.py`: 60% agreeing and 40% arguing, of only 5
     misidentification delusions. An AI agent read them in the paper's Table 1, as the notes in
     `derived/accounts_peer.json` record; the full text refuses scripted reads, so no script checks them.

   The published figures in the prose of `problem-size.md` are typed in as well; `evidence_notes.py` checks each
   headline figure against its sentence in `derived/figures.json`. The few numbers in `research-at-scale.md` sentences
   written by reading titles are typed in too; `research_note.py` stops if the counts behind those sentences change.

## Layout

| Path | What it holds | Committed |
|---|---|---|
| `pull_corpus.py` | The Europe PMC pull; writes `raw/*.jsonl` and `raw/manifest.json` | yes |
| `jobs/` | The Spark jobs (`corpus_jobs.py`), the runner (`run_corpus.py`), the Spark session (`session.py`) and a smoke test | yes |
| `tests/known_answers.py` | Every job run on hand-made abstracts whose answers are known | yes |
| `check_quotes.py` | Fetches each source and matches every recorded quote word for word | yes |
| `check_deep_read.py` | Applies the refuters' verdicts to the close reading and checks sentences and DOIs | yes |
| `check_note_quotes.py` | Checks that every quotation in `docs/research/` and the root `README.md` is in the verified pool | yes |
| `charts.py` | Draws the four charts into `docs/research/charts/` | yes |
| `notes/` | The page generators: `research_note.py`, `evidence_notes.py`, and `common.py` for what they share | yes |
| `raw/` | What was collected: the five theme files, the CMS file, and the deduplicated corpus `abstracts.jsonl` | only `raw/manifest.json` |
| `derived/` | Small aggregates and checked records, about 300 KB | yes |

`raw/manifest.json` stays in git because the pages need it: it holds the queries, each query's hit count at pull time
and the yearly totals for all dementia papers. A fresh pull would give different counts.

The files in `derived/`:

| File | Written by | Holds |
|---|---|---|
| `job0_counts.json` | job 0 | Records before and after deduplication and the veracity filters |
| `growth.csv` | job 1 | Papers per theme and year, with all dementia papers for scale |
| `top_terms.json` | job 2 | The top 15 terms per theme |
| `concepts.json` | job 3 | The vocabulary size, and papers per Nametags concept with the most-cited matches |
| `reading_list.json` | job 4 | The top 30 papers by tf-idf against a query describing Nametags |
| `cooccurrence.json` | job 5 | Papers per pair of themes; the diagonal is each theme's size |
| `cms_dementia_by_state.csv` | job 6 | Dementia diagnoses in nursing homes, by state |
| `emerging_terms.json` | job 7 | Terms rising and falling between 2011–18 and 2019–25 |
| `run_summary.json` | `jobs/run_corpus.py` | The run's headline counts and each job's time in seconds |
| `figures.json` | an AI agent | Published figures, each with its exact source sentence |
| `accounts_peer.json`, `accounts_org.json`, `accounts_extra.json` | AI agents | Care-worker accounts: the quote, its context, and whether it was kept |
| `extra_quotes.json` | an AI agent | 13 more quotes from papers on recognition aids and non-drug care |
| `quote_check.json` | `check_quotes.py` | The word-for-word result for every quote and sentence |
| `deep_read_list.json` | an AI agent | The 20 papers chosen for close reading, and why. The 15 tf-idf picks came from an earlier pull's reading list, so their ranks differ from `reading_list.json`; all 15 are still in its top 30 |
| `deep_read_0.json` to `deep_read_3.json`, and their `_verdicts` files | AI agents | What four readers found, and what four refuters said about it |
| `deep_read_final.json` | `check_deep_read.py` | The close reading with the verdicts applied and the checks recorded |

Some records mention `product.md` and numbered *open tensions*. `product.md` was the study's one-page summary of Nametags
as built, and it is not in this repository; the five open tensions are listed in
[`care-worker-accounts.md`](../docs/research/care-worker-accounts.md).

## Requirements

- [uv](https://docs.astral.sh/uv/), which installs Python 3.12 and the packages from `uv.lock`, including PySpark 4.2.0.
  Installed, the environment takes about 720 MB, most of it PySpark (about 475 MB).
- Java 17, 21 or 25 for Spark. If `JAVA_HOME` is unset and Java 17 is installed at
  `/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home`, the jobs use it. Otherwise, on macOS with Java 17
  installed, run this in the shell first:

  ```bash
  export JAVA_HOME="$(/usr/libexec/java_home -v 17)"
  ```

This project is separate from the Nametags app: the root `pyproject.toml`, its tests and the Docker image never see it.

## Run it

Every command runs from the repository root.

Install the environment:

```bash
uv --directory research sync
```

Run the known-answer tests. They need no data and take about 10 seconds; the last line should read
`known answers: all 8 jobs pass`:

```bash
uv --directory research run python tests/known_answers.py
```

Spark prints a few warnings first (a native-hadoop library, pandas 3); they don't affect the jobs.

Redraw the charts, regenerate the three pages, and check the pages' quotations. These need only the committed files,
and running them again gives byte-identical output:

```bash
uv --directory research run python charts.py
uv --directory research run python notes/research_note.py
uv --directory research run python notes/evidence_notes.py
uv --directory research run python check_note_quotes.py
```

`charts.py` also writes PNG previews to `research/.previews/`, which git ignores.

### Re-run the Spark jobs

The jobs read the corpus files in `research/raw/`, which are not committed. With those files in place, this re-runs all
eight jobs in about 30 seconds on an Apple M1, with no network unless the CMS file is missing:

```bash
uv --directory research run python jobs/run_corpus.py
```

It rewrites `research/derived/`, and `research/raw/abstracts.jsonl`. Every count should come out the same; only the
timings in `derived/run_summary.json` change, which this shows:

```bash
git diff --stat -- research/derived
```

This puts the study's own timings back:

```bash
git restore research/derived/run_summary.json
```

### Steps that need the network

```bash
uv --directory research run python pull_corpus.py
uv --directory research run python check_quotes.py
uv --directory research run python check_deep_read.py
```

- `pull_corpus.py` pulls the corpus again and overwrites `raw/manifest.json`. Europe PMC keeps growing, so the counts will
  differ from the study's; `git restore research/raw/manifest.json` brings the study's back.
- `check_quotes.py` rewrites `derived/quote_check.json`. It identifies itself as `nametags-research-quote-check/0.1`, and
  a site that refuses it is recorded as unreachable, never worked around.
- `check_deep_read.py` rewrites `derived/deep_read_final.json`, checking each DOI against Crossref.

## Data sources and licensing

- **Europe PMC**, through its search API at `https://www.ebi.ac.uk/europepmc/webservices/rest/search`: titles, abstracts
  and metadata for the corpus. The abstracts belong to their authors and publishers, so they are not committed:
  `raw/abstracts.jsonl` stays on the machine that pulled them.
- **CMS** (Centers for Medicare & Medicaid Services): the Minimum Data Set Frequency file, state level, Q3 2026, a
  public file downloaded by `jobs/run_corpus.py` and not committed. Only the state totals in `derived/` are.
- **Published figures**: the Alzheimer's Association's *2026 Alzheimer's Disease Facts and Figures*, the WHO dementia
  fact sheet, NCHS FastStats, the Alzheimer's Society, and three abstracts, each cited in `derived/figures.json`.
- **Accounts and close reading**: peer-reviewed papers found through Europe PMC, and guidance from dementia
  organizations, each cited with its DOI or URL.
- **Crossref**: DOI metadata for the citation checks.

The code is covered by the repository's [MIT license](../LICENSE). The quotes and source sentences in `derived/` belong
to their sources: they are short, attributed, and kept so each one can be checked.
