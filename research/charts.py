"""Draw the study's four charts from derived/ as SVGs for docs/research/charts/, plus PNG previews
for a quick look in research/.previews/ (git-ignored).

The SVGs have an opaque background, so they read the same in GitHub's light and dark themes, and
no timestamp, so drawing them again from the same files gives byte-identical output. From the
repository root:

    uv --directory research run python charts.py

Two optional arguments replace the SVG and preview folders.

Palette: the dataviz reference instance, light mode (blue #2a78d6, orange #eb6834), validated with
validate_palette.js on the chart surface #fcfcfb. One axis per chart, recessive solid gridlines,
direct labels, a source line under every chart.
"""
import csv
import json
import sys
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("svg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent
D = ROOT / "derived"
SVG_DIR = ROOT.parent / "docs" / "research" / "charts"
PREVIEW_DIR = ROOT / ".previews"
SURFACE, INK, INK2, MUTED, GRID, BASE = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE = "#2a78d6", "#eb6834"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "sans-serif", "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 10, "text.color": INK, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": INK2,
    "axes.edgecolor": BASE, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": False, "grid.color": GRID, "grid.linewidth": 0.6, "grid.linestyle": "-",
    "svg.fonttype": "none", "svg.hashsalt": "nametags-study",
})
SOURCE_EPMC = "Source: Europe PMC titles and abstracts, pulled Oct 25, 2026; deduplicated and counted with Spark."


def layout(fig, left, right, top_in=0.95, bottom_in=1.0):
    """Margins in inches, so the header and source block are the same size on every chart."""
    h = fig.get_figheight()
    fig.subplots_adjust(left=left, right=right, top=1 - top_in / h, bottom=bottom_in / h)


def finish(fig, ax, title, subtitle, source, name, out, preview):
    h = fig.get_figheight()
    fig.suptitle(title, x=0.01, y=1 - 0.10 / h, ha="left", va="top", fontsize=12.5, fontweight="bold", color=INK)
    # break_on_hyphens=False keeps file names such as research-at-scale.md on one line.
    fig.text(0.01, 1 - 0.38 / h, textwrap.fill(subtitle, 100, break_on_hyphens=False), ha="left", va="top", fontsize=9.3, color=INK2)
    fig.text(0.01, 0.06 / h, textwrap.fill(source, 125, break_on_hyphens=False), ha="left", va="bottom", fontsize=7.6, color=MUTED)
    fig.savefig(out / f"{name}.svg", metadata={"Date": None})  # no timestamp: a redraw is byte-identical
    fig.savefig(preview / f"{name}.png", format="png", dpi=110)
    plt.close(fig)


def growth(out, preview):
    rows = list(csv.DictReader(open(D / "growth.csv")))
    assistive = {int(r["year"]): int(r["papers"]) for r in rows if r["theme"] == "assistive"}
    total = {int(r["year"]): int(r["all_dementia_papers"]) for r in rows if r["all_dementia_papers"]}
    years = list(range(2005, 2026))
    a = [assistive.get(y, 0) / assistive[2010] for y in years]
    t = [total[y] / total[2010] for y in years]
    fig, ax = plt.subplots(figsize=(7.2, 4.3))
    layout(fig, left=0.08, right=0.74)
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    ax.plot(years, a, color=BLUE, lw=1.8)
    ax.plot(years, t, color=ORANGE, lw=1.8)
    ax.scatter([2025], [a[-1]], s=22, color=BLUE, zorder=3, edgecolors=SURFACE, linewidths=1.2)
    ax.scatter([2025], [t[-1]], s=22, color=ORANGE, zorder=3, edgecolors=SURFACE, linewidths=1.2)
    ax.text(2025.4, a[-1], f"Dementia technology\n×{a[-1]:.1f}: {assistive[2010]} to {assistive[2025]} papers", va="center", fontsize=8.6, color=INK)
    ax.text(2025.4, t[-1], f"All dementia research\n×{t[-1]:.1f}: {total[2010]:,} to {total[2025]:,}", va="center", fontsize=8.6, color=INK)
    ax.axhline(1, color=BASE, lw=0.8)
    ax.set_xlim(2005, 2025)
    ax.set_ylim(0, max(a) * 1.08)
    ax.set_xticks([2005, 2010, 2015, 2020, 2025])
    ax.set_ylabel("Papers per year, 2010 = 1")
    finish(fig, ax, f"Dementia technology research grew {a[-1]:.1f}× since 2010; the whole field grew {t[-1]:.1f}×",
           "Papers on assistive technology for dementia, against all dementia papers, each indexed to its own 2010 count.",
           SOURCE_EPMC + " The assistive query is in research/pull_corpus.py.", "growth-index", out, preview)


