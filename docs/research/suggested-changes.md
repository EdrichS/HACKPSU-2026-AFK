# Suggested changes

> [!NOTE]
> Version 4, October 25, 2026. Four of the changes are now built, listed below; the team decides what to build next.
>
> This page was written against `main` at commit `0245eb3`; PR #17 (`514e3f3`) has since fixed the three [issues found in the code](#issues-found-in-the-code) and changed some of what the suggestions describe (captions can now come from Speechmatics in the cloud, an unknown voice is no longer attributed to the wearer, and the glasses HUD speaks only when asked, not on arrival). So re-check each suggestion against the current code before building it.

**Built since version 4:**
- **Change 1's quick win:** an arrival is introduced, *"Here's David, your grandson."*; asked "Who is this?", the answer is still *"That's …"*. Cue first, then the name, is not built.
- **Change 2:** when a name isn't registered, Nova says so and says who is here. Her first answer in a visit introduces her, and she never claims to be a person.
- **Change 6, first part:** Gemini gets only the lines of voices the app recognized, and so does Nova's view of the conversation on the glasses HUD. The pause mode, the recording cue and the local-only default are not built.
- **Change 9, the measuring:** each arrival is logged with how long naming took. Changing the two-sightings rule waits for those numbers.

**What changed since version 3:**
- A point a care-home worker made about helping people remember names, as a team member recalls it, rewrote change 1: cue first, then the name. It is designed against the code on `main`, but not built.
- A new section, [issues found in the code](#issues-found-in-the-code), records three problems, all since fixed in PR #17.

**How it's ranked:** by how strong the evidence is, how much it matters to a person with dementia, and how small it is to build.

**Where the evidence comes from:**
- [Care-worker accounts](care-worker-accounts.md): quotes matched word for word in their sources by script, except four that are labelled there and in [references](references.md).
- [Research at scale](research-at-scale.md): corpus counts, plus the verified deep read.
- [How big the problem is](problem-size.md).
- [Interview themes](interview-themes.md): a care-home worker's points, recalled by a team member, set against the evidence.

Every file and line named here refers to `main` at commit `0245eb3`, unless marked `514e3f3`. PR #17 has since changed several of the cited files, among them `backend/live_api.py`, `contract/live.py`, `live/cli.py` and the HUD, so some line numbers have moved. `live/README.md` and `DEPLOY.md` still say what they're cited for.

## The lesson from the closest prior art

Nametags is not the first system to name the people a person with memory loss meets. McCarron et al. 2019 ran a 6-month pilot trial of a phone that recognized enrolled faces and showed the person's name and relationship on a smartwatch. In their words, "the majority of participants did not find the SSA useful" (SSA is their name for the app), and it had no significant effect on social interaction or quality of life. The trial was small and possibly underpowered.

The reasons they found are a checklist for Nametags:

| Why it failed (McCarron 2019 interviews) | What Nametags does about it | Status |
|---|---|---|
| Enrolling was time-consuming and awkward; many only asked people they knew well, often people the person already remembered | Visitors enroll **themselves**, with consent (`/visitor`) | Built. Make the invite easy: item 8 |
| It only worked in certain lighting | A voice match counts at once (`live/presence.py:69`); the camera names a face after two sightings and breaks ties between close voices (`live/voices.py:58–62`) | Built. Explain it: item 3 |
| Too slow: "by the time the SSA recognized the face, her husband had already asked her who the person was" | A voice match counts at once; a face needs two sightings within 3 s | Built. Measure it: item 9 |
| It couldn't tell her son from her son-in-law, though they otherwise looked little alike | Faces too close to call get no name (the margin rule in `db/match.py`), and whoever speaks is named by voice (`live/presence.py:69`) | Built. Explain it: item 3 |
| A small screen to read, a photo to take (Fardoun 2017, smartwatch and cloud) | Spoken announcement, hands-free camera | Built, but untested with users |

## What the care-home conversation adds

These are points a care-home worker made, recalled by a team member; the conversation's audio wasn't captured. They are paraphrased here, and [interview themes](interview-themes.md) sets each one against the evidence.

- **Connection is the point.** The worker put affection and human connection first; recognizing someone is only the way in. This raises the priority of **change 1**: an introduction keeps the warm moment, while a correction can spoil it. It also supports the upbeat context card.
- **Fit by type and stage.** The worker pointed out that dementia has many types and stages, so the project should find the group it suits best. The literature gives the same answer: mild Alzheimer's (see [who it fits](#who-it-fits-say-it-plainly)). Say so plainly.
- **Help them remember; don't just tell.** In the worker's view, telling a person who someone is can work against what they need; supporting their own recall is better. This rewrote **change 1**.
- **Why, what, how.** The [evidence summary](README.md) now opens with them.
- **Claims to leave out.** Two aims came up that this study can't support: slowing or preventing the move into the most advanced stages, and standing in for medication. The study found nothing for either, and the closest prior art found no significant effect even on social interaction. A claim to prevent or treat a disease is also the kind that brings medical-device rules into play.
  - **Say instead:** *"a non-drug support for the moments that matter, alongside medical care, not instead of it."*
  - **Backing for that:** *Scales et al. 2018:* "Nonpharmacological practices are person-centered…"
  - **Where to check:** the README and any public description of Nametags.

## Build first (small)

### 1. Cue first, then the name (designed, not built)

- **Now:** on arrival, `That's {name}, your {relationship}.` (`contract/live.py:137–139`).
- **What the worker advised** (recalled by a team member): help the person recall who someone is, rather than telling them.
- **Evidence:** details and caveats are in [interview themes, theme 5](interview-themes.md#5-help-them-remember-dont-just-tell).
  - **For recall:**
    - *Dunn & Clare 2007:* "Reducing errors did not produce any benefits."
    - *Clare et al. 2002:* "Gains were largely maintained 6 months later, in the absence of practice."
  - **The guardrail:**
    - *Yamaguchi et al. 2010:* learning should be errorless "to ensure a pleasant atmosphere and to maintain a patient's dignity".
    - *Dementia UK:* "Try not to correct the person if they get your name wrong…"
  - **Keep the name and relationship in the end:**
    - *Dementia UK:* "introduce yourself and explain the connection between you".
    - *Luzzi et al. 2017:* people with Alzheimer's "were significantly impaired in the naming tests, but showed preserved recognition".
- **What the wearer would experience:**
  1. The glasses cue without the name: *"Your grandson is here."*
  2. For about 12 seconds the name stays off the glasses' tags, info panel and captions, and they listen.
  3. If the wearer says the name, they get warm praise: *"Yes, that's David!"*
  4. If not, or if the wearer asks ("Who is this?" or Space), the name comes gently: *"It's David, your grandson."* Never "No".
  5. Everything else stays: once per arrival, silence when unsure, and the unknown-face line.
- **Decisions so far:** if built, it is **off by default** (opt-in), and **the glasses HUD comes first**. The desktop `python -m live` stays as it is.
- **How it would plug in** (checked against `main` 0245eb3 by three code explorations and a design review):
  - **A new shared module, `live/recall.py`.** A small "recall coach" with a testable clock: it opens a window, hears the name, and gives the gentle line when time runs out or the wearer asks. Plus three sentences next to `who_text()` in `contract/live.py`.
  - **The server, `backend/live_api.py`:**
    - send the cue as the arrival text (:115 face, :157 voice);
    - check the wearer's transcribed lines after the caption (:166);
    - close the window on "Who is this?" (:178–179);
    - check deadlines after each message;
    - mark held-back people with `recall_pending` (set in `card()`, :83–98);
    - while the name is held back, use the **relationship** as the caption speaker, because today it is the name (:159).
  - **The HUD:** leave out the name tag (`FaceTags.tsx:64–68`) and show nothing in `InfoPanel.tsx` while `recall_pending` is set. Speech needs no change.
  - **The setting:** `NAMETAGS_RECALL_FIRST` (default 0) and `NAMETAGS_RECALL_WINDOW` (default 12), read at startup into `app.state`. Pin it to 0 in `tests/conftest.py`, so a local `.env` can't break `test_live_api.py:58`.
  - **Left alone:** `who_text()`, `Presence.saw()`, the mock and the schema. So **no existing test changes**.
- **Known limits, to check in testing:**
  - **Short replies:** a bare *David!* can fall under the 0.8 s speech minimum (`live_api.py:143`). Test with a longer reply, such as *Oh, it's David!*
  - **False recall:** an unenrolled visitor saying the name counts as the wearer.
  - **Late replies:** audio arrived in 3 s chunks, so a reply could land about 6 s late. Hence 12 s. PR #17 cut the chunks to about 1 s, so replies now arrive sooner.
  - **Transcription off:** recall can't succeed, so the mode falls back to the gentle line.
- **Untested:** the evidence comes from structured training in early-stage dementia, not from a live device.
- **Size:** medium (the server, the HUD and tests).
- **Quick win for today's mode, small:** change `That's…` to *"Here's David, your grandson."*, which reads as an introduction, not a correction (Alzheimer's Association: "Avoid explanations that sound like scolding").

### 2. Nova: answer gracefully when she mishears, and say what she is, once

- **Now:** "Never guess or invent a fact … Never mention being an AI unless asked." (`live/nova.py:36–39`, the system prompt)
- **Evidence on mishearing:**
  - *Stara et al. 2021,* on the conversational agent Anne, used by people with early dementia: "Some of them clearly discussed how technical problems related to speech recognition had a negative impact on intention to use, adaptiveness, usefulness, and trust." Separately, the users' ratings of usefulness and trust fell over the 4 weeks.
  - *Ruggiano et al. 2021:* commercial dementia voice skills were hard to start when voice recognition didn't accept the evaluators' pronunciation or demanded a specific command. Also, "most apps had limitations in their programmed content, which created challenges when evaluators did not use specific commands."
- **Evidence on honesty, which is mixed:**
  - *Day et al. 2011:* people with dementia found carers' lies acceptable when told in their best interest. That decision was "influenced by factors such as the person with dementia's awareness of the lie, and the carer's motivation for lying."
  - *Koh et al. 2023:* one care professional wanted a robot introduced "that it is a robot" to avoid "further distress down the line"; another went along with residents who believed the robot cat was real.
- **Change:**
  1. When a name in the question doesn't match anyone registered, Nova says so, then says who is here. That gives an answer instead of a dead end. A one-line prompt addition.
  2. The first time she speaks in a visit, she introduces herself: *I'm Nova, the helper in your glasses.* She never claims to be a person. This costs nothing, and it addresses the awareness that Day et al. found matters.
- **Size:** small. Prompt text, plus a first-use flag per visit.

### 3. Explain why voice comes first, and the margin rule (no code)

- **Evidence:**
  - *Verbeek et al. 2020:* "Mister J. did not recognize his son as they had not seen each other for 10 weeks… He was crying and could not understand how he could forget about his son."
  - *Bernardi et al. 2024:* families lower the mask "to make themselves recognizable".
  - *Kaelen et al. 2021:* "many residents did not recognize the staff anymore or could no longer engage in a conversation due to hearing problems." The residents may not all have had dementia. The HUD's captions speak to the second half.
  - *McCarron 2019:* the app worked only in some lighting, was too slow, and confused a son with a son-in-law.
- **Key point:** *When the face fails (masks, time apart, bad light, two relatives a camera confuses), the voice still names the person, and when Nametags isn't sure, it says nothing rather than a wrong name.* The evidence for voice over face is indirect: no study compared them.

### 4. Keep the "Who is this?" button front and center (no code)

- **Now:** the HUD button, with the Space key (`frontend/src/hud/Controls.tsx:16–30`).
- **Evidence:** *Edwards et al. 2021:* care-home smart speakers couldn't understand "certain residents because of speech difficulties".
- **Key point:** Nova is for people who can still ask; the button is for people who can't.

## Next (small to medium)

### 5. Let the family choose, per person, how arrivals are announced

- **Evidence:**
  - *SCIE:* "Mrs B no longer recognises her husband, and sometimes becomes very frightened because she thinks he is an intruder…"
  - *Mental Health Foundation:* family "believed to be an imposter".
  - *Cohen-Mansfield et al. 2014:* "The most effective approaches may be those tailored to the individual."
  - *Nagaratnam et al. 2003:* 35% of 116 people with dementia had misidentification, closely related to accusatory behavior, though age, stage and other factors confounded that link.
- **Change:** a per-person setting:
  - announce on arrival;
  - only when asked;
  - never.

  Plus optional custom wording, such as *Maria, your nurse*.
- **Where:** the enrollment flows (`frontend/src/flows/`), a field on `people`, and the announce decision at `live/presence.py:73–75`.
- **Size:** medium.

### 6. Privacy by design for a camera worn among other people

- **Now:**
  - an unknown voice is labelled unknown, not the wearer (`backend/live_api.py` and `live/cli.py` at `514e3f3`), but its lines still go to Gemini with the visit transcript;
  - whole-visit transcripts go to Gemini (`live/README.md`, section "The visit and Gemini"), and the live view also saves each visit's transcript, unknown voices included, to a file in `NAMETAGS_DATA/visits/` (`backend/live_api.py` at `514e3f3`);
  - Nova's questions go to Anthropic;
  - with `SPEECHMATICS_API_KEY` set, the HUD's audio is streamed to Speechmatics for captions, and `NAMETAGS_CAPTIONS=local` keeps captions on the machine (`backend/cloud_captions.py` at `514e3f3`);
  - `DEPLOY.md` puts it all on a server.
- **Evidence:**
  - *Mishra et al. 2023,* a dementia unit: "Due to privacy concerns, the cameras were not installed in the bedrooms and washrooms of participating residents, and the audio was turned off." Staff, and the residents' substitute decision-makers, gave written consent.
  - *Emilsson et al. 2023,* night staff: "Some felt uncomfortable that we should maybe be on film, did someone sit and watch us?"
  - *Rönning et al. 2026:* residents "were likely to forget" the monitoring they'd been told about, so a one-time notice isn't enough.
  - *Edwards et al. 2021:* "15 (43%) belonged to a care provider whose IT specialist raised concerns about data protection". These were among the 35 care homes that left the device unused.
- **Change:**
  1. **Before the Gemini call, keep only lines from consented, enrolled voices.** Unknown voices are no longer attributed to the wearer, but their lines still reach Gemini. *Trade-off:* the wearer's own unmatched lines are lost too, since they are now labelled unknown.
  2. **A pause mode,** so nothing is seen or heard in bedrooms and bathrooms.
  3. **A visible recording cue.**
  4. **A one-page data-flow sheet,** plus a local-only mode, captions included, as the care-home default. `--no-nova` and `--no-summary` already exist (`live/cli.py:60–61`).
- **Size:** (1) small to medium; (2) small (a button that stops capture); (3) depends on the hardware; (4) small.

### 7. Enroll care staff through the same consent flow

- **Evidence:**
  - *Kaelen 2021* and *Ariander 2024:* residents stopped recognizing **staff** in masks and protective equipment.
  - *Kemp 2025:* residents took some staff for relatives. This comes from the paper's full text, which an agent read but the check script couldn't reach (see [references](references.md#care-worker-accounts)).
- **Change:** invite key staff to enroll through `/visitor` with their role. Pair this with item 5 for residents whose beliefs about staff help their care.
- **Size:** small.

### 8. Make enrollment an ongoing habit, not a one-off

- **Evidence:**
  - *Sriram et al. 2019,* a review of 56 publications: assistive technology at home "was often wrongly seen as a one-off event, rather than an ongoing process".
  - *McCarron 2019:* enrolling was time-consuming and awkward, so many only asked people they knew well, often people the person already remembered.
- **Change:**
  - a share link that a family sends visitors **before** the visit;
  - a nudge after some months to refresh photos and voice, as faces and voices change.
- **Size:** small, because the link is just the `/visitor` route.

### 9. Measure the time to name someone before tuning it

- **Evidence:** *McCarron 2019:* "She said that by the time the SSA recognized the face, her husband had already asked her who the person was."
- **Change:** log the seconds from first sighting or first word to the announcement, in testing. Only then consider announcing on a single, very strong face match (well under the 0.6 cutoff) instead of two sightings (`live/presence.py:33`). **Never** trade the design's never-a-wrong-name rule for speed.
- **Size:** small to measure, small to change.

## Who it fits (say it plainly)

- **Mild Alzheimer's is the best fit; moderate is untested.**
  - *Luzzi 2017:* recognition preserved, naming impaired.
  - *Kurth et al. 2015:* recognition of familiar faces was preserved in mild Alzheimer's but "in moderate AD, both self and familiar face recognition were affected".
  - *Chandra et al. 2017* (frontotemporal dementia): 12 of 46 patients couldn't recognize a spouse or relative's face. The authors suggest, without testing it, that in frontotemporal dementia naming or voice doesn't help the way it does in Alzheimer's.
- **So:** Nametags helps most where the person still knows people but can't find the name. For later stages, the family's per-person settings (item 5) matter more.

## The research landscape (Spark analysis of 5,804 abstracts)

- **The field is growing fast.** Dementia technology papers went from 24 to 358 a year between 2010 and 2025 (×14.9); all dementia research grew ×2.6.
- **The gap.** Of 692 abstracts matching the recognition query:
  - **11** also match the assistive-technology query;
  - **6** match the ethics-of-technology query;
  - **0** match the care-home-staff interview query.

  These are overlaps, not topics: only one of the 6, McCarron 2019, is about technology that recognizes people.
- **Nametags' newest parts barely show up:**
  - **3** abstracts match our smart-glasses terms, and one of them is about audio glasses;
  - **10** match wearable cameras;
  - **6** match privacy with cameras and other people, though none uses the word bystander.
- **A thin evidence base:** a 2026 scoping review of camera-based assistive technology found 25 studies, of which only one focused on face recognition for Alzheimer's (Caute et al. 2026).

## Issues found in the code

Found on `main` at `0245eb3`. The lines cited for the fixes are at `514e3f3`.

1. **Nova's answers were never spoken on the glasses HUD.** Fixed in PR #17.
   - **The problem:** the server sent Nova's `answer` message, but the React HUD had no case for it.
   - **The fix:** the HUD now speaks her answers (`frontend/src/hud/useLiveSession.ts:181–182`).
2. **The HUD frontend didn't build on a Mac.** Fixed in PR #17.
   - **The problem:** macOS file names ignore case by default, so `captions.ts` (the caption state) and `Captions.tsx` (the caption bar) clashed, and `npm run typecheck` and `npm run build` stopped with 4 type errors.
   - **The fix:** `captions.ts` was renamed `captionLines.ts`. Measured on macOS at `514e3f3`, the frontend now type-checks and builds: both commands exit 0.
3. **Captions always looked unfinished.** Fixed in PR #17.
   - **The problem:** the server sent whole utterances with no `final` field, so every caption showed a blinking cursor.
   - **The fix:** captions now carry `final` (`contract/live.py:98`), and a missing one counts as finished (`frontend/src/hud/captionLines.ts:42–44`).
