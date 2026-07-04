# Vitrine — Competitive Landscape

Research findings, compiled 2026-07-02. Scope: consumer + professional 3D
capture / photogrammetry / Gaussian-splatting (3DGS) / NeRF platforms, and
cultural-heritage digitisation services, benchmarked against **Vitrine** — a
capture-adaptive photo/video → 3DGS → structured, textured 3D-scene pipeline
that outputs **game-ready assets** (FBX/GLB with baked PBR + per-object meshes)
for Unreal Engine 5.8 / Blender, running as a single hardened on-premises Docker
"mono-image" with an internal agentic controller, targeting on-prem,
data-sovereign heritage digitisation at the University of Salford.

> **Honesty note:** Vitrine is a bespoke research pipeline, not a shipping
> product. On raw reconstruction quality, mobile UX, capture ergonomics, scale,
> and polish, the commercial tools below are ahead. Vitrine's edge is a
> *specific integration* (on-prem + game-asset UE output + structured
> room-plus-objects + lineage) that none of them deliver as a single deployable
> unit. Claims flagged **[uncertain]** need primary-source confirmation.

---

## 1. Comparison table

| Tool / Service | What it does | Primary delivery format | On-prem vs cloud | Licensing / cost | How it compares to Vitrine |
|---|---|---|---|---|---|
| **Luma AI** | Cloud 3DGS/NeRF from phone photo/video; now primarily a **generative-video** company (Ray3/Dream Machine) | `.ply` splat, `.luma`; mesh fallback (GLB/USDZ); UE plugin (LumaActor, splat renderer) | **Cloud only** (uploads required); enterprise API | Free tier + paid/enterprise API; proprietary | Opposite deployment model. Luma is cloud-first and has pivoted focus to video; **not data-sovereign**; UE output is a splat renderer, not a game-asset mesh. Vitrine = on-prem, mesh-out. |
| **Polycam** | Mobile/web photogrammetry + cloud 3DGS; AEC/object capture | 15+ formats: PLY, OBJ, **FBX**, USDZ, glTF, DAE, STL, LAS, etc. (gated by tier) | **Cloud** processing (mobile capture) | Free (glTF only) → ~$13–27/mo Pro; proprietary | Strong mesh export incl. FBX, but **cloud pipeline** and no structured room+object scene graph or UE game-asset packaging. No on-prem/air-gap. |
| **KIRI Engine** | Mobile/web 3D scanner; 3DGS capture + on-phone 3DGS editing; v4.0 added AI-PBR photogrammetry | PLY (splat); OBJ/FBX/STL/GLB/glTF/USDZ via 3DGS-to-mesh | **Cloud** (some on-device preview/edit) | Free + subscription; proprietary | Best-in-class mobile 3DGS editing and 3DGS→mesh, but cloud-processed and consumer-scoped; no structured scene, no UE game-asset target, no on-prem. |
| **Scaniverse (Niantic)** | Free mobile app; **on-device** 3DGS + mesh; open SPZ format | Splat: PLY, SPZ; mesh: OBJ, FBX, GLB, USDZ, STL, LAS | **On-device** (mobile), sharing is cloud | Free; proprietary app; SPZ format open-source | Closest on *local processing* ethos, but it's a phone app for single captures — no server pipeline, no room+object structuring, no UE asset baking, no IT-signable container. |
| **RealityScan (Epic, ex-RealityCapture)** | Pro desktop photogrammetry; mesh/point-cloud; SLAM/LiDAR merge (2.1); COLMAP/NeRF transforms export | High-res textured mesh (OBJ/FBX/etc.); COLMAP + Radiance-Field transforms JSON for 3DGS/NeRF tools | **Desktop / on-prem** (local install) | Free <$1M rev; $1,250/seat/yr above; proprietary (Epic) | Genuine on-prem photogrammetry and free-to-Salford, and native UE affinity — **the strongest overlap on paper**. But it does *not* train 3DGS itself (exports COLMAP for external trainers), has no agentic orchestration, no automated room+per-object segmentation, no single-container mono-image. |
| **Agisoft Metashape** | Pro desktop photogrammetry; dense mesh/DEM/ortho; 3DGS export added in 2.2 | Textured mesh (OBJ/FBX/PLY), point cloud; COLMAP-compatible export for 3DGS | **Desktop / on-prem** (perpetual local licence) | Perpetual licence (~£4k Pro; Std cheaper); proprietary | On-prem and heritage-proven, but a *photogrammetry* tool, not a 3DGS trainer or a UE-asset pipeline; no orchestration, no object segmentation, no mono-image packaging. |
| **Postshot (Jawset)** | Desktop 3DGS/NeRF trainer with GUI; local training, live preview | `.ply`, `.splat`, `.ksplat` (splat only) | **Desktop / on-prem** (Windows) | Free (all tiers free since Sep 2025); proprietary; Windows-only | Best local 3DGS *trainer* UX, and fully offline — but **splat-only output** (no mesh/game asset), Windows-only, single-scene, no structuring or UE packaging. Complements rather than matches Vitrine. |
| **Matterport** | Cloud digital-twin platform for spaces; virtual tours | Proprietary hosted twin; mesh/point-cloud export on higher tiers | **Cloud** (hosted twins, ~$/mo) | Subscription (hosting-gated); proprietary | Deployment-model opposite: hosted, subscription, **not sovereign**; twins are for navigation/measurement, not game-asset meshes or per-object scenes. Used in museums for tours, not archival assets. |
| **CyArk** | Non-profit heritage-documentation *service*; LiDAR + photogrammetry at 200+ sites; Open Heritage 3D archive | Point clouds, meshes; CC-BY-NC archive downloads | **Service** (they capture); archive is cloud | Non-profit / grant-funded; data CC-BY-NC 4.0 | A *service + archive*, not software. Complementary (Vitrine could process/deliver assets); no self-hosted product, no UE game-asset pipeline, no 3DGS-native workflow (traditionally survey/LiDAR). |
| **Factum Arte / Factum Foundation** | High-end heritage facsimile studio; Lucida laser scanner, structured-light, close-range photogrammetry | Ultra-high-res surface/colour data → physical facsimiles | **Service / bespoke** | Non-profit foundation + commercial studio | Gold standard for *fidelity* and *facsimile*, but a boutique service with proprietary hardware, not a deployable pipeline; not 3DGS/game-engine focused. Different market (museography/facsimile vs. game-ready digital assets). |
| **Academic: Gaussian Heritage** (Del Bue et al., IIT, EU Horizon) | Research pipeline: 3DGS of museum scene + **integrated per-object segmentation** from RGB only; Docker-packaged | Instance-aware 3DGS + per-object models | **Local / Docker** (research code) | Open-source (research); EU-funded | **Closest conceptual analogue** to Vitrine's room+per-object idea, and Docker-packaged. But it's research code (splat/segmentation output, not baked UE game assets), no agentic controller, no hardened IT-signable image, no UE 5.8 delivery. |
| **Open-source stack** (Nerfstudio/gsplat, OpenSplat, SuperSplat, COLMAP) | DIY building blocks: 3DGS training (gsplat, Apache-2.0), editing (SuperSplat), SfM (COLMAP) | PLY/splat; mesh via add-ons | **Local / self-hosted** | Open-source (Apache-2.0 / BSD) | These are *the components Vitrine assembles* (LichtFeld Studio is itself a native 3DGS trainer in this family). Ahead on raw research velocity; behind on turnkey integration, structuring, and UE game-asset delivery. |

