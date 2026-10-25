# Evidence summary

A small data-science study behind Nametags, framed with CSCI 436 (Big Data Management and Analytics). Nametags is a memory aid for people living with dementia: it recognizes people by face and voice, says who they are, and has a voice assistant, Nova. It is designed for glasses, and today runs as a web app with a glasses-style live view, and as a laptop program.

**How everything here was checked:**
- **Numbers:** each comes from a fetched source sentence, or from our own Spark run over public data.
- **Quotes:** each was matched word for word in its source by script.
- **The care-home conversation:** a care-home worker's points appear only as anonymized paraphrase, recalled by a team member. Nothing from that conversation is quoted.

**The details:**
- [How big the problem is](problem-size.md)
- [Care-worker accounts](care-worker-accounts.md)
- [Research at scale](research-at-scale.md)
- [Suggested changes](suggested-changes.md)
- [Interview themes](interview-themes.md)
- [How the study ran: the pipeline](pipeline.md)
- [References](references.md)

## Why, what, how

- **Why.** Recognizing someone you love is a moment of joy, and failing to is distressing for everyone in the room. A care-home worker we spoke with put affection and human connection at the center of dementia care ([interview themes](interview-themes.md)). Millions of people live with this: see the numbers below.
- **What.** Designed for glasses, Nametags quietly tells a person with dementia who they're talking to. Today the laptop program says *"That's David, your grandson."* when someone arrives, and the live view says it when asked; the [suggested changes](suggested-changes.md) propose a gentler introduction. Nova, a voice assistant, answers questions such as who is here.
- **How.** Voice comes first, because faces fail with masks, time apart and poor light. It gives no name when unsure. Visitors enroll themselves, with consent. The live view shows captions.
- **For whom.** Best fit: **mild Alzheimer's**, people who still know their family but can't find the name.
- **What it isn't.** A treatment. Nametags doesn't slow dementia or replace medication. It is a non-drug, person-centered support that works alongside medical care. [Interview themes](interview-themes.md#4-what-nametags-does-not-claim) explains why that line matters.

## The problem

- **7.4 million** Americans 65 and older live with Alzheimer's dementia in 2026. Worldwide, **57 million** people were living with dementia in 2021. WHO: people with dementia "may not be able to recognize family members or friends."
- **12.7 million** family and other unpaid caregivers gave **19.6 billion hours** of care in 2025.
- **In US nursing homes, between 39% and 49% of residents have a dementia diagnosis.**
  - In Q3 2026, 477,804 residents (38.9%) had non-Alzheimer's dementia and 124,553 (10.1%) had Alzheimer's disease.
  - We counted this ourselves with Spark from the federal Minimum Data Set file, and it reconciles with the file's own national total.
  - The range is because one resident can have both.

More figures, each with the sentence it comes from: [how big the problem is](problem-size.md).

## What carers see

> "Mister J. did not recognize his son as they had not seen each other for 10 weeks… He was crying and could not understand how he could forget about his son."
>
> — a nursing-home team leader, Netherlands (Verbeek et al. 2020)

> "The masks created even more distance, as many residents did not recognize the staff anymore or could no longer engage in a conversation due to hearing problems."
>
> — Kaelen et al. 2021, eight Brussels nursing homes

> "Mrs B no longer recognises her husband, and sometimes becomes very frightened because she thinks he is an intruder."
>
> — Social Care Institute for Excellence: an illustrative safeguarding scenario, not a first-hand account

A care-home worker we spoke with made the same point from the other side: warmth from family means a great deal to the people they care for, and it is a good moment when someone is recognized, or a memory they knew they had lost comes back. These are the worker's points as a team member recalls them; the conversation's audio wasn't captured. See [interview themes](interview-themes.md).

## What the research says

![Line chart: papers on assistive technology for dementia per year, indexed to 2010, grew 14.9 times by 2025, against 2.6 times for all dementia papers](charts/growth-index.svg)

![Bar chart: of 692 abstracts matching the recognition query, 11 also match the assistive-technology query, 6 the ethics-of-technology query, and none the care-home-staff query](charts/recognition-gap.svg)

The bars in the second chart are overlaps between queries, not what each paper is about.
- **The 6 "ethics" matches** include a psilocybin review and an MRI de-identification tool. Only one of those 6, McCarron et al. 2019, is about technology that recognizes people.
- **The 11 assistive overlaps** include more prior art, such as Fardoun et al. 2017, below.

**The closest prior art was tested, and it fell short.** McCarron et al. 2019 ran a 6-month pilot trial with 48 people with memory loss. Their phone recognized enrolled faces and showed the person's name and relationship on a smartwatch, and "the majority of participants did not find the SSA useful." (SSA is the paper's name for the app.) Its failures are exactly what Nametags is built around:

| What went wrong then | What Nametags does |
|---|---|
| Enrolling was time-consuming and awkward; many only asked people they knew well, often people the person already remembered | Visitors enroll themselves, with consent |
| "Several participants reported that the SSA only worked in certain lighting." | A voice match names the person at once; the camera names a face after two sightings and breaks ties between close voices |
| "She said that by the time the SSA recognized the face, her husband had already asked her who the person was." | Voice first; on arrival the laptop program says the name once and the live view shows it; a "Who is this?" button |
| It couldn't tell her son from her son-in-law, though they otherwise looked little alike | Faces too close to call get no name, and whoever speaks is named by voice |
| A small screen to read and a photo to take (Fardoun et al. 2017) | A spoken introduction and a hands-free camera |