def gap(out, preview):
    co = json.load(open(D / "cooccurrence.json"))
    manifest = json.load(open(ROOT / "raw" / "manifest.json"))
    assert co["recognition"]["assistive"] == manifest["recognition_and_assistive_hit_count"]
    assert co["recognition"]["ethics"] == manifest["recognition_and_ethics_hit_count"]
    n = co["recognition"]["recognition"]
    items = [("…also match the assistive-technology query", co["recognition"]["assistive"]),
             ("…also match the ethics-of-technology query", co["recognition"]["ethics"]),
             ("…also match the truth-telling query", co["recognition"]["truth"]),
             ("…also match the care-home-staff interview query", co["recognition"]["carehome"])]
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    layout(fig, left=0.47, right=0.95, top_in=1.0)
    ys = list(range(len(items)))[::-1]
    vals = [v for _, v in items]
    ax.barh(ys, vals, height=0.55, color=BLUE)
    for y, v in zip(ys, vals):
        ax.text(v + max(vals) * 0.015 + 0.2, y, f"{v}", va="center", fontsize=9.5, color=INK)
    ax.set_yticks(ys, [label for label, _ in items], fontsize=9.5)
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(0, max(vals) * 1.15 + 1)
    ax.set_xlabel("Abstracts")
    finish(fig, ax, f"Of {n} abstracts matching the recognition query…",
           "Recognition query: faces, voices, familiar people, prosopagnosia, misidentification, Capgras. These are query overlaps, not topics.",
           SOURCE_EPMC + f" Counts are abstracts matching both queries; Europe PMC's own intersection counts agree "
           f"({manifest['recognition_and_assistive_hit_count']} and {manifest['recognition_and_ethics_hit_count']}).",
           "recognition-gap", out, preview)


def concepts(out, preview):
    c = json.load(open(D / "concepts.json"))
    data = c["concepts"]
    total = json.load(open(D / "job0_counts.json"))["unique_after_filter"]
    skip = {"not recognizing family"}  # doc-level AND match is too noisy to chart (see research-at-scale.md)
    focus = {"smart glasses", "wearable camera", "recognizing voices", "bystanders / others on camera",
             "voice assistant / conversational AI", "name badges / tags", "recognizing faces"}
    items = sorted(((k, v["papers"]) for k, v in data.items() if k not in skip), key=lambda kv: kv[1])
    fig, ax = plt.subplots(figsize=(7.2, 6.0))
    layout(fig, left=0.36, right=0.95, top_in=1.05)
    ys = range(len(items))
    colors = [BLUE if k in focus else BASE for k, _ in items]
    ax.barh(list(ys), [v for _, v in items], height=0.62, color=colors)
    top = max(v for _, v in items)
    for y, (k, v) in zip(ys, items):
        ax.text(v + top * 0.012, y, f"{v}", va="center", fontsize=8.8, color=INK if k in focus else INK2)
    ax.set_yticks(list(ys), [k for k, _ in items], fontsize=9)
    for lab in ax.get_yticklabels():
        lab.set_color(INK if lab.get_text() in focus else INK2)
        lab.set_fontweight("bold" if lab.get_text() in focus else "normal")
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(0, top * 1.12)
    ax.set_xlabel("Abstracts matching the concept's terms (inverted-index lookup)")
    finish(fig, ax, f"How many abstracts match each Nametags concept",
           f"Blue: Nametags' own parts. Grey: context. Out of {total:,} abstracts. Matches, not topics: see research-at-scale.md.",
           SOURCE_EPMC + " Concept terms and AND rules are in research/jobs/run_corpus.py.", "concepts", out, preview)


