# Vitrine — Business Case & Research-Platform Justification

**Scope.** Evidence base for justifying Vitrine — a capture-adaptive photo/video → 3D
Gaussian Splatting → game-ready structured-3D pipeline (mesh + textures + metadata
lineage, delivered to Unreal Engine 5.8, on-prem hardened Docker) — as a University of
Salford research platform. The case rests on two convergent decay vectors: **physical
decay of cultural artifacts** and **digital bitrot / format obsolescence**. Both make
*structured, open, re-renderable 3D surrogates* a preservation, access, and restoration
asset rather than a novelty.

> **Reading note on figures.** Heritage-loss and preservation facts below come from
> primary or institutional sources (UNESCO, WRI, DPC, Library of Congress, Pew, CLIR)
> and are reliable. **Market-size numbers come from commercial market-research firms,
> have opaque methodology and wide variance between vendors, and should be treated as
> directional only** — each such figure is flagged inline.

---

## Why now

Three curves are crossing at once:

1. **Loss is accelerating and largely irreversible.** UNESCO/WRI (July 2025) find **73%
   of 1,172 non-marine World Heritage sites are highly exposed to water-related hazards**,
   and **21% face multiple overlapping risks** [1]. Catastrophic single-event losses —
   Brazil's National Museum (2018), Notre-Dame (2019), Palmyra/Mosul (2015), the Bamiyan
   Buddhas (2001) — show that whatever was not captured *before* the event is simply gone
   [2][3][4][5].
2. **The capture technology just became good and cheap enough.** 3D Gaussian Splatting
   (2023 onward) delivers photorealistic, view-dependent capture with small file sizes and
   web/real-time deployment, and by 2025 is the subject of a dense peer-reviewed heritage
   literature (ISPRS, *npj Heritage Science*, the EU Horizon "Gaussian Heritage" project)
   [6][7]. Capture that once needed survey-grade LiDAR crews can now start from ordinary
   photo/video.
3. **The default digital-preservation story is failing.** Pew (2024) measured that **38% of
   web pages that existed in 2013 were gone by 2023** [8]; the Digital Preservation
   Coalition's 2023 "Bit List" grew to **87 endangered digital categories** and reclassified
   **unpublished research data as *Critically Endangered*** [9]. Un-migrated 3D captures on
   ageing media and in proprietary formats are exactly the material that vanishes quietly.

The window in which an artifact still exists physically **and** has not yet been captured is
the window Vitrine addresses. It is closing.

---

## 1. Physical decay of cultural artifacts

**The scale is systemic, not anecdotal.**

- **Climate / water.** UNESCO + World Resources Institute screened 1,172 non-marine World
  Heritage sites against four water risks (stress, drought, riverine and coastal flooding):
  **73% are highly exposed; 21% face multiple overlapping risks** [1]. In the Mediterranean
  alone, of **49 low-lying coastal cultural** World Heritage sites, **37 are already at risk
  from a 100-year flood and 42 from coastal erosion today**, with flood risk projected to
  rise ~50% by 2100 (peer-reviewed, *Nature Communications*) [10]. At-risk named sites
  include Venice, Alexandria, Carthage, and Delos [10].
- **Material degradation & handling.** Conservation is a losing race against humidity,
  salt crystallisation, subsidence, light, and the cumulative micro-damage of physical
  handling; digital surrogates let researchers study and display without touching the
  object [10].

**Notable losses — the recurring lesson is "capture beats reconstruction."**

- **National Museum of Brazil (Rio), September 2018.** Fire tore through a collection of
  ~20 million items — dinosaur fossils, the "Luzia" skull (oldest human remains in the
  Americas), and irreplaceable recordings of now-extinct Indigenous languages [2]. Recovery
  has depended on **crowdsourced photos and 3D reconstruction** (Museu Nacional Vivo /
  Sketchfab; 3D-printed recreations of ~300 objects including Luzia) — surrogates that
  exist only because someone happened to have imaged the objects beforehand. The hard limit
  is explicit: a 3D model preserves form and enables access, but **DNA and material analysis
  die with the object** [2]. *(Uncertainty: "20 million" is the museum's total holdings;
  destruction estimates commonly cited at ~90%+ but vary by source.)*
