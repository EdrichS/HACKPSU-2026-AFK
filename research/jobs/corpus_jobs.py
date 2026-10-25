"""The study's Spark jobs, each written as map -> shuffle -> reduce (CSCI 436 Lecture 4, Lab 1).

Every function takes RDDs and returns plain Python values, so `tests/known_answers.py` can run
the same code on hand-made abstracts whose answers are known.
"""
import math
import re

THEMES = ["assistive", "recognition", "carehome", "ethics", "truth"]

# Veracity filter for the truth theme. The Europe PMC query includes the bare words "lie" and
# "lies", which mostly match the verb ("the novelty lies in ..."): 842 of 1,138 records, measured
# Oct 25 00:40. A record keeps its truth tag only if it really talks about truth-telling.
TRUTH_STRICT = re.compile(
    r"\b(deception|deceptive|deceit\w*|deceiv\w*|therapeutic (lie|lies|lying)|truth[- ]telling"
    r"|white (lie|lies)|validation therapy|honesty|untruth\w*)\b", re.I)
# Bare "lying" is excluded above: it also means lying down ("lying in bed"). It counts only when
# it is about telling lies.
TRUTH_TELLING_LIES = re.compile(
    r"\b(tell|tells|telling|told)\b[^.]{0,40}\b(lie|lies)\b"
    r"|\b(lie|lies|lying)\b[^.]{0,15}\b(to|about)\b[^.]{0,20}\b(patient|patients|resident|residents|person|people|them|him|her|family|families|relatives)\b"
    r"|\blying\b[^.]{0,60}\b(truth|honest\w*|deceiv\w*|deception|ethic\w*)\b|\b(truth|honest\w*|deception|ethic\w*)\b[^.]{0,60}\blying\b",
    re.I)

# Veracity filter for the ethics theme: 44 of 1,064 records (measured 00:57) were there only
# because of approval boilerplate ("ethics committee approval", "written informed consent").
ETHICS_BOILER = re.compile(
    r"(ethic\w* (committee|approval|board)|approved by the \w+ ethic\w*|informed consent was obtained"
    r"|written informed consent|institutional review board)", re.I)
ETHICS_TERM = re.compile(r"\b(ethics|ethical|privacy|surveillance|informed consent|autonomy|dignity|data protection)\b", re.I)

TOKEN = re.compile(r"[a-z][a-z']*[a-z]|[a-z]")

# Words that say nothing about a theme because nearly every abstract in this corpus has them.
# Used only by the top-terms job; tf-idf and the index keep them and let idf weigh them down.
DOMAIN_STOP = {
    "dementia", "dementias", "alzheimer", "alzheimer's", "alzheimers", "disease", "diseases",
    "patients", "patient", "people", "persons", "person", "study", "studies", "results", "result",
    "methods", "method", "conclusion", "conclusions", "background", "objective", "objectives",
    "aim", "aims", "also", "using", "used", "use", "may", "can", "however", "among", "well",
    "including", "based", "new", "one", "two", "three", "data", "findings", "review", "research",
    "analysis", "participants", "significant", "significantly", "associated", "compared", "group",
    "groups", "years", "year", "within", "whether", "two", "high", "higher", "low", "lower",
}


def text_of(r: dict) -> str:
    return f"{r.get('title') or ''} {r.get('abstract') or ''}"


def terms(text: str, stop: frozenset) -> list[str]:
    """Unigrams minus stopwords, plus bigrams of adjacent tokens where neither is a stopword.

    Hyphens become spaces first, so "truth-telling" is the bigram "truth telling"."""
    toks = TOKEN.findall(text.lower().replace("-", " "))
    uni = [t for t in toks if t not in stop and len(t) > 1]
    bi = [f"{a} {b}" for a, b in zip(toks, toks[1:]) if a not in stop and b not in stop and len(a) > 1 and len(b) > 1]
    return uni + bi


def keeps_truth_tag(r: dict) -> bool:
    t = text_of(r)
    return bool(TRUTH_STRICT.search(t) or TRUTH_TELLING_LIES.search(t))


def keeps_ethics_tag(r: dict) -> bool:
    return bool(ETHICS_TERM.search(ETHICS_BOILER.sub(" ", text_of(r))))


# ---- Job 0: deduplicate, merge query tags, apply the truth veracity filter ----------------------