def states(out, preview):
    rows = [r for r in csv.DictReader(open(D / "cms_dementia_by_state.csv"))
            if r["location"] != "National Total" and r["non_alzheimers_dementia_pct"]]
    nat = next(r for r in csv.DictReader(open(D / "cms_dementia_by_state.csv")) if r["location"] == "National Total")
    rows.sort(key=lambda r: float(r["non_alzheimers_dementia_pct"]))
    fig, ax = plt.subplots(figsize=(7.2, 10.6))
    layout(fig, left=0.24, right=0.95, top_in=1.25)
    ys = range(len(rows))
    nad = [float(r["non_alzheimers_dementia_pct"]) for r in rows]
    ad = [float(r["alzheimers_pct"]) for r in rows]
    ax.xaxis.grid(True)
    ax.set_axisbelow(True)
    ax.axvline(float(nat["non_alzheimers_dementia_pct"]), color=BLUE, lw=0.8, alpha=0.5)
    ax.axvline(float(nat["alzheimers_pct"]), color=ORANGE, lw=0.8, alpha=0.5)
    ax.scatter(nad, list(ys), s=30, color=BLUE, zorder=3, edgecolors=SURFACE, linewidths=1.0, label="Non-Alzheimer's dementia (I4800)")
    ax.scatter(ad, list(ys), s=30, color=ORANGE, zorder=3, edgecolors=SURFACE, linewidths=1.0, label="Alzheimer's disease (I4200)")
    ax.set_yticks(list(ys), [r["location"] for r in rows], fontsize=8)
    for lab in ax.get_yticklabels():
        if lab.get_text() == "Pennsylvania":
            lab.set_fontweight("bold")
            lab.set_color(INK)
    pa = next(i for i, r in enumerate(rows) if r["location"] == "Pennsylvania")
    ax.text(float(rows[pa]["non_alzheimers_dementia_pct"]) + 1.0, pa, f"PA {rows[pa]['non_alzheimers_dementia_pct']}%", va="center", fontsize=8.5, color=INK)
    ax.text(float(nat["non_alzheimers_dementia_pct"]) + 0.4, -1.3, f"US {nat['non_alzheimers_dementia_pct']}%", fontsize=8, color=INK2, va="center")
    ax.text(float(nat["alzheimers_pct"]) + 0.4, -1.3, f"US {nat['alzheimers_pct']}%", fontsize=8, color=INK2, va="center")
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(0, 55)
    ax.set_ylim(-2, len(rows))
    ax.set_xlabel("Share of nursing-home residents with an active diagnosis (%)")
    ax.legend(loc="lower left", bbox_to_anchor=(-0.02, 1.0), ncol=2, frameon=False, fontsize=8.5, handletextpad=0.3)
    finish(fig, ax, "Dementia diagnoses in US nursing homes, by state",
           "Q3 2026. The two diagnoses can overlap, so they are never added. Puerto Rico and the Virgin Islands are suppressed by CMS.",
           "Source: CMS Minimum Data Set Frequency, state level, Q3 2026 (MDS_Frequency_Q3_2026.csv); counted with Spark.",
           "nursing-homes-by-state", out, preview)


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else SVG_DIR
    preview = Path(sys.argv[2]) if len(sys.argv) > 2 else PREVIEW_DIR
    out.mkdir(parents=True, exist_ok=True)
    preview.mkdir(parents=True, exist_ok=True)
    for f in (growth, gap, concepts, states):
        f(out, preview)
    print("charts written:", sorted(p.name for p in out.glob("*.svg")))
