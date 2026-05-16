---
name: doc-to-sketch
description: Create final Chinese handdrawn technical article/PPT-style page images from articles, Markdown, PDFs, DOCX files, Feishu (飞书) document URLs, existing slide decks, course notes, scripts, outlines, or rough ideas. Use when the user asks to turn content into PPT/PPTX/slides/courseware/课件/演示稿/配图/效果图/帮我出图 in a refined Chinese handdrawn technical explanation style, to plan such pages, to choose page layouts from semantic content, or to generate complete image-model pages with Chinese text baked into the final visual. Default article outputs use 21:9 covers and 16:9 body illustrations.
---

# Doc to Sketch

Turn source material into a Chinese handdrawn technical PPT-style image deck. Supports direct Feishu document URL input — paste a link and say "帮我出图". Optimize for commercial delivery: clear narrative, semantic page archetypes, exact short Chinese text, refined handdrawn diagrams, and deck-level visual consistency.

## Operating Rule

When you have a built-in image generation tool, default production output is complete raster page images. Blog/article covers default to 21:9; body illustrations and standard deck pages default to 16:9. Each page is a final visual deliverable with both diagram and Chinese text included in the image.

When you do not have a built-in image generation tool, default output is a structured blueprint plus ready-to-use prompt files for each page. This blueprint is a complete, valuable deliverable — not a fallback or degraded product. It includes full page-by-page prompts that the user can take to any image generation service.

In this skill, "PPT", "slides", "page", and "deck" mean finished PPT-style visual page images, not editable presentation/document files. Do not route to presentation or document packaging merely because the user says PPT/PPTX/PDF. Editable PPTX, image-based PPTX, and PDF export are out of scope for this skill.

Do not use deterministic drawing scripts, HTML, SVG, canvas, or python-pptx as the primary visual generator for style samples. Deterministic post-processing is allowed for crop/resize, contact sheets, or exact text overlay when the generated image direction is accepted but image text fidelity is not good enough.

Produce a planning blueprint when the user asks to plan, outline, or design first, or when the current host does not have image generation capability. Production output is final PNG page images plus a contact sheet when there are multiple pages.

## Resource Map

Load only the references needed for the current task:

- `references/intake.md`: input types, missing-information checks, and concise clarification rules.
- `references/narrative-planning.md`: deck type selection and story structures.
- `references/slide-archetypes.md`: semantic mapping from content type to slide layout.
- `references/visual-dna-v6.md`: handdrawn Chinese technical PPT visual system and deck-level style lock.
- `references/output-quality.md`: output contracts and verification gates for final image pages.
- `references/prompt-patterns.md`: prompt templates for complete image-model slide pages.

Use `assets/theme-tokens.json` as the compact theme token file when writing prompts.
Use `assets/style-anchor-cover-21x9.png` as the active style anchor for blog/article cover and body illustrations.
When the current image tool supports local reference images, load or attach this style anchor before generation. When it does not, use the theme tokens plus the reference-match clause in `references/prompt-patterns.md`, and report the style as prompt-matched rather than image-referenced.
Do not use legacy bordered PPT reference images unless the user explicitly asks to recreate the older bordered look.

## Workflow

1. **Ingest material**
   - Read the provided content or attached file.
   - If the input is a Feishu/Lark document URL (`feishu.cn`, `lark.suite.com`, or `larksuite.com` docx/wiki URL), run `python3 scripts/feishu_fetch.py fetch "<url>"` to fetch the document content as Markdown. On first use, `fetch` opens browser OAuth authorization and then continues reading the document. If authorization cannot complete, inform the user and offer to proceed with manually pasted content instead.
   - If the input is `.pptx`, extract the source content and visual intent only; do not edit or package the PPTX inside this skill.
   - If the input is `.docx`, use the Documents plugin or skill to extract content.
   - If the input is `.pdf`, use the PDF/document tooling appropriate to the task.
   - If the input is plain text, Markdown, notes, or an outline, parse it directly.

2. **Run intake and gap diagnosis**
   - Read `references/intake.md` when the content is broad, incomplete, or the output requirements are unclear.
   - Determine topic, audience, scenario, target length, and source sufficiency.
   - Ask at most 1-3 questions only when the missing information materially changes the deck.
   - If no critical information is missing, proceed with reasonable defaults.

3. **Plan the deck narrative**
   - Read `references/narrative-planning.md`.
   - Classify the deck as teaching, persuasive, report, product explanation, or knowledge-card style.
   - Create a slide-by-slide spine: each slide must have one main point.

4. **Map each slide to an archetype**
   - Read `references/slide-archetypes.md`.
   - Choose slide layouts from the content semantics, not from a fixed template order.
   - Vary archetypes so the deck has rhythm.