def job0_dedup(raw):
    """raw: RDD of per-theme records (one per theme hit). Returns (unique RDD, counts dict)."""
    merged = (
        raw.map(lambda r: (r["id"], (r, {r["theme"]})))                       # map
        .reduceByKey(lambda a, b: (a[0], a[1] | b[1]))                         # shuffle + reduce
        .map(lambda kv: {**{k: v for k, v in kv[1][0].items() if k != "theme"}, "tags": sorted(kv[1][1])})
    )

    checks = {"truth": keeps_truth_tag, "ethics": keeps_ethics_tag}

    def filter_tags(r):
        drop = {t for t, ok in checks.items() if t in r["tags"] and not ok(r)}
        return {**r, "tags": [t for t in r["tags"] if t not in drop]} if drop else r

    filtered = merged.map(filter_tags)
    kept = filtered.filter(lambda r: r["tags"]).cache()
    counts = {
        "unique_before_filter": merged.count(),
        "truth_tags_removed": merged.filter(lambda r: "truth" in r["tags"]).count()
        - filtered.filter(lambda r: "truth" in r["tags"]).count(),
        "ethics_tags_removed": merged.filter(lambda r: "ethics" in r["tags"]).count()
        - filtered.filter(lambda r: "ethics" in r["tags"]).count(),
        "records_dropped_by_filter": filtered.filter(lambda r: not r["tags"]).count(),
        "unique_after_filter": kept.count(),
    }
    return kept, counts


# ---- Job 1: growth, papers per (tag, year) ------------------------------------------------------

def job1_growth(docs) -> dict:
    return dict(
        docs.flatMap(lambda r: [((t, r["year"]), 1) for t in r["tags"] if r.get("year")])   # map
        .reduceByKey(lambda a, b: a + b)                                                     # reduce
        .collect()
    )


# ---- Job 2: word count per tag (Lab 1), counting each term once per paper ---------------------

def job2_top_terms(docs, stop: frozenset, k: int = 15) -> dict:
    stop_all = frozenset(stop | DOMAIN_STOP)
    counts = (
        docs.flatMap(lambda r: [((t, term), 1) for term in set(terms(text_of(r), stop_all)) for t in r["tags"]])
        .reduceByKey(lambda a, b: a + b)
    )
    top = (
        counts.map(lambda kv: (kv[0][0], (kv[1], kv[0][1])))
        .groupByKey()
        .mapValues(lambda vs: sorted(vs, key=lambda x: (-x[0], x[1]))[:k])
        .collect()
    )
    return {tag: [(term, n) for n, term in vs] for tag, vs in top}


# ---- Job 3: inverted index (Lecture 4): term -> sorted postings ------------------------------

def job3_inverted_index(docs, stop: frozenset):
    return (
        docs.flatMap(lambda r: [(term, r["id"]) for term in set(terms(text_of(r), stop))])   # map
        .groupByKey()                                                                       # shuffle
        .mapValues(lambda ids: sorted(set(ids)))                                            # reduce
    )


def concept_postings(index, concepts: dict) -> dict:
    """Boolean retrieval over the inverted index (Lecture 4).

    concepts: name -> list of alternatives; each alternative is a list of groups; a group is a
    list of index terms. Terms in a group are ORed (union of postings), groups are ANDed
    (intersection), and alternatives are ORed. A plain list of terms is one alternative with one
    group. Returns name -> sorted doc ids."""
    def alternatives(spec):
        return [[spec]] if spec and isinstance(spec[0], str) else spec

    wanted = {t for spec in concepts.values() for alt in alternatives(spec) for group in alt for t in group}
    post = {term: set(ids) for term, ids in index.filter(lambda kv: kv[0] in wanted).collect()}
    out = {}
    for name, spec in concepts.items():
        hits = set()
        for alt in alternatives(spec):
            sets = [set().union(*(post.get(t, set()) for t in group)) for group in alt]
            hits |= set.intersection(*sets) if sets else set()
        out[name] = sorted(hits)
    return out


# ---- Job 4: tf-idf with cosine similarity against a weighted Nametags query -------------------