---

## 2. Category readout (detail + sourcing)

### 2.1 Consumer / mobile capture (Luma, Polycam, KIRI, Scaniverse)
- **Deployment reality:** all four are **cloud-processed except Scaniverse**
  (on-device) [Niantic; radiancefields]. For a data-sovereign, air-gapped
  heritage brief, Luma/Polycam/KIRI are structurally disqualified — captures
  leave the institution. Scaniverse processes locally but is a **phone app**, not
  a server pipeline; there is no institutional deployment, no orchestration, and
  no room+object structuring.
- **Mesh maturity:** Polycam, KIRI, and Scaniverse all export FBX/OBJ/GLB meshes,
  and KIRI's 3DGS→mesh + AI-PBR (v4.0, Sep 2025) is genuinely strong for objects
  [beforesandafters]. This is an area where consumer tools are **ahead of a
  bespoke pipeline** on per-object mesh quality and ease.
- **Luma's strategic drift:** Luma has pivoted its centre of gravity to
  **generative video** (Ray2/Ray3, $900M Series C Nov 2025, ~$4B valuation)
  [techcrunch]. The 3D capture app persists but is no longer the company's focus
  — relevant when assessing it as a long-term "competitor" for heritage.

### 2.2 Professional desktop (RealityScan, Metashape, Postshot)
- **RealityScan (Epic)** is the most direct on-prem overlap: free under $1M
  revenue (so free to a university), local desktop, high-quality textured mesh,
  native UE lineage, and now exports **COLMAP + Radiance-Field transforms** to
  feed 3DGS/NeRF trainers [cgchannel]. Critically it **does not train 3DGS
  itself** — it's the SfM/mesh front-end. Vitrine's differentiation vs. RealityScan
  is the *downstream* automation: 3DGS training, per-object segmentation, mesh
  cleanup, PBR bake, FBX packaging, UE 5.8 import, and agentic orchestration —
  none of which RealityScan does.
