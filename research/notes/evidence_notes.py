"""Write two research pages from derived/: care-worker-accounts.md and problem-size.md.

Quotes are copied from the verified files, never retyped. A quote appears only if check_quotes.py
matched it word for word in its source; one it could not check is described in our words instead.
The headline figures in the prose are typed in, and each is checked against the verified sentence
it comes from. The Cohen-Mansfield figures are typed in without a check; research/README.md says why.
From the repository root:

    uv --directory research run python notes/evidence_notes.py
"""
import csv
import json
import re

from common import CMS_ROWS, CODE, DERIVED as D, generated_by, repo_text, table, tensions_list, write

check = {(c["file"], c["id"]): c["result"] for c in json.load(open(D / "quote_check.json"))}
MARK = {"pass": "✓ matched word for word in the source, by script.",
        "unreachable": "not checked by script: the source refuses scripted reads."}

GROUPS = [
    ("When residents stop recognizing people", {"non-recognition", "long separation", "masks/PPE", "family distress"}),
    ("Misidentification, and whether to correct it", {"misidentification", "going along/truth-telling"}),
    ("What helps", {"what helps"}),
    ("Technology in care homes: voices, cameras, privacy", {"technology", "bystander privacy"}),
]
# How to read a few of the accounts, in our words, from the agents' notes in derived/accounts_*.json.
CAVEATS = {
    "kaelen2021-masks-staff": "The passage doesn't say these residents had dementia, and the study's resident interviews "
                              "left out people with dementia, so read it as evidence about masks and recognizing staff.",
    "kemp2025-staff-as-relatives": "The paper isn't one-sided: it also reports correcting that helped some residents and "
                                   "harmed others.",
    "edwards2021-speech-difficulties": "Not specific to dementia: the homes were mostly care homes for older people, and "
                                       "the feedback came mostly from one person per home, usually the manager.",
    "edwards2021-data-protection": "Not specific to dementia, and the paper doesn't say whose data the IT specialist "
                                   "was concerned about.",
    "koh2023-introduce-as-robot": "A minority view: the authors' summary says few participants were concerned that "
                                  "residents taking the robots for real animals could be distressed by it.",
    "org-scie-1": "An illustrative scenario in safeguarding guidance for practitioners, not a first-hand account.",
}
# The source's own label is "Nurse, male, more 10": role, gender and years of experience.
SPEAKER = {"bernardi2024-lower-mask": "a male nurse with more than 10 years' experience"}
DROPPED_REWRITES = [("Dropped only to stay within the 2-4 additions, because org-dementiauk-1 gives",
                     "Dropped only to keep the list of organizations short: Dementia UK gives")]


def who(a: dict) -> str:
    if a.get("organization"):
        return a["organization"]
    names = [n.strip() for n in a["authors"].replace("et al.", "").split(",") if n.strip()]
    surnames = [n.rsplit(" ", 1)[0] for n in names]
    return surnames[0] if len(names) == 1 else " and ".join(surnames) if len(names) == 2 else f"{surnames[0]} et al."


def source(a: dict) -> str:
    link = f"https://doi.org/{a['doi']}" if a.get("doi") else a["url"]
    title = a["title"].replace("[", "(").replace("]", ")")
    venue = f" {a['venue']}." if a.get("venue") else ""
    return f"{who(a)} ({a.get('year') or 'n.d.'}). [{title}]({link}).{venue}"


def account(a: dict) -> str:
    result = check.get((a["_file"], a["id"]))
    assert result in MARK, (a["id"], result)
    head = (f"> {a['quote']}" if result == "pass" else
            "*Not quoted here: the source refuses scripted reads, so the quote's wording couldn't be checked word for "
            "word.*")
    lines = [head, "", f"- **Speaker:** {SPEAKER.get(a['id'], a.get('speaker'))}", f"- **Source:** {source(a)}"]
    if a.get("organization"):
        lines.append(f"- **Kind:** {a.get('kind')}")
    else:
        where = ", ".join(x for x in (a.get("setting"), a.get("country")) if x)
        lines.append(f"- **Setting:** {where}" + ("; during COVID" if a.get("covid_period") is True else ""))
    lines.append(f"- **For Nametags:** {repo_text(a.get('nametags_relevance'))}")
    if a["id"] in CAVEATS:
        lines.append(f"- **Read with care:** {CAVEATS[a['id']]}")
    lines.append(f"- **Check:** {MARK[result]}")
    return "\n".join(lines)


def dropped_reason(a: dict) -> str:
    reason = re.search(r"Dropped[^.]*\.", a.get("note", "")).group(0)
    for old, new in DROPPED_REWRITES:
        reason = reason.replace(old, new)
    return reason