## How the evidence fits Nametags as built

| Part of Nametags | What the evidence says | Verdict |
|---|---|---|
| Name and relationship, spoken | Dementia UK's advice is to "introduce yourself and explain the connection between you". In Alzheimer's, people "were significantly impaired in the naming tests, but showed preserved recognition" (Luzzi et al. 2017). A care-home worker we spoke with advised helping people remember rather than telling them (recalled by a team member). Effort helped people with early dementia relearn names: "Reducing errors did not produce any benefits." (Dunn & Clare 2007) | **Supports, with a twist.** Cue recall first, then the name (change 1) |
| Voice-first recognition | Residents stopped recognizing masked or long-absent people (Verbeek 2020, Bernardi 2024, Kaelen 2021; Kaelen's residents may not all have had dementia), and a face-only app failed in poor lighting (McCarron 2019). No study compares voice with face directly | **Indirect support** |
| No name when unsure | A face-only app confused a son with a son-in-law (McCarron 2019) | **Supports** |
| "Who is this?" button | Care-home smart speakers couldn't understand "certain residents because of speech difficulties" (Edwards et al. 2021) | **Supports** |
| Nova, the voice assistant | Some users of a dementia assistant said speech-recognition errors hurt their intention to use it, its usefulness and their trust; separately, their ratings of usefulness and trust fell over 4 weeks (Stara et al. 2021). Honesty is contested: people with dementia accepted carers' well-meant lies, depending on "awareness of the lie" (Day et al. 2011) | **Challenges.** Handle mishearing; introduce herself once (change 2) |
| A camera and microphone worn among others | A dementia unit kept "cameras … not installed in the bedrooms and washrooms" and "the audio was turned off" (Mishra et al. 2023); some night staff felt uncomfortable at possibly being "on film" (Emilsson et al. 2023) | **Challenges.** Privacy by design (change 3) |
| Visitor consent at enrollment | In a dementia unit with cameras, staff and residents' substitute decision-makers gave written consent (Mishra et al. 2023); the paper doesn't say whether visitors did | **Precedent.** Visitors not covered |
| Server deployment and cloud calls | Data-protection objections kept a voice device unused in 15 of the 35 homes that weren't using it (Edwards et al. 2021) | **Challenges.** Default to the local mode in care homes |
| Who it fits | Recognition of familiar faces holds in mild Alzheimer's but is "affected" in moderate (Kurth et al. 2015); frontotemporal dementia differs (Chandra et al. 2017) | Best fit: **mild Alzheimer's**; moderate untested |

## What we'd change, from the evidence

These are the top three; the full ranked list is in [suggested changes](suggested-changes.md).
1. **Cue first, then the name.**
   - The flow: *"Your grandson is here."*, a few seconds to remember, then *"Yes, that's David!"*, or gently *"It's David, your grandson."*
   - It is designed against the code but not built: off by default, glasses first.
   - The quick win for today's behavior is *"Here's David, your grandson."* instead of *"That's David…"* (`contract/live.py:147`).
2. **Make Nova graceful.** When a name isn't recognized, she says who is here. She introduces herself once (*I'm Nova, the helper in your glasses*) and never claims to be a person (`live/nova.py:39`).
3. **Privacy by design.**
   - Only consented, enrolled voices go into the transcript sent to Gemini.
   - A pause mode for bedrooms and bathrooms.
   - Local-only mode, captions included, by default in care homes.

## Limits of this study

- **The interview:** its recording had no usable audio, so it appears only as a team member's recollection, paraphrased as themes.
- **COVID:** many staff accounts come from that period, when masks and visiting bans made non-recognition worse.
- **Abstracts:** 14 of the 20 papers read in depth were abstract-only. The corpus is Europe PMC titles and abstracts, searched with English terms.
- **Concept counts** match words anywhere in an abstract, not within one sentence. The remaining noise is documented in [research at scale](research-at-scale.md).
- **Misidentification rates** come from clinic samples.
- **No user test:** Nametags itself hasn't been tested with people with dementia.

## The big-data part (CSCI 436)

- **Data:** 6,816 Europe PMC abstracts, plus 133,920 rows of CMS nursing-home data.
- **Processing:** eight Spark jobs written as map, then shuffle, then reduce: word count as in Hadoop Lab 1, an inverted index as in Lecture 4, tf-idf, co-occurrence, and growth. Each was tested first on hand-made data with known answers.
- **What ran where:** PySpark 4.2.0 in local mode on one Apple M1 machine. These are MapReduce-shaped jobs on Spark; no Hadoop cluster and no Hadoop MapReduce job ran. The [pipeline](pipeline.md) maps every step.
- **Veracity, the fourth V:** four data-quality problems were found and fixed, all documented in [research at scale](research-at-scale.md):
  - "app" also matched APP, the amyloid precursor protein, and pulled in 3,456 lab-biology papers, such as mouse studies;
  - "lies" is also a verb;
  - ethics-approval boilerplate;
  - a national-total row hidden among the states.

  After the fixes, **5,804** papers remained.
