# Interview themes

> [!NOTE]
> Points a care-home worker made, recalled by a team member; the call's audio wasn't captured.

**About this page:**
- **The conversation:** a team member spoke with a care-home worker about Nametags. The recording turned out to have no usable audio and no captions, so there is no transcript.
- **What's here:** five themes from the team member's recollection, paraphrased in our own words. None of it is a quote, either from the worker or from the team member's notes.
- **Privacy:** the worker agreed to anonymized use. Nothing here names the worker, their workplace or any resident.
- **The evidence:** every quote from a published source was matched word for word in that source by script, and the sources are listed in [references](references.md). Lines in italics are Nametags' own wording, current or proposed.

## 1. Affection and human connection are the point

**The point, in our words:** for people living with dementia, warmth from family, and from their sons especially, matters enormously. Recognizing a visitor, or recovering a memory they knew had slipped away, is a good moment. Affection and human connection are what matter most, to carers and to everyone who works with people with dementia.

**The evidence agrees, from the other side: not being recognized hurts.**
- *Verbeek et al. 2020,* a nursing-home team leader: "Mister J. did not recognize his son as they had not seen each other for 10 weeks… He was crying and could not understand how he could forget about his son."
- *Mental Health Foundation:* "Often most heart-breaking for close family members or friends are situations where they are no longer recognised or are even believed to be an imposter."

**For Nametags:** the product's job is the moment of recognition and the warmth that follows, not the recognition itself.
- **The announcement.** This supports [change 1](suggested-changes.md#1-cue-first-then-the-name-designed-not-built): introduce, don't correct. A correction can spoil the very moment the worker described.
- **The context card.** It is upbeat and gives things to ask about (`backend/gemini.py`). It serves the same goal, giving the visitor and the person something to share.

## 2. Different types and stages: find the best fit

**The point, in our words:** dementia takes many forms and moves through stages, so the project should work out which group it can help most.

**The literature points to the same answer.**
- *Luzzi et al. 2017:* "AD patients were significantly impaired in the naming tests, but showed preserved recognition, whereas SD patients were profoundly impaired both in naming and in recognition of famous faces and voices."
- *Kurth et al. 2015:* "However, in moderate AD, both self and familiar face recognition were affected."
- *Chandra et al. 2017* (frontotemporal dementia): "Prosopagnosia in Alzheimer's disease is of visuospatial nature and hence can recognize the individual when named or spoken to, but in FTD, it is multimodal and hence cannot be recognized by any mode." The authors state this without testing it.

**For Nametags:** the best fit is **mild Alzheimer's**, where the person still knows people but can't find the name; **moderate is untested**. Saying so plainly is a strength, not a weakness. The worker and the literature arrived at it independently.

## 3. Why, what and how

**The point, in our words:** be clear about why Nametags exists, what it does, and how it does it.

**For Nametags:** the [evidence summary](README.md) now opens with a why, what and how, built from the evidence.

## 4. What Nametags does not claim

**Nametags does not claim to prevent or slow dementia, or to replace medication.**

**What came up:** two larger aims were mentioned: slowing or preventing the move into the most advanced stages of dementia, and standing in for medication. The recollection doesn't make clear whether these were the worker's views or hopes for the project. Either way, **the study found no evidence for either, and the closest prior art points the other way:**
- *McCarron et al. 2019,* a 6-month pilot trial of a face-recognition phone app: "The absence of empirical intervention effects is supported by the qualitative analysis, which revealed that the majority of participants did not find the SSA useful." The trial was small and possibly underpowered, but it is the closest test there is.
- **Medical-device rules:** claiming that software prevents a disease from progressing, or treats it, is the kind of claim that brings medical-device rules into play.

**What the evidence does support** is a person-centered, non-drug role alongside medical care:
- *Scales et al. 2018:* "Nonpharmacological practices are person-centered, and their selection can be informed by considering the cause and meaning of the individual's behavioral and psychological symptoms."
- *Abraha et al. 2017,* a review of reviews of non-drug approaches to distress in dementia, lists "cognitive/emotion-oriented interventions (13 SRs; 26 primary studies) that included cognitive stimulation, reminiscence therapy, validation therapy, simulated presence therapy". Simulated presence therapy plays recordings of family members to the person. That is close in spirit to Nametags, but no study here tested Nametags itself.

**Suggested wording:** *"Nametags is a non-drug support for the moments that matter: recognizing the people you love. It works alongside medical care, not instead of it."*

## 5. Help them remember; don't just tell

**The point, in our words:** simply telling someone who a visitor is can work against what they need. It is better to support their own recall and give them the chance to remember, rather than having a carer supply every answer or point it out, even when the person is confused or doesn't recognize family.

This challenges what Nametags does today: on arrival, the laptop program says the name and the live view shows it. **The evidence mostly backs the worker, with one guardrail.**

**Effort helps people relearn names:**
- *Dunn & Clare 2007,* comparing ways of learning face–name pairs in early-stage dementia: "Reducing errors did not produce any benefits." And: "Effort enhancement may be more important, especially when learning novel associations."
- *Clare et al. 2002,* relearning face–name pairs in early Alzheimer's: "Training produced a significant group improvement in recall of trained, but not control, items. Gains were largely maintained 6 months later, in the absence of practice." Also: "participants who were more aware of their memory difficulties achieved better outcomes."
- *Woods et al. 2012* (Cochrane): "There was consistent evidence from multiple trials that cognitive stimulation programmes benefit cognition in people with mild to moderate dementia over and above any medication effects."
- *Clare et al. 2019* (the GREAT trial, a multicentre randomised controlled trial): "CR enables people with early-stage dementia to improve their everyday functioning in relation to individual goals targeted in the therapy."

**The guardrail: never make it a test they can fail.**
- *Woods et al. 2012:* the older reality orientation (RO) approach "became associated with a rigid, confrontational approach to people with dementia, leading to its use becoming less and less common."
- *Yamaguchi et al. 2010:* "the activities should be based on errorless learning to ensure a pleasant atmosphere and to maintain a patient's dignity."
- *Dementia UK:* "Try not to correct the person if they get your name wrong…"

**For Nametags: cue first, then the name.**
1. The glasses say the relationship without the name: *"Your grandson is here."*
2. They listen for a few seconds.
3. If the wearer says the name, they affirm it warmly: *"Yes, that's David!"* That is the warm moment from theme 1.
4. If not, or if the wearer asks, they give the name gently: *"It's David, your grandson."* Never "No".

The design, worked out against the code on `main`, is [change 1 in the suggested changes](suggested-changes.md#1-cue-first-then-the-name-designed-not-built). It is *designed, not built*.

**Caveat:** all of this evidence comes from structured training sessions in early-stage dementia. No study has tested a device that cues in the moment, so Nametags' version is untested. The worker's point, the research and the best-fit group (mild Alzheimer's, theme 2) line up; a pilot would have to show the rest.