def accounts() -> tuple[str, int, int]:
    items = []
    for f in ("accounts_peer.json", "accounts_org.json", "accounts_extra.json"):
        for a in json.load(open(D / f)):
            items.append({**a, "_file": f})
    kept = [a for a in items if a.get("status") == "kept"]
    dropped = [a for a in items if a.get("status") == "dropped"]
    assert set(CAVEATS) | set(SPEAKER) <= {a["id"] for a in kept}
    n_pass = sum(1 for a in kept if check.get((a["_file"], a["id"])) == "pass")
    n_blocked = sum(1 for a in kept if check.get((a["_file"], a["id"])) == "unreachable")
    assert n_pass + n_blocked == len(kept)
    n_extra = sum(1 for a in kept if a["_file"] == "accounts_extra.json")
    used, sections = set(), []
    for title, themes in GROUPS:
        sel = [a for a in kept if a["id"] not in used and themes & set(a.get("themes", []))]
        if sel:
            used |= {a["id"] for a in sel}
            sections.append(f"## {title}\n\n" + "\n\n".join(account(a) for a in sel))
    assert used == {a["id"] for a in kept}, "an account fits no section"
    gone = "\n".join(f"- **{who(a)} ({a.get('year')}), [{a['title']}]({a.get('url')}):** {dropped_reason(a)}"
                     for a in dropped)
    text = f"""# Care-worker accounts

What care-home, nursing-home and assisted-living staff report about residents who stop recognizing people, from
published studies, with guidance from dementia organizations. Part of the [evidence summary](README.md). The accounts
sit alongside the [interview themes](interview-themes.md): points a care-home worker made, recalled by a team member.

{generated_by("notes/evidence_notes.py")}

## How the accounts were gathered and checked

- **Gathered by:** two AI agents, one searching peer-reviewed studies in Europe PMC and one searching dementia
  organizations. Another {n_extra} quotes were added from abstracts.
- **Checked by:** a script that fetches each source and matches every quote word for word.
- **Result:** {len(kept)} accounts kept and {len(dropped)} dropped. {n_pass} quotes matched their source by script. The
  other {n_blocked} come from sources that refuse scripted reads, so they are described in our words, not quoted.
- **Details:** where each quote sits in its source, and how it was read, is in the `note` field of the account files in
  [`research/derived/`]({CODE}/derived/). The script's results are in
  [`quote_check.json`]({CODE}/derived/quote_check.json).

**Read these with three caveats:**
- **COVID:** many accounts come from the COVID period, when masks and visiting bans made non-recognition worse than
  usual.
- **Small numbers:** Cohen-Mansfield et al. (2014) report staff agreeing with a resident's misidentification delusion in
  60% of cases and arguing in 40%, but both rest on only 5 cases, and one case could get more than one reaction. Cite
  them with that base.
- **Organizations:** the guidance quotes are advice, not observations.

## The open tensions

Each account is read against five open tensions in Nametags' design; *open tension 1* below means the first.

{tensions_list()}

""" + "\n\n".join(sections) + f"""

## Dropped, and why

{gone}

## Gaps the search left open

- **What helps:** no peer-reviewed, open-access staff account was found that describes what actually helps when a
  resident doesn't recognize someone (introductions, name badges, photos, memory books). The organizations' guidance
  fills that gap with advice, not evidence.
- **Staff turnover:** nothing was found on staff turnover and recognition.
"""
    return text, len(kept), n_pass