- **Notre-Dame de Paris, April 2019.** Art historian **Andrew Tallon laser-scanned the
  cathedral in 2010, capturing >1 billion points to ~5 mm accuracy** [3]. After the fire,
  that pre-existing point cloud became the **restoration blueprint** for the vaults and
  spire. Tallon died in 2018 — the capture pre-dated both his death and the fire, the
  clearest possible argument for **pre-emptive, opportunistic digitisation** [3].
- **Palmyra & Mosul Museum, 2015 (ISIS); Bamiyan Buddhas, 2001 (Taliban).** Deliberate
  destruction of the 1,800-year-old Arch of Triumph, Mosul's statuary, and the Bamiyan
  cliff Buddhas [4][5]. Post-hoc reconstruction (Project Mosul / Rekrei photogrammetry from
  tourist photos; the two-thirds-scale Palmyra arch machined from pre-war imagery for
  Trafalgar Square) proves that **even scattered, low-quality prior captures have
  preservation value** — but also that reconstruction from happenstance images is a poor
  substitute for a deliberate, structured capture made while the object stood [4][5].

**The case for 3D digital surrogates** is therefore threefold: **preservation** (a dated,
accurate record of the object's exact state), **access** (study/display without handling or
transport), and a **restoration reference** (a measurable blueprint if the physical object
is damaged or lost) [3][2].

---

## 2. Digital bitrot & format obsolescence

Digitising is necessary but **not sufficient** — the surrogate itself decays unless it is
built to last.

- **The threat is officially recognised.** The **UNESCO Charter on the Preservation of the
  Digital Heritage (2003)** warns that "unless the prevailing threats are addressed, the
  loss of the digital heritage will be rapid and inevitable," naming **rapid obsolescence of
  hardware and software** as a primary cause [11].
- **Endangerment is measured and worsening.** The **Digital Preservation Coalition's Global
  "Bit List"** — the sector's authoritative at-risk register — reached **87 endangered
  digital categories in 2023 (up from 73 in 2021)**, reclassified **unpublished research
  data to *Critically Endangered***, and lists **3D digital engineering drawings as
  *Endangered*** [9]. The 2024 interim update found the risk profile essentially unchanged
  and renewed calls for action [12].
- **Link rot / reference rot quantifies the "digital dark age."** Pew Research (2024):
  **38% of pages online in 2013 were inaccessible by 2023; 25% of all pages sampled
  2013–2023 were gone; 54% of Wikipedia articles contain at least one dead reference link;
  ~1 in 5 tweets vanished within months** of posting [8]. Independent web-scale studies put
  overall link death since 2013 at ~66.5% [13]. Anything that depends on a cloud URL,
  a hosted viewer, or an external reference is on this decay curve.
- **Storage media are not archival.** LTO magnetic tape is rated 15–30 years but typically
  lasts **10–20 in practice; hard drives 3–5 years; some recordable optical discs become
  unreadable in under a year** [14]. CLIR's guidance is blunt: no single medium guarantees
  long-term survival — **only redundancy plus active migration does** [14].
- **Proprietary 3D formats are a lock-in hazard.** Opaque or vendor-controlled formats
  (e.g. Autodesk FBX) risk becoming unreadable as tools change. **Open, standardised
  formats age far better**: **glTF is an ISO/IEC 12113:2022 international standard** (the
  "JPEG of 3D"), and **OpenUSD** is an open, vendor-neutral scene description now being
  formally aligned with glTF by AOUSD and Khronos [15]. The **Library of Congress
  Sustainability of Digital Formats / Recommended Formats Statement** flags born-digital 3D
  stewardship as "not yet mainstream" and favours open, widely-supported formats such as
  **PLY and OBJ** for scanned surface geometry [16].

**Why Vitrine's output ages better than an opaque capture.** A raw scan, a proprietary
project file, or a cloud-hosted viewer is a single point of failure. Vitrine emits a
**structured, re-renderable asset stack** — mesh + baked textures + explicit metadata
lineage (`v2g:*` provenance), exportable to open formats (glTF/OpenUSD) and importable into
a mainstream game engine (UE 5.8). That is **format-migratable, tool-independent, and
re-renderable decades out**, exactly the properties the DPC and Library of Congress
identify as surviving obsolescence [16][15][9]. A `.ply` splat and a `.glb` mesh with
documented provenance are things a future institution can still open; a defunct SaaS
account is not.