- **Metashape** added 3DGS/COLMAP export in **2.2** [github/agisoft], reinforcing
  that even incumbents now treat 3DGS as an export target rather than a native
  deliverable. On-prem perpetual licence; heritage-proven; but no scene
  structuring or game-asset pipeline.
- **Postshot (Jawset)** is the best *local* 3DGS trainer UX (GUI, live preview,
  fully offline, all tiers free since Sep 2025) but is **splat-only** output
  (PLY/SPLAT/KSPLAT), Windows-only, single-scene [jawset; thefuture3d]. It is a
  potential *component*/benchmark for LichtFeld's trainer, not a full competitor.

### 2.3 Digital-twin / spaces (Matterport)
- Matterport is **hosted-cloud, subscription, hosting-gated** [matterport/plans].
  For museums it delivers navigable virtual tours and measurement twins, not
  game-ready object meshes or sovereign archival assets. Deployment model is the
  antithesis of the brief.

### 2.4 Heritage-specialist services (CyArk, Factum, MYND, "digital surrogate" practice)
- **CyArk** (501c3, 200+ sites, 40+ countries) and its **Open Heritage 3D**
  archive (CC-BY-NC) are the reference *non-profit service + open archive* model;
  methodology is traditionally **LiDAR + photogrammetry**, not 3DGS
  [cyark.org; wikipedia]. Vitrine is complementary: it could be a
  *processing/delivery* layer, not a competitor to the fieldwork/archive mission.
- **Factum Arte / Factum Foundation** set the fidelity ceiling (Lucida scanner,
  structured light, close-range photogrammetry → museum-grade facsimiles) but are
  a **boutique service with proprietary hardware** [factumfoundation], a different
  market (facsimile/museography) from game-ready digital assets.
- The broader museum-informatics literature stresses **preservation-master file
  formats, long-term stewardship, and data-sovereignty** (esp. Indigenous
  materials, consent, repatriation) and warns there is **"no single perfect
  format"** for 3D preservation [DPC report; GRUR Int.]. This is exactly the
  governance surface Vitrine's on-prem/sovereign posture speaks to — but it also
  means Vitrine must answer archival-format and lineage questions, not just
  game-asset quality.

### 2.5 Academic 3DGS-for-heritage (the real intellectual peer set)
- **Gaussian Heritage** (Dahaghin, Castillo, Toso, Del Bue et al., IIT; EU
  Horizon) is the closest published analogue: RGB-only 3DGS of a museum scene
  **with integrated per-object segmentation**, no manual annotation,
  **Docker-packaged** for easy deployment [arxiv 2409.19039;
  github/contrastive-gaussian-clustering]. It validates Vitrine's core thesis
  (room + per-object structuring from splats) but stops at splats/segmentation —
  no baked PBR, no FBX, no UE 5.8 game-asset delivery, no agentic resilience.
- A wave of 2025–2026 heritage-3DGS papers exists: ISPRS Annals "3DGS for
  Enhanced Documentation of Cultural Artifacts" (2025), Frontiers "Immersive
  heritage through Gaussian Splatting" (2025), npj Heritage Science pieces on
  damaged-statue visualisation and dual-prior museum-artifact reconstruction, and
  a SIGGRAPH 2025 talk on **3DGS + game engines + crossmedia** heritage. The
  field is moving toward exactly Vitrine's intersection (3DGS → game engine →
  structured heritage scene), so novelty is *engineering integration + sovereign
  deployment*, not the raw idea. [copernicus; frontiersin; nature/npj; dl.acm]