def job4_tfidf(docs, stop: frozenset, query: dict, k: int = 15) -> list:
    n_docs = docs.count()
    tf = (
        docs.flatMap(lambda r: [((r["id"], term), 1) for term in terms(text_of(r), stop)])
        .reduceByKey(lambda a, b: a + b)                                   # (doc, term) -> tf
        .map(lambda kv: (kv[0][1], (kv[0][0], kv[1])))                     # term -> (doc, tf)
    )
    idf = tf.map(lambda kv: (kv[0], 1)).reduceByKey(lambda a, b: a + b).mapValues(lambda df: math.log(n_docs / df))
    weighted = tf.join(idf).map(lambda kv: (kv[1][0][0], (kv[0], kv[1][0][1] * kv[1][1])))   # doc -> (term, w)
    norms = weighted.mapValues(lambda tw: tw[1] ** 2).reduceByKey(lambda a, b: a + b).mapValues(math.sqrt)
    idf_q = dict(idf.filter(lambda kv: kv[0] in query).collect())
    qvec = {t: w * idf_q[t] for t, w in query.items() if t in idf_q}
    qnorm = math.sqrt(sum(v * v for v in qvec.values())) or 1.0
    dots = weighted.filter(lambda kv: kv[1][0] in qvec).mapValues(lambda tw: tw[1] * qvec[tw[0]]).reduceByKey(lambda a, b: a + b)
    scores = dots.join(norms).mapValues(lambda dn: dn[0] / (dn[1] * qnorm) if dn[1] else 0.0)
    return scores.takeOrdered(k, key=lambda kv: (-kv[1], kv[0]))


# ---- Job 5: theme co-occurrence ---------------------------------------------------------------

def job5_cooccurrence(docs) -> dict:
    return dict(
        docs.flatMap(lambda r: [((a, b), 1) for a in r["tags"] for b in r["tags"]])   # map: every ordered pair
        .reduceByKey(lambda a, b: a + b)                                            # reduce
        .collect()
    )


# ---- Job 6: nursing-home dementia diagnoses by state (CMS MDS frequency file) -----------------

ITEMS = {"I4200": "alzheimers", "I4800": "non_alzheimers_dementia"}


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def job6_cms(rows) -> dict:
    """rows: RDD of dicts with the CSV's columns. Returns (state, item) -> (percent, residents, rows).

    CMS prints "*" for cells it suppresses for privacy; those come back as (None, None, 1)."""
    def pick(r):
        code = (r.get("MDS Item Question/Description") or "").split(":")[0].strip()
        if code in ITEMS and (r.get("MDS Item Response") or "").strip() == "Yes":
            pct, n = _num(r.get("Percent")), _num(r.get("Total Residents"))
            return [((r["Geographical Location"], ITEMS[code]), (pct, int(n) if n is not None else None, 1))]
        return []

    return dict(
        rows.flatMap(pick)                                                          # map
        .reduceByKey(lambda a, b: (a[0], a[1], a[2] + b[2]))                         # reduce: keep, count rows
        .collect()
    )


# ---- Job 7: emerging terms, 2011-18 versus 2019-25 --------------------------------------------

def job7_emerging(docs, stop: frozenset, min_docs: int = 15, k: int = 15):
    stop_all = frozenset(stop | DOMAIN_STOP)

    def era(y):
        return "early" if y and 2011 <= y <= 2018 else ("late" if y and 2019 <= y <= 2025 else None)

    tagged = docs.filter(lambda r: era(r.get("year")) is not None)
    sizes = dict(tagged.map(lambda r: (era(r["year"]), 1)).reduceByKey(lambda a, b: a + b).collect())
    counts = (
        tagged.flatMap(lambda r: [((term, era(r["year"])), 1) for term in set(terms(text_of(r), stop_all))])
        .reduceByKey(lambda a, b: a + b)
        .map(lambda kv: (kv[0][0], {kv[0][1]: kv[1]}))
        .reduceByKey(lambda a, b: {**a, **b})
        .filter(lambda kv: sum(kv[1].values()) >= min_docs)
    )
    e, l = sizes.get("early", 1), sizes.get("late", 1)
    ratio = counts.map(lambda kv: (kv[0], math.log(((kv[1].get("late", 0) + 1) / l) / ((kv[1].get("early", 0) + 1) / e)), kv[1]))
    return {
        "era_sizes": sizes,
        "rising": ratio.takeOrdered(k, key=lambda x: -x[1]),
        "falling": ratio.takeOrdered(k, key=lambda x: x[1]),
    }