---

## 3. Value & demand signals

**The access gap is enormous — and digitisation is the lever.** Museums display only a
small fraction of what they hold: an **ICCROM/UNESCO survey and multiple institutional
figures put on-display holdings at roughly 5–10%**, with storage at **~90% for science
museums, ~95% for ethnographic, ~96.5% for archaeology, ~99% for biology/geology** [17].
Structured 3D digitisation is the most direct route to unlocking the other 90%+ for
research, teaching, and public access.

**Public appetite is documented, not assumed.** The **University of Glasgow's £5.6m
"Museums in the Metaverse" (MiM)** programme surveyed **2,000+ people worldwide and found
79% interested in using digital tools to explore collections not currently on public
display** [18] — a strong, UK-academic demand signal directly relevant to a Salford
research platform.

**Technology fit is validated in the literature.** 3D Gaussian Splatting is repeatedly
identified in 2025 peer-reviewed heritage work (ISPRS Annals, *npj Heritage Science*, the
EU Horizon "Gaussian Heritage" project) as **the most advantageous method where rapid
processing, low compute, small file size, and easy web deployment matter**, while
delivering photorealistic material/lighting fidelity that traditional meshes lack
[6][7] — precisely Vitrine's capture core.

**Market signals (directional only — commercial estimates, treat with caution).** Vendor
market-research reports (methodology opaque, figures vary widely between firms) put the
"virtual museums" market at roughly **$3.8B in 2025 growing to ~$12.6B by 2034
(~14% CAGR)**, "VR museum" at **~$1.4B (2024) → ~$13B by 2033 (~28% CAGR)**, and "digital
museum solutions" at **~$2.5B (2025) → ~$8B by 2033 (~15% CAGR)** [19]. One vendor claims
platforms such as Matterport/Sketchfab/Google Arts & Culture collectively served
**>45,000 cultural institutions by end-2025** [19] *(single-source, unverified — cite only
as an adoption indicator, not a hard figure)*. The **consistent signal across all sources
is strong growth and mainstreaming**; the **specific magnitudes are unreliable**.

**Repatriation & restitution.** Digital surrogates are now a live element of repatriation
and restitution debates and of "digital repatriation" practice — returning high-quality 3D
records to originating communities. Critically, the literature stresses that meaningful
digital repatriation requires the **originating community to control the infrastructure and
access terms** (CARE principles; Indigenous data sovereignty), not merely to receive a file
on someone else's server [20]. This directly motivates a **sovereign, on-prem** platform
(§4).

---

## 4. The specific case for a sovereign, on-prem research platform

Why an on-prem, reproducible, hardened pipeline — **not** a cloud SaaS — is the right shape
for an institutional research platform:

- **IP & sensitive collections / data sovereignty.** Sacred, culturally-restricted, or
  rights-encumbered material cannot be governed under a third-party SaaS's terms. The
  Indigenous-data-sovereignty and CARE literature is explicit: **when an outside institution
  "controls the servers, the data, and the terms of access," it reproduces dependency**
  [20]. An **on-prem, sovereign** pipeline keeps custody, access protocols, and cultural
  protocols with the institution and originating communities — a hard requirement for
  ethically defensible heritage work, not a preference.
- **Reproducibility & FAIR/paradata.** Modern heritage scholarship treats the **3D
  digitisation *process* itself as a research object** requiring documented provenance and
  paradata; "without formal representation of data provenance, 3D data can be FAIR but of
  little use" [21]. Vitrine's **pinned-SOTA, version-checked, containerised pipeline with
  `v2g:*` lineage metadata** makes runs reproducible and the provenance chain explicit —
  the difference between a research instrument and a black box.
- **Longevity vs SaaS lock-in.** A cloud viewer or proprietary platform is subject to the
  same link-rot/obsolescence curves as everything else (§2): vendor pivots, price changes,
  or shutdown can orphan a collection. **Locally-held, open, re-renderable assets** (mesh +
  texture + open-format export + game-engine import) survive independent of any single
  vendor's business model — aligned with DPC and Library of Congress guidance [9][16].
- **Cost at collection scale.** Because **90%+ of collections sit in storage** [17], any
  serious digitisation programme is high-volume. Recurring per-asset cloud
  storage/processing/hosting fees scale badly against that volume; an **on-prem capex
  pipeline** amortises across the whole collection and avoids open-ended egress and
  subscription liabilities.