### 2.6 Open-source components (what Vitrine stands on)
- **gsplat/Nerfstudio** (Apache-2.0, JMLR 2025), **OpenSplat** (CPU/GPU),
  **SuperSplat** (browser editor), **COLMAP** (SfM) are the commodity building
  blocks; LichtFeld Studio (Vitrine's vendored native C++/CUDA trainer) sits in
  this family. The open stack is ahead on research velocity and community; Vitrine
  adds turnkey integration, structuring, and delivery on top. [github/gsplat;
  jmlr; github/OpenSplat]

---

## 3. Vitrine differentiation (honest assessment)

**Genuine, defensible differentiators (the *combination* is the moat, not any single axis):**

1. **Single hardened on-prem "mono-image" (IT-signable, air-gappable,
   data-sovereign).** No mainstream competitor ships the *whole* capture→game-asset
   pipeline as one deployable, offline container. Cloud tools (Luma/Polycam/KIRI/
   Matterport) are structurally disqualified for sovereign heritage data;
   desktop tools (RealityScan/Metashape/Postshot) are on-prem but are *single
   apps*, not an integrated pipeline; Gaussian Heritage is Docker-packaged but is
   research code, not a hardened product. **This is Vitrine's strongest claim.**
2. **Capture-adaptive multi-pipeline.** Auto-routing between photogrammetry / 3DGS
   / mesh strategies per input quality (frame-QA gating, fallback env-mesh paths)
   is more than any single competitor does; commercial tools each pick one lane.
3. **Native UE 5.8 *game-asset* output — not a splat or point cloud.** Baked-PBR
   FBX + per-object meshes that import as standard game assets (Nanite), sidestepping
   the well-documented 3DGS-in-UE limitations (no Lumen GI/reflection interaction,
   view-dependent appearance baked in, ~180 MB/1M splats vs 5–20 MB textured mesh,
   no standard PBR/collision) [polyvia3d; strayspark]. Luma's UE plugin ships a
   *splat renderer*; RealityScan gives meshes but no automated per-object scene.
4. **Structured room + per-object scenes with lineage metadata.** Automated
   segmentation into individually-reconstructed, correctly-placed, textured
   objects plus a room mesh, carrying `v2g:*` provenance — matches the academic
   frontier (Gaussian Heritage) but pushed through to a delivered, textured,
   engine-ready scene graph.
5. **Agentic internal resilience.** An internal controller that recovers
   long-running GPU jobs (VRAM lifecycle, restart-per-object, oversight recovery)
   is an operational differentiator for unattended heritage batch runs — no
   competitor advertises this.

**Where competitors are genuinely ahead (do not oversell Vitrine):**
- **Raw capture UX & ergonomics:** Polycam/KIRI/Scaniverse mobile capture is far
  more polished and accessible than a server pipeline.
- **Per-object mesh quality out-of-box:** KIRI v4.0 AI-PBR and RealityScan/Metashape
  textured meshes are mature, tuned products; Vitrine's object quality is still
  capture-limited and iterating (Hunyuan3D/TRELLIS.2 per-object work in progress).
- **3DGS trainer polish:** Postshot's GUI/live-preview and gsplat's efficiency are
  ahead of a bespoke trainer wrapper on convenience.
- **Scale & track record:** CyArk/Factum have decades and hundreds of sites;
  Matterport has an enormous hosted footprint. Vitrine is pre-product (single-site
  R&D at Salford).
- **Archival-format story:** heritage-preservation practice values open,
  long-lived master formats; Vitrine's UE-game-asset focus (FBX + optional
  `.ksplat`, USD explicitly *not* the deliverable) is a *delivery* strength but a
  *preservation-master* question mark that needs an answer.

**Net positioning:** Vitrine is not competing on "best splat" or "best mobile
scanner." It occupies a **narrow, real gap**: *sovereign, on-prem, automated
capture→structured-textured-game-asset delivery for UE 5.8, with per-object scene
structure and lineage.* The nearest neighbours are RealityScan (on-prem + UE, but
no 3DGS/structuring/automation) and Gaussian Heritage (structuring + Docker, but
research-grade splats, no game-asset delivery). No single competitor spans both.

