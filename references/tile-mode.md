# List tiles

Use this mode for a square thumbnail beside one entry in a website list. Works, articles, life notes, and any other list share the mode.

Skip this mode for a full-page illustration, for icon editing, and for photo processing.

## From the content to one object

1. Draw one everyday object. Use at most three elements.
2. Put the accent on a real part of that object.
3. Before you draw, check that the grouping is not a religious, national, or political symbol.

When the user names the object and the accent part, use that pair.

When the user does not name an object, read the title and the one-line summary. Read the body when that is what the user gave. Propose two or three pairs. Each pair is one object and the part that carries the accent. Recommend one pair. The user picks, or you go ahead with the recommendation and name the pair you used.

Examples:

- 作品「桌面计时器」：一只厨房计时器，强调色在旋钮上。
- 文章「为什么要写交接单」：一张单子，强调色在回形针上。
- 生活「周末放风筝」：一只风筝，强调色在风筝尾巴上。

## Style profile

A style profile is a JSON file of site data. Every list thumbnail on one site shares one profile, so the site has one way of drawing. Another site uses another profile.

The skill stores no site color, size, wording, or object. Those values live in the profile.

Look for a profile in this order:

1. Use the file the user names.
2. Otherwise use `tile-style.json` in the current project.
3. When the project has no profile, ask for the colors and the display sizes, or copy a base style into a draft and ask the user to confirm the draft. Do not apply `examples/tile-style.example.json` unless the user asks to start from that file.

Keep one profile for every list on that site. A change to the profile is a change of style. Redraw the set. Do not mix thumbnails from two profiles.

Fields:

- `palette.ink`, `palette.accent`, and `palette.accent_name`. `accent_name` is a short English hue name.
- `palette.mat.light`, `palette.mat.dark`, `palette.paper.light`, `palette.paper.dark`, `palette.page.light`, and `palette.page.dark`.
- `sizes`. Pixel sizes for the review sheet. The last item is the smallest size the site displays.
- `candidates`. Default count. When the field is absent, use 4. When the user states a count, use the user's count.
- `prompt`. Use one of the two shapes below. When both are present, `lock` wins.
  - `{ "preset": "<base style name>", "vars": { "context": "...", "set_rule": "..." } }` fills a base style.
  - `{ "lock": "<full style-lock text>" }` is the style lock, verbatim. Use it to reproduce a finished style word for word.
- `gates`. Optional thresholds. A missing key uses the default in `scripts/tile_review.py`. The defaults are copied below.
- `anchors`. Paths of thumbnails this site already accepted. The review sheet shows them beside the candidates. A relative path starts at the profile file. Paths passed to `--anchors` come after these paths.

`examples/tile-style.example.json` is one finished profile. It is an example. It is not a default.

## Base styles

Base styles are files under `assets/tile-styles/`. `fine-pencil.json` has a style-lock template and a Brief template.

The lock template uses `{ink}`, `{accent}`, `{accent_name}`, `{context}`, `{set_rule}`, and `{min_size}`. The Brief template also uses `{subject}` and `{accent_part}`. The templates name no site, no object, and no color.

Fill the lock from the profile:

- `{ink}`, `{accent}`, and `{accent_name}` come from `palette`.
- `{context}` and `{set_rule}` come from `prompt.vars`.
- `{min_size}` is the last `sizes` entry written as digits plus `px`.

Fill the Brief from the chosen object. `{subject}` is the object. `{accent_part}` is the part that carries the accent. Append one pose or angle clause to the Brief for each candidate. Keep the style lock the same for every candidate.

The full prompt is the style lock, a blank line, and then the Brief.

Ask the user when a placeholder has no value. Do not leave a brace in the prompt, and do not invent a site, a color, or an object.

## Run

1. Choose a short ASCII slug and tell it to the user. Write the run under `output/tiles/<slug>/`.
2. Generate one image per count. Save `cand-1.png` through `cand-N.png`.
3. Write every full prompt to `prompts.json` in that directory, as a list of objects with `file` and `prompt`.
4. Run the review script:

```bash
python3 scripts/tile_review.py output/tiles/<slug> --profile tile-style.json [--anchors a.png b.png]
```

The script writes `candidate-review.png` and `review.json` in that directory. It does not call the network and it does not generate an image. `--profile` is required. The script has no built-in color.

5. Read the sheet and the `flags`. Recommend one primary and one alternate. Give one sentence for each reason. The user chooses.
6. Copy the chosen file to `source.png` in the same directory.

This mode does not export layers and does not make hover motion.

Generate pixels with the host image tool. Do not call an image API from this mode.

## Judge

Keep a candidate when all of these are true:

- At the smallest `sizes` entry, a person can say what the object is.
- Next to the anchors, the contour weight and the amount of ink match.
- The accent is in one place, and that place is part of the object.
- The drawing is not an emoji, a flat vector icon, or a 3D render.

`review.json` holds one object per candidate. The object is a set of marks. It does not name a winner.

## No image tool

When the host has no image tool, deliver the N full prompts and this command:

```bash
python3 scripts/tile_review.py output/tiles/<slug> --profile tile-style.json
```

The user saves the images as `cand-N.png` and runs the command.

## Gate defaults

`scripts/tile_review.py` reads `gates` from the profile. Missing keys use these values:

```text
border_band: 0.05
border_alpha_max: 8
border_clear_min: 0.995
accent_distance: 60
accent_share_max: 0.12
ink_core_min: 6
```

`borderClear` is true when the share of pixels with alpha at or below `border_alpha_max`, inside the outer band, is at least `border_clear_min`. The band thickness is `border_band` times the image width, on every edge.

`subjectSpan` is the long side of the opaque bounding box divided by the long side of the canvas.

`accentShare` is the share of pixels with alpha at or above 128 whose Euclidean RGB distance to `palette.accent` is at or below `accent_distance`.

`inkCore` and `accentCore` are measured after a uniform scale that makes the long side equal the smallest size. A pixel counts when its alpha is at or above 128. Accent pixels sit within `accent_distance`. Ink pixels are the other counted pixels. Each core is the pixel count of the largest 8-connected component.

Flags:

- `border-not-clear` when `borderClear` is false.
- `accent-too-large` when `accentShare` is above `accent_share_max`.
- `ink-core<N@S` when `inkCore` is below `ink_core_min`. `N` is `ink_core_min`. `S` is the smallest size.

## Script exits

Exit 1 when `--profile` is missing, the profile is missing or invalid, Pillow is missing, the directory is missing, or the directory has no `cand-*.png`. A missing `--profile` tells the user to copy `examples/tile-style.example.json` and confirm it before use.

Exit 2 when any candidate or anchor image cannot be read.
