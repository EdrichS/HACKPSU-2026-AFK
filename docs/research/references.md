# References

Every source cited in these pages, grouped by kind. Authors, years, titles, venues, DOIs and links are taken from the study's data files in [`research/derived/`](../../research/derived/), not typed from memory.

**How the quotes were checked:**
- **44 quotes** from figures, care-worker accounts, guidance and papers were fetched from their sources by script and matched word for word.
- **20 deep-read papers:** each supporting sentence was matched the same way, and each DOI was checked against Crossref for title, first author and year.
- **4 quotes could not be checked by script.** The study's agent read them in the full text on PubMed Central, but the check script was refused there (HTTP 403), so they are not independently verified. They are marked **Not checked by script** below, under Cohen-Mansfield et al. 2014 and Kemp et al. 2025. None of them is quoted in the [evidence summary](README.md), the [suggested changes](suggested-changes.md) or the [interview themes](interview-themes.md).

> [!NOTE]
> Quotes in these pages are short and attributed, and they belong to their sources. The MIT license covers the code, not the quoted text.

## Figures

### Published figures

- **Alzheimer's Association (2026).** 2026 Alzheimer's Disease Facts and Figures. Printed citation: Alzheimers Dement 2026;22, [doi:10.1002/alz.71345](https://doi.org/10.1002/alz.71345). [PDF](https://www.alz.org/getmedia/ef8f48f9-ad36-48ea-87f9-b74034635c1e/alzheimers-facts-and-figures.pdf). Used for: 7.4 million Americans 65 and older with Alzheimer's dementia in 2026; 12.7 million unpaid caregivers and 19.6 billion hours of care in 2025, or 1,543 hours each; 472,000 caregivers in Pennsylvania; 46% of nursing-home residents with Alzheimer's or other dementias (58% of long-stay and 36% of short-stay patients).
- **World Health Organization (2026).** Dementia fact sheet, dated 3 July 2026. [who.int](https://www.who.int/news-room/fact-sheets/detail/dementia). Used for: 57 million people living with dementia worldwide in 2021, and that people with dementia may not be able to recognize family members or friends.
- **National Center for Health Statistics (CDC).** Alzheimer disease statistics page, last reviewed February 18, 2026. [cdc.gov](https://www.cdc.gov/nchs/fastats/alzheimers.htm). Used for: 41.1% of US nursing-home residents diagnosed with Alzheimer disease or other dementias in 2022.
- **Alzheimer's Society.** Facts for the media about dementia, no date on the page. [alzheimers.org.uk](https://www.alzheimers.org.uk/what-we-do/news-and-media/facts-media). Used for: 70% of people in care homes in England with dementia or severe memory problems.
- **Mendez MF, Martin RJ, Smyth KA, Whitehouse PJ (1992).** Disturbances of person identification in Alzheimer's disease. A retrospective study. *The Journal of nervous and mental disease* 180(2):94-96. PMID 1737981. [Europe PMC record (JSON)](https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:1737981%20AND%20SRC:MED&format=json&resultType=core). Used for: disturbances of person identification in 25.4% of 217 outpatients with Alzheimer's disease.
- **Harciarek M, Kertesz A (2008).** The prevalence of misidentification syndromes in neurodegenerative diseases. *Alzheimer disease and associated disorders* 22(2):163-169. PMID 18525289. [Europe PMC record (JSON)](https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:18525289%20AND%20SRC:MED&format=json&resultType=core). Used for: misidentification syndromes in 15.8% of 392 people with probable Alzheimer's disease.
- **Pereira GCM, de Oliveira GC (2019).** Prevalence of Capgras syndrome in Alzheimer's patients: A systematic review and meta-analysis. *Dementia & neuropsychologia* 13(4):463-468. PMID 31844501. [Europe PMC record (JSON)](https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:31844501%20AND%20SRC:MED&format=json&resultType=core). Used for: Capgras syndrome in 6% of 1,977 people with Alzheimer's disease, pooled from 8 studies.

### Data we counted ourselves

- **Europe PMC REST API.** [https://www.ebi.ac.uk/europepmc/webservices/rest/search](https://www.ebi.ac.uk/europepmc/webservices/rest/search). Five searches of titles and abstracts, pulled October 25, 2026 at 00:51 EDT: 7,366 records, 6,816 unique, 5,804 after the data-quality filters. The queries and hit counts are in [`research/raw/manifest.json`](../../research/raw/manifest.json).
- **Centers for Medicare & Medicaid Services (CMS).** Minimum Data Set Frequency, state level, Q3 2026: [`MDS_Frequency_Q3_2026.csv`](https://data.cms.gov/sites/default/files/2026-10/3fc2159f-c755-4ffc-81d6-fd40bb3e421f/MDS_Frequency_Q3_2026.csv), 133,920 rows. Used for the nursing-home diagnosis counts.

## Care-worker accounts

Published accounts from care-home, nursing-home and assisted-living staff, quoted on [care-worker accounts](care-worker-accounts.md).

- **Ariander A, Olaison A, Andersson C, Sjödahl R, Nilsson L, Kastbom L (2024).** Ethical challenges causing moral distress: nursing home staff's experiences of working during the COVID-19 pandemic. *Scandinavian Journal of Primary Health Care* 42(2):266-275. [doi:10.1080/02813432.2024.2308573](https://doi.org/10.1080/02813432.2024.2308573).
- **Bernardi S, Fiordelli M, Rubinelli S, Spagnoli V, Malacrida R, Martignoni G (2024).** Navigating Communication in Nursing Homes During COVID-19: Perspectives From Families, Healthcare Professionals, and Managers in Southern Switzerland-A Qualitative Study. *International Journal of Public Health* 69:1606583. [doi:10.3389/ijph.2024.1606583](https://doi.org/10.3389/ijph.2024.1606583).
- **Cohen-Mansfield J, Golander H, Arnheim G, Cohen R (2014).** Reactions and Interventions for Delusions in Nursing Home Residents with Dementia. *American Journal of Alzheimer's Disease and Other Dementias* 29(4):386-394. [doi:10.1177/1533317514522850](https://doi.org/10.1177/1533317514522850).
  - **Not checked by script (2 quotes):** a staff informant seeing no need to intervene when a resident (Mr D, the paper's label) took a caregiver for his daughter; and staff arguing with residents about reality in 37% of cases, and in 40% of misidentification cases. The study's agent read them in the full text on [PubMed Central](https://pmc.ncbi.nlm.nih.gov/articles/PMC10852750/), but the check script was refused there (HTTP 403).
  - **Checked by script:** 1 quote from the abstract.
- **Edwards KJ, Jones RB, Shenton D, Page T, Maramba I, Warren A, Fraser F, Križaj T, Coombe T, Cowls H, Chatterjee A (2021).** The Use of Smart Speakers in Care Home Residents: Implementation Study. *Journal of Medical Internet Research* 23(12):e26767. [doi:10.2196/26767](https://doi.org/10.2196/26767).
- **Emilsson M, Karlsson C, Svensson A (2023).** Experiences of using surveillance cameras as a monitoring solution at nursing homes: The eldercare personnel's perspectives. *BMC Health Services Research* 23(1):144. [doi:10.1186/s12913-023-09130-2](https://doi.org/10.1186/s12913-023-09130-2).
- **Kaelen S, van den Boogaard W, Pellecchia U, Spiers S, De Cramer C, Demaegd G, Fouqueray E, Van den Bergh R, Goublomme S, Decroo T, Quinet M, Van Hoof E, Draguez B (2021).** How to bring residents' psychosocial well-being to the heart of the fight against Covid-19 in Belgian nursing homes-A qualitative study. *PLoS One* 16(3):e0249098. [doi:10.1371/journal.pone.0249098](https://doi.org/10.1371/journal.pone.0249098).
- **Kemp CL, Anglin E, Morgan JC, Perkins MM, Burgess EO, Bender AA, et al. (2025).** Differing Realities Among Assisted Living Residents With Dementia: Understanding Care Partner Responses. *The Gerontologist* 65(5):gnaf061. [doi:10.1093/geront/gnaf061](https://doi.org/10.1093/geront/gnaf061).
  - **Not checked by script (2 quotes):** residents believing some staff were relatives, and care partners tending not to correct this; and a care worker describing how staff act as the assistant of a resident (Hugh, the paper's pseudonym). The study's agent read them in the full text on [PubMed Central](https://pmc.ncbi.nlm.nih.gov/articles/PMC12048800/), but the check script was refused there (HTTP 403).
  - **Checked by script:** 1 quote from the abstract.
- **Koh WQ, Vandemeulebroucke T, Gastmans C, Miranda R, Van den Block L (2023).** The ethics of pet robots in dementia care settings: Care professionals' and organisational leaders' ethical intuitions. *Frontiers in Psychiatry* 14:1052889. [doi:10.3389/fpsyt.2023.1052889](https://doi.org/10.3389/fpsyt.2023.1052889).
- **Rönning H, Svanholm S, Ekdahl A, Johansson D, Rising MH (2026).** 'To Have One Extra Eye': Exploring Professionals' Experiences with Digital Supervision in a Nursing Home for Older People. *SAGE Open Nursing* 12:23779608261436779. [doi:10.1177/23779608261436779](https://doi.org/10.1177/23779608261436779).
- **Tuckett AG (2012).** The experience of lying in dementia care: a qualitative study. *Nursing Ethics* 19(1):7-20. [doi:10.1177/0969733011412104](https://doi.org/10.1177/0969733011412104).
- **Verbeek H, Gerritsen DL, Backhaus R, de Boer BS, Koopmans RTCM, Hamers JPH (2020).** Allowing Visitors Back in the Nursing Home During the COVID-19 Crisis: A Dutch National Study Into First Experiences and Impact on Well-Being. *Journal of the American Medical Directors Association* 21(7):900-904. [doi:10.1016/j.jamda.2020.06.020](https://doi.org/10.1016/j.jamda.2020.06.020).

## Research papers

### Read in depth (20 papers)

Chosen by the tf-idf reading list and for the open questions about Nametags; summarized on [research at scale](research-at-scale.md). 6 were read in full text and 14 from the abstract only.

- **Caute A, Mirza L, Mackintosh B, Scherer R, Joffe V (2026).** Uses of assistive technology incorporating smart camera features in the rehabilitation of people living with disabilities: a scoping review. *Disability and Rehabilitation: Assistive Technology*. [doi:10.1080/17483107.2026.2678548](https://doi.org/10.1080/17483107.2026.2678548). Read from: abstract.
- **Chandra SR, Patwardhan K, Pai AR (2017).** Problems of Face Recognition in Patients with Behavioral Variant Frontotemporal Dementia. *Indian Journal of Psychological Medicine*. [doi:10.4103/ijpsym.ijpsym_90_17](https://doi.org/10.4103/ijpsym.ijpsym_90_17). Read from: full text.
- **Day AM, James IA, Meyer TD, Lee DR (2011).** Do people with dementia find lies and deception in dementia care acceptable? *Aging & Mental Health*. [doi:10.1080/13607863.2011.569489](https://doi.org/10.1080/13607863.2011.569489). Read from: abstract.
- **Fardoun HM, Mashat AA, Ramirez Castillo J (2017).** Recognition of familiar people with a mobile cloud architecture for Alzheimer patients. *Disability and Rehabilitation*. [doi:10.3109/09638288.2015.1025992](https://doi.org/10.3109/09638288.2015.1025992). Read from: abstract.
- **Hocking J, Oster C, Maeder A, Lange B (2023).** Design, development, and use of conversational agents in rehabilitation for adults with brain-related neurological conditions: a scoping review. *JBI Evidence Synthesis*. [doi:10.11124/jbies-22-00025](https://doi.org/10.11124/jbies-22-00025). Read from: abstract.
- **Horn BL, Albers EA, Mitchell LL, Jutkowitz E, Finlay JM, Millenbah AN, et al. (2023).** Can Technology-Based Social Memory Aids Improve Social Engagement? Perceptions of a Novel Memory Aid for Persons With Memory Concerns. *Journal of Applied Gerontology*. [doi:10.1177/07334648221134869](https://doi.org/10.1177/07334648221134869). Read from: abstract.
- **Kurth S, Moyse E, Bahri MA, Salmon E, Bastin C (2015).** Recognition of personally familiar faces and functional connectivity in Alzheimer's disease. *Cortex*. [doi:10.1016/j.cortex.2015.03.013](https://doi.org/10.1016/j.cortex.2015.03.013). Read from: abstract.
- **Luzzi S, Baldinelli S, Ranaldi V, Fabi K, Cafazzo V, Fringuelli F, et al. (2017).** Famous faces and voices: Differential profiles in early right and left semantic dementia and in Alzheimer's disease. *Neuropsychologia*. [doi:10.1016/j.neuropsychologia.2016.11.020](https://doi.org/10.1016/j.neuropsychologia.2016.11.020). Read from: abstract.
- **Matthews JT, Campbell GB, Hunsaker AE, Klinger J, Mecca LP, Hu L, et al. (2016).** Wearable Technology to Garner the Perspective of Dementia Family Caregivers. *Journal of Gerontological Nursing*. [doi:10.3928/00989134-20151008-65](https://doi.org/10.3928/00989134-20151008-65). Read from: abstract.
- **Matthews JT, Lingler JH, Campbell GB, Hunsaker AE, Hu L, Pires BR, et al. (2015).** Usability of a Wearable Camera System for Dementia Family Caregivers. *Journal of Healthcare Engineering*. [doi:10.1260/2040-2295.6.2.213](https://doi.org/10.1260/2040-2295.6.2.213). Read from: abstract.
- **McCarron HR, Zmora R, Gaugler JE (2019).** A Web-Based Mobile App With a Smartwatch to Support Social Engagement in Persons With Memory Loss: Pilot Randomized Controlled Trial. *JMIR Aging*. [doi:10.2196/13378](https://doi.org/10.2196/13378). Read from: full text.
- **Mishra PK, Iaboni A, Ye B, Newman K, Mihailidis A, Khan SS (2023).** Privacy-protecting behaviours of risk detection in people with dementia using videos. *BioMedical Engineering OnLine*. [doi:10.1186/s12938-023-01065-3](https://doi.org/10.1186/s12938-023-01065-3). Read from: full text.
- **Nagaratnam N, Irving J, Kalouche H (2003).** Misidentification in patients with dementia. *Archives of Gerontology and Geriatrics*. [doi:10.1016/s0167-4943(03)00045-1](https://doi.org/10.1016/s0167-4943%2803%2900045-1). Read from: abstract.
- **Oriani M, Moniz-Cook E, Binetti G, Zanieri G, Frisoni GB, et al. (2003).** An electronic memory aid to support prospective memory in patients in the early stages of Alzheimer's disease: a pilot study. *Aging & Mental Health*. [doi:10.1080/1360786021000045863](https://doi.org/10.1080/1360786021000045863). Read from: abstract.
- **Pearce D, Gould RL, Roughley M, Reynolds G, Ward EV, Bhome R, et al. (2022).** Paranoid and misidentification subtypes of psychosis in dementia. *Neuroscience & Biobehavioral Reviews*. [doi:10.1016/j.neubiorev.2022.104529](https://doi.org/10.1016/j.neubiorev.2022.104529). Read from: abstract.
- **Ruggiano N, Brown EL, Roberts L, Framil Suarez CV, Luo Y, Hao Z, et al. (2021).** Chatbots to Support People With Dementia and Their Caregivers: Systematic Review of Functions and Quality. *Journal of Medical Internet Research*. [doi:10.2196/25006](https://doi.org/10.2196/25006). Read from: full text.
- **Sriram V, Jenkinson C, Peters M (2019).** Informal carers' experience of assistive technology use in dementia care at home: a systematic review. *BMC Geriatrics*. [doi:10.1186/s12877-019-1169-0](https://doi.org/10.1186/s12877-019-1169-0). Read from: full text.
- **Stara V, Vera B, Bolliger D, Rossi L, Felici E, Di Rosa M, et al. (2021).** Usability and Acceptance of the Embodied Conversational Agent Anne by People With Dementia and Their Caregivers: Exploratory Study in Home Environment Settings. *JMIR mHealth and uHealth*. [doi:10.2196/25891](https://doi.org/10.2196/25891). Read from: full text.
- **Woodberry E, Browne G, Hodges S, Watson P, Kapur N, Woodberry K (2015).** The use of a wearable camera improves autobiographical memory in patients with Alzheimer's disease. *Memory*. [doi:10.1080/09658211.2014.886703](https://doi.org/10.1080/09658211.2014.886703). Read from: abstract.
- **Zwijsen SA, Niemeijer AR, Hertogh CM (2011).** Ethics of using assistive technology in the care for community-dwelling elderly people: an overview of the literature. *Aging & Mental Health*. [doi:10.1080/13607863.2010.543662](https://doi.org/10.1080/13607863.2010.543662). Read from: abstract.

### Cited for a specific finding

Quoted for the recall-first design and the non-drug framing. McCarron et al. 2019, above, also supplies three quotes from its full text.

- **Abraha I, Rimland JM, Trotta FM, Dell'Aquila G, Cruz-Jentoft A, Petrovic M, et al. (2017).** Systematic review of systematic reviews of non-pharmacological interventions to treat behavioural disturbances in older patients with dementia. The SENATOR-OnTop series. *BMJ open*. [doi:10.1136/bmjopen-2016-012759](https://doi.org/10.1136/bmjopen-2016-012759).
- **Clare L, Kudlicka A, Oyebode JR, Jones RW, Bayer A, Leroi I, et al. (2019).** Individual goal-oriented cognitive rehabilitation to improve everyday functioning for people with early-stage dementia: A multicentre randomised controlled trial (the GREAT trial). *International journal of geriatric psychiatry*. [doi:10.1002/gps.5076](https://doi.org/10.1002/gps.5076).
- **Clare L, Wilson BA, Carter G, Roth I, Hodges JR (2002).** Relearning face-name associations in early Alzheimer's disease. *Neuropsychology*. [doi:10.1037//0894-4105.16.4.538](https://doi.org/10.1037//0894-4105.16.4.538).
- **Dunn J, Clare L (2007).** Learning face-name associations in early-stage dementia: comparing the effects of errorless learning and effortful processing. *Neuropsychological rehabilitation*. [doi:10.1080/09602010701218317](https://doi.org/10.1080/09602010701218317).
- **Scales K, Zimmerman S, Miller SJ (2018).** Evidence-Based Nonpharmacological Practices to Address Behavioral and Psychological Symptoms of Dementia. *The Gerontologist*. [doi:10.1093/geront/gnx167](https://doi.org/10.1093/geront/gnx167).
- **Woods B, Aguirre E, Spector AE, Orrell M (2012).** Cognitive stimulation to improve cognitive functioning in people with dementia. *The Cochrane database of systematic reviews*. [doi:10.1002/14651858.cd005562.pub2](https://doi.org/10.1002/14651858.cd005562.pub2).
- **Yamaguchi H, Maki Y, Yamagami T (2010).** Overview of non-pharmacological intervention for dementia and principles of brain-activating rehabilitation. *Psychogeriatrics : the official journal of the Japanese Psychogeriatric Society*. [doi:10.1111/j.1479-8301.2010.00323.x](https://doi.org/10.1111/j.1479-8301.2010.00323.x).

## Guidance

Advice and reports from dementia and social-care organizations. They are quoted as advice, not as observations.

- **Alzheimer's Association (n.d.).** Memory Loss and Confusion. Guidance. [alz.org](https://www.alz.org/help-support/caregiving/stages-behaviors/memory-loss-confusion).
- **Dementia UK (2025).** When someone with dementia doesn’t recognise you. Guidance. [dementiauk.org](https://www.dementiauk.org/information-and-support/looking-after-yourself-as-a-carer/when-someone-doesnt-recognise-you/).
- **Mental Health Foundation (2016).** What is Truth? An Inquiry about Truth and Lying in Dementia Care. Report. [mentalhealth.org.uk](https://www.mentalhealth.org.uk/sites/default/files/2022-09/MHF-dementia-truth-inquiry-report.pdf).
- **Social Care Institute for Excellence (SCIE) (2018).** Adult safeguarding practice questions. Guidance. [scie.org.uk](https://www.scie.org.uk/safeguarding/adults/practice/adult-safeguarding-practice-questions/).

## Read but not used

These were read for the care-worker accounts and then dropped. [Care-worker accounts](care-worker-accounts.md) explains each choice.

- **Murray J, Thompson J, Hill M, James I (2025).** An ethnographic study to develop a taxonomy of lies for communicating with people with moderate to severe dementia. *Nursing Ethics* 32(1):272-287. [doi:10.1177/09697330241246087](https://doi.org/10.1177/09697330241246087). Dropped: the setting is hospital wards, not a care home.
- **Eikelenboom-Boskamp A, Huis A, Saris K, Stobernack T, de Leeuw M, Hulscher M, Voss A (2023).** Preferences for healthcare worker attire among nursing home residents and residents' preferences as perceived by workers: A cross-sectional study. *International Journal of Nursing Studies Advances* 5:100112. [doi:10.1016/j.ijnsa.2022.100112](https://doi.org/10.1016/j.ijnsa.2022.100112). Dropped: an unreferenced aside in the limitations, from a study that excluded residents with a known dementia diagnosis.
- **National Institute on Aging (NIA), US National Institutes of Health (2024).** Helping Family and Friends Understand Alzheimer’s Disease. Guidance. [nia.nih.gov](https://www.nia.nih.gov/health/alzheimers-and-relationships/helping-family-and-friends-understand-alzheimers-disease). Dropped: the same advice as Dementia UK's, which also spells out the relationship.