5. **Apply visual DNA**
   - Read `references/visual-dna-v6.md`.
   - Use small exact Chinese text, fine handdrawn lines, light pastel marks, few characters, low visual heaviness, large negative space, and one shared master layout language across the whole deck.
   - Lock cross-page constants before generating: page role, canvas ratio, near-white paper tone, no-border default, page number, title treatment, title optical size, line weight, pastel palette, corner grid marks, character policy, and spacing rhythm.
   - Keep the outer shell fixed across pages: page number location, title block, underline, paper tone, corner marks, and visual scale. Vary only the middle semantic diagram area according to the content.
   - Treat blog/article visuals as two role-specific outputs by default: a 21:9 cover image and 16:9 body illustrations. Do not let body pages look like cover pages.

6. **Build output**
   - Before choosing an output path, determine your current image generation capability:
     - **Path A — Native image generation available**: You have a built-in image generation tool (e.g., you are running in Codex, Claude Code, or another host with native image gen). Proceed with full image production.
     - **Path B — Fallback API configured**: You do not have native image generation, but `IMAGE_API_KEY` and `IMAGE_API_URL` are set in the environment. Inform the user: "I can generate images using your configured API provider. This will send prompts to an external service and consume your API quota. Should I proceed?" Only call `scripts/generate_image.sh` after explicit user confirmation.
     - **Path C — No image generation available**: You have neither native image gen nor a configured fallback API. Deliver a **blueprint + prompt package** as the primary output. This is a complete, valuable deliverable.
   - If you cannot reliably confirm that you have native image generation capability, do not assume Path A. Default to Path C or ask the user to confirm.
   - **Path A execution** (native image gen):
     - Use one image generation call per distinct page brief, not a generic repeated template.
     - When the user asks for a cover plus body illustrations, generate the cover as 21:9 and body illustrations as 16:9 unless the user specifies otherwise.
     - Before generating multiple pages, write one compact deck style lock and reuse it verbatim in every page prompt. Add page-specific layout instructions only for the central diagram/content area.
     - Keep all visible Chinese text short and exact in the prompt. Include a `Required text only` list for each page.
     - If exact Chinese text is mission-critical or repeated generations render text incorrectly, reduce the text budget first. If needed, generate the accepted visual with blank label spaces and add exact text as deterministic post-processing; the final deliverable is still a raster page image.
     - Save final selected images into the workspace, and make a contact sheet when generating multiple pages.
     - Check actual image dimensions. If the image model returns near-target native sizes, report the actual size; normalize body illustrations to 1920x1080 and cover images to 2520x1080 only when strict delivery dimensions are requested.
   - **Path B execution** (fallback API): Same generation rules as Path A, but use `scripts/generate_image.sh --prompt-file <file> --size <WxH> --output-dir <dir>` for each page. Write each page prompt to a temporary file first.
   - **Path C execution** (blueprint + prompt package):
     - Deliver a structured blueprint: deck type, slide count, and for each page: title, main point, archetype, content blocks, visual brief, and exact Chinese text list.
     - Write a ready-to-use prompt file for each page (following `references/prompt-patterns.md`). Each prompt must be self-contained — a user can paste it directly into ChatGPT, Midjourney, or any image generation service and get a usable result.
     - At the end, include a "Next Steps" section:
       1. "Paste any prompt into ChatGPT/Midjourney/DALL-E to generate that page."
       2. "Or configure `IMAGE_API_KEY` and `IMAGE_API_URL` (see `.env.example`), then re-run this skill to generate all pages automatically."
       3. "Or switch to Codex / Claude Code for native one-step generation."
   - For explicit planning-only requests (user says "先规划" / "不要生图"), always deliver blueprint regardless of capability.

7. **Verify**
   - Read `references/output-quality.md`.
   - Check content accuracy, slide rhythm, Chinese text accuracy, visual consistency, style-anchor match, and commercial handoff readiness.
   - If verification fails, revise before final delivery.

## Defaults

Use these defaults unless the user says otherwise:

- Language: Simplified Chinese.
- Audience: Chinese learners with some technical curiosity but not necessarily expert depth.
- Deck length: 8-12 slides for an article, 15-30 slides for a course module, 5-8 slides for a short idea.
- Output: determined by host capability. With image gen: final PNG page images plus contact sheet and blueprint summary. Without image gen: structured blueprint plus ready-to-paste prompt files for each page.
- Blog/article visual split: cover image is 21:9; body illustrations are 16:9.
- Style: refined near-white Chinese handdrawn technical article/PPT illustration V6.

## Final Response

When finished, report:

- The output path taken (A: native image gen / B: fallback API / C: blueprint + prompts).
- The created image folder and contact sheet path (Path A/B), or the blueprint and prompt files location (Path C).
- The page count and deck type.
- Any important assumptions.
- Verification performed and any remaining risks.

For blueprint outputs (Path C or explicit planning-only), provide the blueprint directly, include ready-to-paste prompts, and identify the next steps for the user to generate final images.