def size() -> str:
    figs = {f["id"]: f for f in json.load(open(D / "figures.json"))}

    def fig(fid: str, *parts: str) -> dict:
        """A figure whose sentence passed the script check and contains what the page says it does."""
        assert check.get(("figures.json", fid)) == "pass", fid
        for p in parts:
            assert p in figs[fid]["sentence"], (fid, p)
        return figs[fid]

    fig("us_prevalence_2026", "7.4 million", "2026")
    fig("who_global", "57 million", "2021")
    who_rec = "may not be able to recognize family members or friends"
    fig("who_global_recognition", who_rec)
    fig("us_caregivers_2025", "12.7 million", "19.6 billion hours", "2025")
    fig("pa_caregivers", "Pennsylvania 472")
    fig("nchs_nursing_homes", "41.1%", "2022")
    fig("ff_nursing_homes", "46%")
    fig("us_caregivers_2025_per_caregiver", "1,543")
    fig("misid_mendez_1992", "25.4%")
    fig("misid_harciarek_2008", "15.8%")
    fig("capgras_pereira_2019", "6%")
    assert "12.734 million caregivers and 19.608 billion hours" in figs["us_caregivers_2025"]["note"]

    run = json.load(open(D / "run_summary.json"))
    nat = run["cms_national"]
    rows = list(csv.DictReader(open(D / "cms_dementia_by_state.csv")))
    national = next(r for r in rows if r["location"] == "National Total")
    states = [r for r in rows if r["location"] != "National Total" and r["non_alzheimers_dementia_pct"]]
    gap = max(int(national[f"{i}_residents"]) - sum(int(r[f"{i}_residents"]) for r in states)
              for i in ("alzheimers", "non_alzheimers_dementia"))
    suppressed = sorted({c.split(" (")[0] for c in run["cms_suppressed_cells"]})
    assert suppressed == ["Puerto Rico", "Virgin Islands"], suppressed  # named in the text below
    states.sort(key=lambda r: -float(r["non_alzheimers_dementia_pct"]))
    lo, hi = states[-1], states[0]
    pa = next(r for r in states if r["location"] == "Pennsylvania")
    pa_rank = states.index(pa) + 1
    nad, ad = nat["non_alzheimers_dementia"], nat["alzheimers"]

    rows_out = []
    for f in figs.values():
        res = check.get(("figures.json", f["id"]))
        sentence = f"“{f['sentence']}”" if res == "pass" else f"not quoted ({res})"
        src = f"[{f.get('locator') or 'source'}]({f['url']}), {f.get('edition_or_date') or ''}"
        rows_out.append((f["figure"], f["claim"], sentence, src, "✓" if res == "pass" else res))

    return f"""# How big the problem is

How many people live with dementia, how many people care for them, and how many US nursing-home residents have a
dementia diagnosis, with the source sentence behind every published figure. Part of the
[evidence summary](README.md).

{generated_by("notes/evidence_notes.py")}

**How the figures were checked:**
- **Published figures:** an AI agent fetched each source and recorded the exact sentence behind the figure. A script
  then fetched the source again and matched that sentence word for word (✓ below).
- **Nursing-home figures:** our own Spark count over the federal Minimum Data Set file, reconciled with the file's
  national row. The [research at scale](research-at-scale.md) page and the [pipeline map](pipeline.md) show how.

## Three numbers

1. **7.4 million** Americans 65 and older live with Alzheimer's dementia in 2026. Worldwide, **57 million** people were
   living with dementia in 2021. WHO's fact sheet says people with dementia "{who_rec}".
2. **12.7 million** family and other unpaid caregivers gave **19.6 billion hours** of care in 2025. Pennsylvania alone
   has 472,000.
3. **{nad['residents']:,} US nursing-home residents ({nad['pct']}%)** had an active non-Alzheimer's dementia diagnosis in
   Q3 2026, and **{ad['residents']:,} ({ad['pct']}%)** had Alzheimer's disease.
   - A resident can have both, so between {max(nad['pct'], ad['pct']):.0f}% and {nad['pct'] + ad['pct']:.0f}% had
     either.
   - That bracket agrees with NCHS's 41.1% (2022) and the Alzheimer's Association's 46%.
   - Pennsylvania: {pa['non_alzheimers_dementia_pct']}% and {pa['alzheimers_pct']}%.

## Published figures, with the sentence each comes from

{table(["Figure", "Claim", "Exact sentence", "Source", "Script check"], rows_out)}

**Notes on these figures:**
- **Not independent:** NCHS's 41.1% and the Alzheimer's Association's 46% both draw on the NCHS overview of long-term
  care, so cite them as two figures, not as two sources agreeing.
- **Clinic samples:** the misidentification rates (25.4%, 15.8%, Capgras 6%) come from clinic samples of people already
  diagnosed, not from the population.
- **Rounding:** the report prints 1,543 hours per caregiver. Dividing the unrounded totals in its endnotes (19.608
  billion hours ÷ 12.734 million caregivers) gives about 1,540. Cite the printed figure.

## Nursing homes, by state (our own Spark count)

![Dot plot of the share of nursing-home residents with each dementia diagnosis, by state](charts/nursing-homes-by-state.svg)

- **Data:** CMS Minimum Data Set Frequency, state level, Q3 2026: {CMS_ROWS:,} rows, public, with no login. We use items
  I4200 (Alzheimer's disease) and I4800 (non-Alzheimer's dementia), `Yes` responses only.
- **No double count:** the file includes a `National Total` row among the states. Spark job 6 checks that the states add
  up to it, and they do, within {gap} resident{'' if gap == 1 else 's'}.
- **Suppressed:** CMS suppresses the figures for Puerto Rico and the Virgin Islands, shown as `*` in its file. They are
  kept as missing, not dropped.
- **Range:** from {lo['location']} ({lo['non_alzheimers_dementia_pct']}%) to {hi['location']}
  ({hi['non_alzheimers_dementia_pct']}%) for non-Alzheimer's dementia. Pennsylvania ranks {pa_rank} of {len(states)}.
"""


if __name__ == "__main__":
    acc, n, n_pass = accounts()
    print("wrote", write("care-worker-accounts.md", acc))
    print("wrote", write("problem-size.md", size()))
    print(f"accounts kept={n}, matched by script={n_pass}")