- **Security & integrity.** A **hardened Docker** deployment (isolation, no ambient
  external dependencies, controlled model provenance) protects sensitive collections and
  guarantees the pipeline is auditable and re-runnable — appropriate for a university
  research platform handling third-party and community-owned material.

**Net:** the two decay vectors make **structured, open, provenance-rich 3D surrogates** the
right preservation artifact; the sovereignty, reproducibility, longevity, and cost
arguments make an **on-prem, hardened, reproducible pipeline** the right way to produce them
for an institution like Salford. Vitrine is the intersection of the two.

---

## Citations

1. UNESCO World Heritage Centre — *Nearly Three-Quarters of World Heritage Sites Are at High
   Risk from Water-Related Hazards* (UNESCO/WRI analysis, July 2025).
   https://whc.unesco.org/en/news/2788 ; WRI insight:
   https://www.wri.org/insights/water-risks-unesco-world-heritage-sites
2. *National Museum of Brazil fire* — Wikipedia (overview, collection scale, 3D/crowdsourced
   reconstruction, Luzia): https://en.wikipedia.org/wiki/National_Museum_of_Brazil_fire ;
   Smithsonian Magazine:
   https://www.smithsonianmag.com/smart-news/artifacts-destroyed-brazil-devastating-national-museum-fire-180970194/
3. Andrew Tallon Notre-Dame laser scans (2010, >1 billion points, ~5 mm; restoration
   blueprint) — Vassar College *Leaving a Trace*:
   https://www.vassar.edu/news/leaving-a-trace ; GIM International:
   https://www.gim-international.com/content/news/the-indispensable-role-of-point-cloud-data-in-rebuilding-notre-dame
4. *Destruction of cultural heritage by the Islamic State* — Wikipedia (Mosul, Palmyra;
   Project Mosul/Rekrei; Trafalgar Sq arch):
   https://en.wikipedia.org/wiki/Destruction_of_cultural_heritage_by_the_Islamic_State ;
   Smithsonian, *The Heroic Effort to Digitally Reconstruct Lost Monuments*:
   https://www.smithsonianmag.com/history/heroic-effort-digitally-reconstruct-lost-monuments-180958098/
5. NOVA/PBS — *The Technology That Will Resurrect ISIS-Destroyed Antiquities* (Bamiyan,
   photogrammetry): https://www.pbs.org/wgbh/nova/article/digital-preservation-syria/
6. ISPRS Annals — *3D Gaussian Splatting for Enhanced Documentation of Cultural Artifacts*
   (2025):
   https://isprs-annals.copernicus.org/articles/X-M-2-2025/215/2025/isprs-annals-X-M-2-2025-215-2025.pdf
7. *Gaussian Heritage: 3D Digitization of Cultural Heritage with Integrated Object
   Segmentation* (EU Horizon), arXiv 2409.19039: https://arxiv.org/html/2409.19039v1 ;
   *npj Heritage Science* (2025), Gaussian splatting for damaged statues:
   https://www.nature.com/articles/s40494-025-02063-5
8. Pew Research Center — *When Online Content Disappears* / Link Rot and Digital Decay (May
   2024): https://www.pewresearch.org/data-labs/2024/05/17/when-online-content-disappears/
9. Digital Preservation Coalition — *Global "Bit List" of Endangered Digital Species 2023*
   (87 entries; unpublished research data → Critically Endangered; 3D engineering drawings →
   Endangered): https://www.dpconline.org/news/it-list-2023-is-data-loss-a-choice ;
   report PDF landing: https://www.dpconline.org/our-work/digitally-endangered-species
10. Reimann et al., *Mediterranean UNESCO World Heritage at risk from coastal flooding and
    erosion due to sea-level rise*, *Nature Communications* (2018), PMC6191433:
    https://pmc.ncbi.nlm.nih.gov/articles/PMC6191433/
11. UNESCO — *Charter on the Preservation of the Digital Heritage* (2003):
    https://www.unesco.org/en/legal-affairs/charter-preservation-digital-heritage ;
    text: https://unesdoc.unesco.org/ark:/48223/pf0000179529
