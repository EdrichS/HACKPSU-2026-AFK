"""Known-answer tests: run every corpus job on a few hand-made abstracts with hand-computed answers.

From the repository root:

    uv --directory research run python tests/known_answers.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "jobs"))

from pyspark.ml.feature import StopWordsRemover  # noqa: E402

import corpus_jobs as J  # noqa: E402
from session import spark  # noqa: E402

RAW = [
    {"id": "MED:1", "year": 2015, "title": "Face recognition in dementia", "abstract": "Familiar faces are hard to recognize.", "theme": "recognition"},
    {"id": "MED:1", "year": 2015, "title": "Face recognition in dementia", "abstract": "Familiar faces are hard to recognize.", "theme": "assistive"},
    {"id": "MED:2", "year": 2020, "title": "Smart glasses for memory", "abstract": "A wearable camera names visitors.", "theme": "assistive"},
    {"id": "MED:3", "year": 2020, "title": "Care home staff interviews", "abstract": "Staff described residents who did not recognize family.", "theme": "carehome"},
    {"id": "MED:4", "year": 2021, "title": "The answer lies in the data", "abstract": "Biomarkers matter.", "theme": "truth"},
    {"id": "MED:5", "year": 2021, "title": "Therapeutic lying in dementia care", "abstract": "Nurses discussed the ethics of truth-telling and deception.", "theme": "truth"},
    {"id": "MED:5", "year": 2021, "title": "Therapeutic lying in dementia care", "abstract": "Nurses discussed the ethics of truth-telling and deception.", "theme": "ethics"},
    {"id": "MED:6", "year": 2022, "title": "Gait sensors at home", "abstract": "Ethics committee approval was obtained. Sensors tracked gait.", "theme": "ethics"},
]

s = spark("known-answers")
sc = s.sparkContext
STOP = frozenset(StopWordsRemover.loadDefaultStopWords("english"))

# Job 0: six unique papers; MED:4 loses its only tag (the verb "lies") and MED:6 its only tag
# (approval boilerplate), so both drop out.
docs, counts = J.job0_dedup(sc.parallelize(RAW))
assert counts == {"unique_before_filter": 6, "truth_tags_removed": 1, "ethics_tags_removed": 1,
                  "records_dropped_by_filter": 2, "unique_after_filter": 4}, counts
tags = {r["id"]: r["tags"] for r in docs.collect()}
assert tags == {"MED:1": ["assistive", "recognition"], "MED:2": ["assistive"], "MED:3": ["carehome"], "MED:5": ["ethics", "truth"]}, tags

# Job 1: one paper per (tag, year) here.
growth = J.job1_growth(docs)
assert growth == {("assistive", 2015): 1, ("recognition", 2015): 1, ("assistive", 2020): 1, ("carehome", 2020): 1,
                  ("ethics", 2021): 1, ("truth", 2021): 1}, growth

# Job 2: bigrams survive, "dementia" is a domain stopword, each term counted once per paper.
top = J.job2_top_terms(docs, STOP, k=50)
rec = dict(top["recognition"])
assert rec.get("face recognition") == 1 and rec.get("familiar faces") == 1 and "dementia" not in rec, rec
assert dict(top["assistive"]).get("wearable camera") == 1

# Job 3: postings, and concept lookup as an OR over index terms.
index = J.job3_inverted_index(docs, STOP)
post = dict(index.collect())
assert post["face recognition"] == ["MED:1"] and post["wearable camera"] == ["MED:2"] and post["truth telling"] == ["MED:5"], post
concepts = J.concept_postings(index, {"recognition": ["face recognition", "familiar faces"], "glasses": ["smart glasses", "wearable camera"], "none": ["no such term"]})
assert concepts == {"recognition": ["MED:1"], "glasses": ["MED:2"], "none": []}, concepts
# AND across groups: "recognize" appears in MED:1 and MED:3, "family" only in MED:3.
anded = J.concept_postings(index, {"not recognizing family": [[["recognize", "recognise"], ["family", "relatives"]]],
                                   "either": [[["staff"]], [["glasses"]]]})
assert anded == {"not recognizing family": ["MED:3"], "either": ["MED:2", "MED:3"]}, anded
# "lying" alone (lying in bed) does not keep a truth tag; lying about the truth does.
assert not J.keeps_truth_tag({"title": "Patients lying in bed", "abstract": "Low mobility in hospital."})
assert J.keeps_ethics_tag({"title": "Privacy and cameras", "abstract": "Written informed consent was obtained. Residents worried about privacy."})
assert J.keeps_truth_tag({"title": "Lying to residents", "abstract": "Is lying ever ethical in care?"})

# Job 4: only MED:1 contains the query term, so it is the only scored paper.
ranked = J.job4_tfidf(docs, STOP, {"face recognition": 1.0}, k=5)
assert [d for d, _ in ranked] == ["MED:1"] and ranked[0][1] > 0, ranked

# Job 5: diagonal = papers per tag; off-diagonal = papers sharing both tags.
co = J.job5_cooccurrence(docs)
assert co[("assistive", "assistive")] == 2 and co[("assistive", "recognition")] == 1 and co[("recognition", "assistive")] == 1
assert co[("ethics", "truth")] == 1 and ("carehome", "assistive") not in co, co

# Job 6: only "Yes" rows of I4200 and I4800 count; the values pass through unchanged.
cms = [
    {"Geographical Location": "Pennsylvania", "MDS Item Question/Description": "I4200: Active Diagnoses - Neurological: Alzheimer's Disease", "MDS Item Response": "Yes", "Percent": "10.61", "Total Residents": "7060"},
    {"Geographical Location": "Pennsylvania", "MDS Item Question/Description": "I4200: Active Diagnoses - Neurological: Alzheimer's Disease", "MDS Item Response": "No", "Percent": "89.39", "Total Residents": "59500"},
    {"Geographical Location": "Pennsylvania", "MDS Item Question/Description": "I4800: Active Diagnoses - Neurological: Non-Alzheimer's Dementia", "MDS Item Response": "Yes", "Percent": "38.35", "Total Residents": "25526"},
    {"Geographical Location": "Pennsylvania", "MDS Item Question/Description": "A0310A: Federal OBRA Reason for Assessment", "MDS Item Response": "Yes", "Percent": "50.0", "Total Residents": "1"},
    {"Geographical Location": "Guam", "MDS Item Question/Description": "I4200: Active Diagnoses - Neurological: Alzheimer's Disease", "MDS Item Response": "Yes", "Percent": "*", "Total Residents": "*"},
]
got = J.job6_cms(sc.parallelize(cms))
assert got == {("Pennsylvania", "alzheimers"): (10.61, 7060, 1), ("Pennsylvania", "non_alzheimers_dementia"): (38.35, 25526, 1),
               ("Guam", "alzheimers"): (None, None, 1)}, got

# Job 7: a term only in 2019-25 papers rises; one only in 2011-18 papers falls.
era_docs = sc.parallelize([
    {"id": "E1", "year": 2012, "title": "Telecare pendants", "abstract": "Pendant alarms at home.", "tags": ["assistive"]},
    {"id": "E2", "year": 2014, "title": "Telecare pendants", "abstract": "Pendant alarms again.", "tags": ["assistive"]},
    {"id": "E3", "year": 2021, "title": "Chatbots for carers", "abstract": "Chatbots answered questions.", "tags": ["assistive"]},
    {"id": "E4", "year": 2023, "title": "Chatbots for carers", "abstract": "Chatbots again.", "tags": ["assistive"]},
])
em = J.job7_emerging(era_docs, STOP, min_docs=1, k=50)
assert em["era_sizes"] == {"early": 2, "late": 2}, em["era_sizes"]
rising, falling = [t for t, _, _ in em["rising"]], [t for t, _, _ in em["falling"]]
assert rising.index("chatbots") < rising.index("telecare") and falling.index("telecare") < falling.index("chatbots"), (rising, falling)

print("known answers: all 8 jobs pass")
s.stop()