---

## 4. Market context (2025–2026)

- **Sizing (treat as directional; market-research figures vary widely and are
  low-confidence [uncertain]).** 3D-reconstruction technology market ~USD 2.15B
  (2025), CAGR ~9–13% to 2033; photogrammetry-software market cited at ~USD 4.1B
  (2024) → ~USD 12.7B (2032) at ~19% CAGR; **cultural-heritage cited as ~10% of
  the 3D-reconstruction market and among the fastest-growing segments**
  [coherentmarketinsights; verifiedmarketresearch; databridge]. Different reports
  disagree by 2–3×; use only as a growth-direction signal, not a hard TAM.
- **3DGS is going mainstream in engines, but as a *renderer*, not an asset.** UE
  (via third-party plugins), Unity, Unigine 2.20 (Jul 2025), Cesium (3D-Tiles LOD
  for splats, 2026) all added 3DGS support in 2025–26 — yet the documented
  limitations (no Lumen interaction, baked view-dependent appearance, memory cost,
  no standard PBR/collision) keep **mesh conversion the pragmatic path for
  game/interactive use** [cgchannel/unigine; cesium; polyvia3d]. This validates
  Vitrine's "splat-as-intermediate, mesh-as-deliverable" bet.
- **Incumbents are absorbing 3DGS as an export target** (Metashape 2.2,
  RealityScan COLMAP/RF-transforms), signalling that "3DGS capture" alone is
  commoditising; differentiation is moving **downstream** to structuring,
  segmentation, and engine-ready delivery — where Vitrine sits.
- **Heritage-specific research is converging on Vitrine's exact intersection**
  (3DGS + object segmentation + game engines + crossmedia; SIGGRAPH 2025, ISPRS
  Annals 2025, multiple npj Heritage Science 2025–26). The idea is no longer
  novel; **execution, sovereignty, and delivery integration are the moat.**
- **Governance tailwind:** growing emphasis on **data sovereignty, consent,
  repatriation, and preservation-master formats** in museum/Indigenous-heritage
  discourse [GRUR Int.; DPC] directly rewards on-prem/air-gapped tooling — the
  strongest structural argument for Vitrine's architecture over cloud incumbents.

---

## 5. Open questions / uncertainty flags

- **[uncertain]** Market-size numbers vary 2–3× across research vendors; no
  authoritative heritage-specific TAM found.
- **[uncertain]** Gaussian Heritage Docker packaging: the paper's contribution
  list and search snippets say "easily deployable Docker container"; the arXiv
  abstract page alone did not restate it — confirm from the repo README before
  citing as fact.
- **[uncertain]** Exact current Metashape/RealityScan on-prem licence pricing for
  a university buyer (list prices move); confirm with vendor quotes.
- **[gap]** No competitor found that markets an *agentic/self-healing* capture
  pipeline — either a real whitespace or simply not publicly described by others.
- **[gap]** Vitrine's **preservation-master / archival-format** answer (vs. the
  heritage-community "no single perfect format" concern) is not yet articulated;
  this is a likely reviewer/stakeholder challenge given USD is explicitly *not*
  the deliverable.
- **[to verify]** Whether any heritage institution has published a fully on-prem,
  air-gapped 3DGS→game-asset pipeline (closest is Gaussian Heritage, which stops
  at splats/segmentation).

---

## 6. Citations

**Consumer / mobile capture**
- Luma AI export/UE plugin: https://www.thefuture3d.com/software/luma-ai/ , https://lumaai.notion.site/Luma-Unreal-Engine-Plugin-0-41-8005919d93444c008982346185e933a1 , https://lumalabs.ai/interactive-scenes
- Luma pivot to video / Series C: https://techcrunch.com/2025/12/18/luma-releases-a-new-ai-model-that-lets-users-generate-a-video-from-a-start-and-end-frame/ , https://lumalabs.ai/ray2
- Polycam formats & pricing: https://learn.poly.cam/hc/en-us/articles/27756102599572-What-File-Types-Can-Polycam-Export , https://poly.cam/pricing , https://poly.cam/tools/gaussian-splatting
- KIRI Engine 3DGS/export/PBR: https://www.kiriengine.app/features/3d-gaussian-splatting , https://beforesandafters.com/2025/09/08/kiri-engine-4-0-major-updates-in-photogrammetry-and-ai-powered-pbr/
- Scaniverse (Niantic) on-device + SPZ: https://nianticlabs.com/news/scaniverse4 , https://radiancefields.com/platforms/scaniverse , https://github.com/nianticlabs/spz