12. DPC *Bit List* 2024 interim report (little change to risk profile; renewed calls for
    action) — InfoDocket summary:
    https://www.infodocket.com/2024/11/05/digital-preservation-coalition-dpc-the-bit-list-of-digitally-endangered-species-2024-interim-report-identifies-significant-little-change-to-risk-profile-prompting-renewed-calls-for-action/
13. Ahrefs — *Link Rot Study* (66.5% of links since 2013 dead):
    https://ahrefs.com/blog/link-rot-study/ ; *Link rot* — Wikipedia (legal-citation and
    Supreme Court URL decay figures): https://en.wikipedia.org/wiki/Link_rot
14. CLIR Pub 54 — *Life Expectancy: How Long Will Magnetic Media Last?*:
    https://www.clir.org/pubs/reports/pub54/4life_expectancy/ ; Arcserve, *Data Storage
    Lifespans*: https://www.arcserve.com/blog/data-storage-lifespans-how-long-will-media-really-last
15. Khronos Group — *Building Bridges in 3D: AOUSD and Khronos Collaborate on OpenUSD and
    glTF Interoperability* (glTF = ISO/IEC 12113:2022):
    https://www.khronos.org/blog/building-bridges-in-3d-aousd-and-khronos-collaborate-on-openusd-and-gltf-interoperability
    ; *glTF* — Wikipedia (ISO standard): https://en.wikipedia.org/wiki/GlTF
16. Library of Congress — *Sustainability of Digital Formats* and *Recommended Formats
    Statement — Design and 3D*; *Born to Be 3D* (born-digital 3D stewardship "not yet
    mainstream"): https://www.loc.gov/preservation/resources/rfs/design3D.html ;
    https://www.loc.gov/preservation/digital/formats/index.shtml ;
    https://loc.gov/preservation/digital/meetings/b2b3d/b2b3d2018.html
17. ICOM Working Group on Collections in Storage / ICCROM survey (only ~10% of collections
    displayed; storage 90–99% by museum type):
    https://icom.museum/wp-content/uploads/2024/05/Report_ICOM-STORAGE_EN_Final.pdf ;
    Quartz, *Why is so much of the world's great art in storage*:
    https://qz.com/583354/why-is-so-much-of-the-worlds-great-art-in-storage
18. University of Glasgow — *Museums in the Metaverse* (£5.6m; 2,000+ surveyed, 79%
    interested in digital access to non-displayed collections), via blooloop:
    https://blooloop.com/museum/in-depth/emerging-museum-technologies/
19. Market estimates (commercial, directional only): Dataintelo *Virtual Museums Market*
    (~$3.8B 2025 → $12.6B 2034): https://dataintelo.com/report/virtual-museums-market ;
    Dataintelo *Virtual Reality Museum Market*:
    https://dataintelo.com/report/virtual-reality-museum-market ; Data Insights *Digital
    Museum Solution Market*:
    https://www.datainsightsmarket.com/reports/digital-museum-solution-523453
    *(the ">45,000 institutions" and "2.6× engagement" claims are single-source vendor
    figures — treat as unverified adoption indicators.)*
20. Indigenous data sovereignty / CARE & digital repatriation (control of infrastructure):
    Terentia, *Upholding Data Sovereignty in Indigenous Cultural Heritage*:
    https://terentia.io/blog/indigenous-data-sovereignty-cultural-heritage ; Heritage
    Management Org, *After the Return*:
    https://heritagemanagement.org/after-the-return-readiness-and-responsibility-in-hosting-digitally-repatriated-heritage/
    ; *Digital repatriation* — Wikipedia: https://en.wikipedia.org/wiki/Digital_repatriation
21. FAIR/paradata for 3D cultural heritage (digitisation process as research object;
    provenance essential): *3D Data Practices and Preservation for Humanities* (MDPI
    Heritage, 2025): https://www.mdpi.com/2571-9408/8/10/435 ; *A Proposal for a FAIR
    Management of 3D Data in Cultural Heritage: the Aldrovandi Digital Twin Case*, arXiv
    2407.02018: https://arxiv.org/pdf/2407.02018

---

*Compiled 2026-07-02. Institutional/primary sources (UNESCO, WRI, DPC, Library of Congress,
Pew, CLIR, ICOM) are reliable; commercial market-size figures are flagged inline and should
be treated as directional. Verify any single-source vendor statistic before quoting it in a
formal funding submission.*