**Professional desktop**
- RealityScan 2.1 / pricing / COLMAP+RF export: https://www.cgchannel.com/2025/11/epic-games-releases-realityscan-2-1/ , https://www.cgchannel.com/2024/11/epic-games-releases-realitycapture-1-5/ , https://flypix.ai/reality-capture-pricing/
- Agisoft Metashape 2.2 3DGS/COLMAP export: https://github.com/agisoft-llc/metashape-scripts/blob/master/src/export_for_gaussian_splatting.py , https://www.agisoftmetashape.com/agisoft-metashape-vs-gaussian-splatting-the-future-of-3d-reconstruction/
- Postshot (Jawset): https://www.thefuture3d.com/software/postshot/ , https://www.jawset.com/docs/d/Postshot+User+Guide/Getting+Started , https://radiancefields.com/platforms/postshot

**Digital twin**
- Matterport plans/pricing: https://matterport.com/plans , https://matterport.com/blog/subscription-pricing-update

**Heritage services**
- CyArk: https://www.cyark.org/ , https://en.wikipedia.org/wiki/CyArk , https://cyark.org/news/laser-scanning-for-cultural-heritage-applications
- Factum Arte / Factum Foundation: https://factumfoundation.org/the-foundation/ , https://www.factum-arte.com/pag/701/3d-scanning-for-cultural-heritage-conservation , https://en.wikipedia.org/wiki/Factum_Arte
- MYND heritage 3D services: https://myndworkshop.com/reality-capture-services-museums-heritage

**Academic 3DGS-for-heritage**
- Gaussian Heritage: https://arxiv.org/abs/2409.19039 , https://mahtaabdn.github.io/gaussian_heritage.github.io/ , https://github.com/mahtaabdn/GaussianHeritage
- ISPRS Annals 2025 (3DGS documentation of artifacts): https://isprs-annals.copernicus.org/articles/X-M-2-2025/215/2025/isprs-annals-X-M-2-2025-215-2025.pdf
- Frontiers 2025 (immersive heritage via 3DGS): https://www.frontiersin.org/journals/computer-science/articles/10.3389/fcomp.2025.1515609/full
- npj Heritage Science (damaged statues; dual-prior museum artifacts): https://www.nature.com/articles/s40494-025-02063-5 , https://www.nature.com/articles/s40494-026-02330-z
- SIGGRAPH 2025 talk (3DGS + game engines + crossmedia heritage): https://dl.acm.org/doi/10.1145/3721239.3734094

**Open-source stack**
- gsplat / Nerfstudio: https://github.com/nerfstudio-project/gsplat , https://www.jmlr.org/papers/v26/24-1476.html
- OpenSplat: https://github.com/pierotofy/OpenSplat
- SuperSplat: https://www.thefuture3d.com/software/supersplat/

**3DGS-in-engine limitations & mesh path**
- UE/Unity 3DGS guide + limitations: https://www.polyvia3d.com/guides/gaussian-splatting-unity-unreal , https://www.strayspark.studio/blog/gaussian-splatting-unreal-engine-5-capture-to-game-pipeline
- Unigine 2.20 3DGS: https://www.cgchannel.com/2025/07/unigine-2-20-adds-support-for-3d-gaussian-splatting/
- Cesium 3D-Tiles splat LOD (2026): https://cesium.com/blog/2026/04/27/3d-gaussian-splats-lod/

**Market context & governance**
- 3D reconstruction / photogrammetry market sizing: https://www.coherentmarketinsights.com/market-insight/3d-reconstruction-market-5685 , https://www.verifiedmarketresearch.com/product/photogrammetry-market/ , https://www.databridgemarketresearch.com/reports/global-3d-reconstruction-technology-market
- Preservation formats / data sovereignty: https://www.dpconline.org/docs/technology-watch-reports/2479-preserving-3d/file , https://academic.oup.com/grurint/article/71/12/1138/6692637
