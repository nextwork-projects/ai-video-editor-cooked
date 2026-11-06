# Visuals

The full rules for `edits/<name>/visuals.json`. Templates, props, transitions and marks are in
`motion.md`; this file says what to put on screen and where it comes from.

## Anti-generic rules

An edit that looks like every other AI edit is a failed edit. Never by default:

- **Lucide icon tiles.** A row of white rounded squares with stock icons in them is the AI look.
- **Emoji.** Not in a card, a label, a title or a caption.
- **Generic stock photos.** No Unsplash, Pexels, Shutterstock, iStock, Getty, Pixabay or Freepik.
- **Purple-to-blue gradients**, and any saturated purple/blue accent the user did not choose.
- **Near-black glass panels with a neon accent** (the old `glass` look).
- **Inter** (or Roboto, Poppins, Montserrat, Open Sans, Arial) as the display face.
- **Text slides.** A big number, a headline or a list on a plain coloured ground. Pictures carry the
  beat: at most about 4 words of text on any card, as a label.
- **A house palette.** Beige paper, poster reds, decorative accent bars. Overlays are neutral chrome;
  colour comes from the real content.
- **The AI title card.** A big centred heading with a small grey or lowercase line under it, a short
  accent rule under a heading, a flat saturated colour ground (poster green, red, blue), a default
  geometric or neo grotesk (Archivo, Geist, Inter and their likes) as the display face. Each one reads
  as AI-made on its own. Headings are left-aligned, set in the source's own type or a serif
  (Newsreader is the default display face), with no rule under them.

`plan.py` enforces them before placing anything (`anti_generic` and `profile.resolve_look`):

| rule | what plan.py does |
|---|---|
| capture of a stock-photo site | skips the beat, warns |
| an anim card whose only pictures are `{"icon": ...}` | skips the beat, warns. `"allow_icons": true` on the beat lets it through when nothing real exists and the icon sits inside a type layout |
| emoji in any text prop | strips them, warns |
| look accent or ground in the purple-blue range | uses the preset's, warns (the user's own brand kit is exempt) |
| `glass` preset not named by the creator's style or the brand kit | uses `editorial`, warns |
| a generic font from a creator's measurement | uses the preset's grotesk, warns (the brand kit is exempt) |
| a colour the profile avoids | uses the preset's, warns |
| a style.json `look` naming a flat saturated ground (`poster-red`, `poster-green`, `poster-blue`) | uses `neutral`, warns (the user's own brand kit is exempt) |
| a display face from the default grotesks (Archivo, Geist, Manrope, DM Sans, Space Grotesk, ...) | uses the preset's (Newsreader), warns (the brand kit is exempt) |
| a type card (`slam`, `title`, `counter`, `bar_chart`, `line_chart`, `checklist`, `phrase_mark`, `versus`, `lower_third`, `pile`, the old `keyword`, `steps`, `race`): removed from the product | skips the beat, warns with the overlay format to use instead |

There are no type templates left to draw a heading. `quality.py` (run by
`check.py render`) WARNs a settled card that shows a big centred heading with a small line under it
and a short solid bar, or one saturated colour over 60% of the card.

The profile's `avoid` answers (`emoji`, `stock`, `icons`, `colors`) set these per user; emoji,
stock and icons are on by default. `check.py render` also WARNs an AI-default look in the render.

## What goes on screen, in this order

1. **The user's own assets.** Their photos, screenshots and b-roll (the profile's `assets_dir`, or
   files they hand over). Put them in `images/` and list them in `images.json`. A clip of their own
   goes in a `video_card`.
2. **The real thing, captured.** A product, website, doc or article that is named: a `capture` beat
   (the real page, cropped to the evidence, with marks), drawn as a floating `shot`, a `browser`
   window that scrolls to the sentence, or a `sticker`. A quoted X post: a `post` beat. An app: an
   `app` beat. A video: a `youtube` beat. A repo: a `github` beat.
3. **A stat is shown inside its real source.** The page that published the number, captured, with
   the number ringed or highlighted as it is said. Never a big number on a plain ground.
4. **UI recreated from real parts.** When the speaker describes what an app does: `chat` (the app's
   real name and logo, messages in the speaker's words), `terminal` (real commands), `toasts` (the
   app's real notifications). The words on them are the speaker's or the product's own.
5. **Real logos.** A brand named in passing: a `logo` beat. Several named together: a
   `logo_cluster` around the head. How work moves between named things (a router picking a model, a
   deploy pipeline): a `flow` diagram of their real logos, each step or pick landing on its word
   (motion.md "The diagram").
6. **No type cards.** Words on a ground (a slam, a title, a counter, a chart, a checklist, a lower
   third) were removed: say it with the real source, captured and marked.

Icons come last: only when none of the above exists, never as a row of tiles.

## The look

No house palette. `plan.json "look"` is the `neutral` preset: white cards (or the real app's own
surface, as captured), near-black text, a soft realistic shadow, no coloured grounds, no accent bars.
The one colour plan.py adds is the highlighter (`mark`), in this order: the profile's brand kit
accent > the copied creator's measured accent (the most saturated `graphics.palette` colour) >
natural marker yellow. Rings, boxes and underlines on captures are white over a dark outline, so
they read on any page. A style.json `look` that names a preset (`editorial`, `poster-red`, ...)
opts in to that preset whole.

## Where each card sits

Overlay first: the speaker stays on screen and every card floats over the frame in the free space
around the head, never over it (face.json). `plan.py` (`place_overlays`) puts each card in the region
its picture fills best: above the head (wide pictures: a page, a chat, a post), or beside it (tall
ones: a phone screenshot, a toast stack, a cropped sticker) on vertical; left or right of the head
on wide. A `logo_cluster` takes the whole frame; on vertical its logos are 20% of the width each,
spread over a band from 17% to 83% above the head, on wide they sit round the head. A `flow` is an
overlay in the band beside or above the head: the speaker stays on screen. An `icon_burst` on vertical
sits in the split panel when the layout is split, else a box. A beat with its own `box` keeps it.

| card | where |
|---|---|
| captures (`shot`, `browser`, `sticker`), `chat`, `terminal`, `toasts`, `social_post`, `side_by_side`, `video_card`, `flow` | the free region around the head it fills best |
| `logo_cluster` | the whole frame; vertical: big logos in a centred band above the head; wide: round the head |
| `logo` / `logo_sting`, `arrow_callout`, `caption_page` | their own small box |
| `flow`, `icon_burst` with `"layout": "scene"` | a full-frame cut-away, only when the user asked for one (`check.py plan` FAILs a scene no beat asked for) |

`"layout": "split"` (vertical only) puts a card in the split layout's top panel; `--layout split`
does it for the whole edit. Neither is the default any more.

## Card edit: pictures only

A style.json `"card_kinds"` that leaves out `"text"` (the sample Card edit: `["capture", "logo", "photo",
"animation"]`; a user's own `own-card-edit` style with no card settings takes the sample's, profile.py
`like_sample`) makes every card a real picture: a screenshot of the page, app, repo or post named, a logo, the
user's photo, or an animation built from real parts. In that style:

- capture.mjs shoots a `sticker` beat as a `shot`, at a 640 px viewport (the page's narrow layout, as a phone
  shows it), and with a `find` mark and no `clip` frames a band-shaped window (1.5:1, at most 1.2 times the mark wide) round the mark, so the
  named thing fills the band above the head.
- plan.py drops a re-set sentence (a capture.mjs sticker, `xh` in images.json), draws a sticker of the page as
  a shot, and keeps a screenshot whose small text would read under 28 px as a picture (its push-in carries the
  mark) instead of cutting it to a line of words; check.py plan FAILs a sentence on white and WARNs small text.
- No card of words alone: plan.py leaves out a `terminal` or `chat` with no logo or picture and gives a `notes`
  card the speaker's avatar and a frame of the take beside each line; check.py plan FAILs any words-only card.
  Fill each beat in this order and stop at the first that fits: the user's added image or link, a real capture or screenshot, a logo (logo-pack), a motion clip (the motion skill builds one per moving beat), a visual template (`likes` counting, `progress` with the take's frames, `curve`, `side_by_side` of real frames). Never a card of words alone: nothing visual fits, no card on that beat.
- route.py prints the allowed kinds; a text card or chart in a creator's mix routes to `capture:shot`.
- `"behind": true` tucks the card behind the speaker's hair (matte.py), and `graphics.per_min` sets the rate.
- The rate is the look: 30 a minute is a card about every 2 s. plan.json carries it (`card_rate`) and check.py
  plan FAILs any stretch with no card longer than `card_gap_s` (2 x the mean gap; the opening title counts).
  Fill each one, in this order: the user's own images and links (assets.json), then captures of what the line
  names, then animations built from its words. A song or demo the speaker stops to play gets its item's own
  card held through it (`hold_s`). No card holds longer than twice `card_gap_s` (one card per item of a list).
- No card is on screen for under 1.2 s (plan.py grows a shorter one into the free time round it, check.py FAILs
  one left short). A picture is fitted at its own ratio, centred in its box (plan.py reads the size of an image
  that has none), and a `list` is set at the captions' size at least.

A line that names nothing real gets a logo of a brand it names or an animation of the idea.

A logo in a card edit is a card of its own on white in the band (plan.py `logo_items(card=True)`), not the small
tile above the captions. Three word overlays go with the cards (plan.json `texts`, remotion `Texts.tsx`), each
inside the reels safe zone:

| beat | draws |
|---|---|
| `{"kind": "title", "text": "line one\nline two"}` (no `word`: from 0 s; with `word`, `nth`: on that word) | one plain white box, black bold type, tight to the words, emoji kept, no border or shadow, on the lower chest with its bottom on the safe zone's bottom line, `hold_s` (3.8). Captions wait while it is up; cards above the head carry on |
| `{"kind": "cta", "text": "\u201cedit\u201d", "label": "comment", "word", "nth"}` | a black pill, the small label over the big word, white type, in the band above the head, `hold_s` (2.4). A card up then ends as it lands |
| `{"kind": "list", "items": [{"text", "word", "nth"}], "until"?: word}` | a running numbered list at the left, each line on its word, held to `until` (else the end); under the chin, else just above or below the captions, never over the head; skipped in a shot too close for it |
| `{"kind": "stamp", "word", "nth"}` | a red circled X drawn over the card up on that word ("that one doesn't count") |

Title, cta and list words are the speaker's (a title may be the video's promise in a few of their words); the
title keeps its emoji, every other text loses them.

## From the teardown

A creator-teardown style.json carries measured fields beyond captions and pace. Each one is used only when
it is present and only when the blend took its part (`blend.take`; a style.json with no `take` counts
every part it has). Absent, the defaults above and in motion.md stand unchanged.

| style.json field | part | drives | where |
|---|---|---|---|
| `graphics.entrances[]` | entrances | one measured entrance per box card, dealt in her shares (smooth weighted round robin, deterministic): kind, GSAP ease, duration, overshoot (inside the ease), side and distance, fade. Replaces the default drop-in; a `cut` shows the card on its word | plan.py `creator_motion` -> `props.enter`; motion.ts `fitIn` |
| `graphics.exits[]` | entrances | the same for leaving, ending as the card's time runs out | `props.exit`; motion.ts `fitOut` |
| `graphics.secondary_motion` | entrances | what a card does while up: `still` (no camera), `push` (scale only), `drift` (move only), `video` (the default push and drift stand in for a moving picture) | `props.ambient`; motion.ts `camera` |
| `graphics.kinds` | graphics | the formats preferred for her mix: UI recording -> `capture:browser` / `video_card`, real screenshot -> `capture:shot` / `capture:sticker`, text card and chart -> `capture:sticker` of the real source (text cards are never built), photo -> `capture:shot`, logo -> `logo` / `logo_cluster`, b-roll -> `video_card`. route.py prints her mix for Claude to lean towards; plan.py deals a format to a capture that has none | route.py `prefer`; plan.py `kind_formats` |
| `graphics.layout` (`grid`, else `zones_pct`; `median_box`) | layout | each free region round the head is scored by its area x (0.25 + how much of her graphics sat there), so her regions win when they fit. Same free regions as always: never over the head, inside the app's safe zones. `median_box` is the box when there is no face.json | plan.py `place_overlays` / `heat` |
| `graphics.per_min` | graphics | her rate (under the user's own `cards.per_min` / `cards.on`, never the default style's cap; plan.py `card_rate`): route.py marks that many sentences `want` for this length (named first, then the longest, spread out); the style check counts the plan's cards against it, and her kinds and zone too | route.py `want`; style_check.py |
| `pace.cut_kinds` | pace | with `zoom.on: every_cut`, only her `zoom-punch` share of the cuts may change the zoom; the rest are hard holds. `zoom.per_min` still spaces them | plan.py `place_zooms` |
| `pace.median_shot_s` | pace | a punch zoom holds about one of her shots, then comes back out by itself (each change is a punch) | plan.py `place_zooms` |
| `zoom.ease` | pace | a push zoom plays on her fitted ease, at least 0.8 s each way (a punch keeps its 0.16 s eased move; motion.md "Zooms") | plan `zooms[].ease`; StyleEdit `zoomScale` |
| `camera.pan_per_min` | pace | that many slow sideways drifts of the footage a minute, 1.5 s each, 2.5% of the width, out and back (overlay layout only) | plan `pans`; StyleEdit `panAt` |
| `sound.sfx_per_min` | sound | the cue budget (0 is allowed: she uses none) | plan.py `place_sfx` |
| `sound.kinds` | sound | only cues that sound like hers: whoosh -> whoosh-in/out, pop/click/ding -> pop, impact -> hit/zoom, riser -> hit | plan.py `SOUND_CUES` |
| `sound.on_graphic_pct`, `on_cut_pct` | sound | 0 drops the card cues (or the zoom cues) | plan.py `place_sfx` |
| `sound.music.level_db` | sound | how far under the speech `sfx.py music` sets the bed (else 18 dB); with no bed laid, plan.py prints her share and level | sfx.py `music`; plan.py `main` |
| `hook.winner.first_graphic_s` (+ `control`) | graphics | a soft rule: check.py plan WARNs when the first card lands more than 0.5 s after her winners' median | plan `targets`; check.py `check_plan` |

`camera.push_per_min`, `graphics.blur_behind_pct` and `graphics.crop_palette` are not used yet. Banned looks
stay banned whatever she measured: plan.py `pick_look` keeps only her saturated accent from the palette (no
cream ground), profile.py `creator_look` refuses Inter and the other default grotesks as a face, and her
text cards become stickers of real sources.

## Beats

Every beat anchors to a word as it appears in captions.json (the transcript may misspell a name:
anchor on its spelling). Always set `nth`. Pacing (SKILL.md step 3): a card on each beats.json `want`
(a copied creator's rate), else where a sentence names something real; never two at once, none in the
first second unless it is the hook's subject. Set `hold_s` so the card is still up on its last
word (plan.py warns when it is not); leave it out to use the creator's measured hold. Leave the
speaker alone for a few seconds between runs of scenes.

```json
[{"word": "Jev", "nth": 1, "kind": "capture", "url": "https://typesafe.ai", "clip": [40, 320, 900, 400],
  "format": "shot", "props": {"label": "typesafe.ai"},
  "marks": [{"kind": "highlight", "find": "System One Model", "at_word": "model"}]},
 {"word": "40", "nth": 1, "kind": "capture", "url": "https://typesafe.ai/...", "format": "browser",
  "marks": [{"kind": "ring", "find": "40-200x", "at_word": "200"}]},
 {"word": "Before", "nth": 1, "kind": "anim", "type": "chat",
  "props": {"app": "Jev", "logo": {"logo": "typesafe"}, "messages": [{"from": "user", "text": "small task", "word": "small"},
            {"from": "app", "text": "use Haiku", "word": "Haiku"}]}}]
```

### capture

`"format"`: how the card is drawn (default `shot`):

| format | draws | `props` |
|---|---|---|
| `shot` | the capture drops in just before its word with a soft depth shadow, the camera pushes into the first mark's region as it lands and the card punches on that word | `label` (the site's name) and `logo_src` (its real logo, a file in `images/`): the source row on a white card above the capture; `zoom` (1.45, clamped so the mark stays in view) |
| `browser` | the page inside a browser window with its URL, scrolling to the mark while a cursor travels there and clicks as it lands | `url` (defaults to the beat's), `cursor` (true) |
| `sticker` | the one sentence holding the first mark, set alone on white in the page's own font at the width that reads largest in the band above the head (x-height about 28 px on 1080 wide; plan.py warns under that), on a white card under the source row, dropped in just before its word, punched as the mark lands | `label`, `logo_src` (as `shot`), `rotate` (0); beat options `fit` ([900, 340] display px), `keep_ground` (the page's own ground, not white); `crop` `[x, y, w, h]` only to hand-crop a full capture |
| `plain` | the old flat capture card | |

The real page, cropped to the part that is the evidence. `"clip": [x, y, w, h]` in page px, or
`"selector": "css"`. `"width"` sets the viewport (default 1000): a narrow one (400-550) reflows docs
so their text reads on a phone. `"highlight": "the exact sentence"` (as it reads on the page) makes
the card travel down to that sentence and sweep a highlighter over it; give it `hold_s` of 3 s or
more. `"marks"` draw on the capture (motion.md "Capture marks"): give each `"find": "text on the
page"` and capture.mjs measures its `rect` (the match inside the clip first), or give `rect` in the
PNG's px yourself. Land each mark on a word with `"at_word"`. Every mark must add something the
capture does not already show.

Cookie banners: capture.mjs hides the common consent managers by selector and clicks a reject
(else accept) button by its text, twice. Look at every capture anyway; if something still covers
it, change `clip`, `selector` or `wait_ms` and run it again.

Captures and logos are kept for 7 days in `~/.ai-video-editor/cache/` and reused by any video with the same
beat (URL, size, marks, format) or brand. A changed beat shoots again; to shoot an unchanged beat again (the page
changed, or loaded badly), run `capture.mjs edits/<name> --fresh`.

Not sure which sentence is the evidence? Add `"page_text": true`, run capture.mjs, then
`route.py highlight edits/<name> images/capture-N-x.text.json "<what the speaker says>"`.

### Free sources (no keys)

| kind | give | gets |
|---|---|---|
| `post` | `url` of an X post, optional `highlight` (the phrase said) and `text` (to verify) | the post's real name, handle, avatar, text, likes, replies and date from X's public embed endpoint into `images/post-<id>.json`, rendered as a `social_post` scene. capture.mjs fails the beat if `text` or `highlight` is not in the post |
| `app` | `app_id` or an App Store `url`, `brand` | the app icon as `images/logo-<brand>.png`, the first screenshot at full size as a card |
| `youtube` | `url` or `id` | the video's thumbnail (maxres, else the next size) as a card |
| `github` | `repo` (`owner/name`) or `url` | the repo's social card as a card |

Never invent data. A figure, a quote, a like count or a date on screen comes from one of these
sources or from the speaker's own words.

### Sourced proof

A line that names a person and what they said gets their real words: the clip from their talk or
interview, found to the second. A line that quotes a post gets the real post. Never a paraphrase on
a card. All free: yt-dlp, YouTube's auto-captions, ffmpeg, X's public embed endpoint.

```bash
python3 "$S/source.py" search "<who> <topic>"                       # id | length | views | channel | title
python3 "$S/source.py" quote "<youtube url>" "<4-8 words they said>"  # each place it is said, best first
python3 "$S/source.py" clip edits/<name> "<youtube url>" <start> <end>  # the line quote printed
python3 "$S/source.py" credits edits/<name>                          # credits.txt, before handing over
```

- **Pick the source:** the person's own channel or the event's official upload, not a re-upload.
- **quote** reads the auto-captions, which time every word, and slides a window the length of the
  phrase over them, scored by word match (a misheard word still lands). It prints the score, the
  times and the `clip` line padded 0.4 s each side. Captions are not verbatim: under 0.80, try other
  words from the same sentence. `--lang` for a talk not in English.
- **clip** downloads only that section, 1080p at most, to `images/clip-<id>-<second>.mp4`. Show it as
  a `video_card` on the line that names them: `{"word", "nth", "kind": "anim", "type": "video_card",
  "props": {"src": "images/clip-<id>-<second>.mp4", "label": "<Name>, <where>"}}`. The card plays muted:
  it shows who said it while the speaker says the line. Keep it 2-8 s.
- **A post:** a `post` beat with `highlight` the phrase (above). capture.mjs falls back to the public
  fxtwitter API when X's endpoint returns nothing.
- **Credits:** every clip goes into `credits.json` (the video's url at that second, channel, title,
  times); `credits` writes `credits.txt` from it and every `images/post-*.json`. `chapters.py --intro`
  puts it under the chapters in `description.txt` (render.md). Hand `credits.txt` over with the render.
- **Exit 3** (a login, a bot check, a 403 or a rate limit): ask in the question box before re-running
  with `--cookies-from-browser chrome` (or their browser). Rate limited: wait 10 minutes first. One
  `quote` per video, never a loop of searches.
- Someone else's clip: short, credited, there to back a point. Say once that reuse is the user's call.

### logo

Every time a brand or product is named in passing: `{"kind": "logo", "word": "Claude", "nth": 1,
"brand": "claude"}`, plus `"domain": "example.com"` for brands Simple Icons lacks. It runs in its
own lane above the captions for 1.2 s and is dropped while a scene or the split panel is up.
When the logo-pack skill ran (`edits/<name>/logos.json`), its files are already checked in `images/`:
route.py lists each sentence's `logos` (the `brand` to use), and each `together` group is one `logo_cluster`.

### Overlay formats (anim)

| type | shows | props |
|---|---|---|
| `chat` | an app's chat thread from its real parts: the user's message pops, the app types its reply | `app`, `logo`, `model?`, `messages: [{from: user|app, text, word?}]` |
| `terminal` | a real terminal: commands type in, output lands | `title?`, `lines: [{text, kind: cmd|out, word?}]` |
| `toasts` | the app's real notifications drop in and stack | `items: [{app, src|logo, title, body?, word?}]` |
| `logo_cluster` | real logos drop in round the head on their words, bare with a soft shadow | `logos: [{logo|src, word?}]` (plan.py adds `head`) |
| `side_by_side` | two real screenshots drop in side by side | `a: {src, size, crop?, label?, marks?}` (`crop` [x, y, w, h] image px: the part that reads on a phone), `b: {...}` (`src`: a capture's file, `images/capture-<i>-<word>.png`) |
| `video_card` | a short real clip in a rounded card | `src` (a video in `images/`), `size?`, `start_s?`, `label?` |
| `social_post` | a `post` beat's real post; when the whole post would read too small on a phone, only the sentence with the highlight, ellipses where text is left out (`"excerpt": false` keeps it whole) | from images/post-<id>.json |

Text on every overlay is the speaker's or the product's own words, a few words per label.
Every overlay drops in just before its word, punches on its hit words and leaves upward (motion.md
"Overlay formats").

### anim

One idea per card, only words and numbers the speaker said. `type` is any template in motion.md;
the eight original names still work. Parts land on their own words (`"word"`, `"off_word"`), and a
part's picture is `{"logo": ...}` or `{"src": "images/..."}`. `*word*` sets the stressed word in the
serif italic accent. A prop that takes a file (`avatar`, `logo_src`, `src`, `a_src`, `b_src`) may be
given as `{"logo": "brand"}`.

## Proposing the beats cheaply

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/route.py" beats edits/<name>
```

Splits captions.json into sentences and marks the profile's named things in each, into
`edits/<name>/beats.json`. Claude picks one route per sentence from that file, leaning to the creator's
`graphics.kinds` mix it prints when edits/<name>/style.json has it ("From the teardown"). Then only the template props are left: the `template-filler` agent
(haiku) fills them from beats.json, or Claude does.

## Template-filler contract

The pick-to-beat table and its rules: `shapes.md`.

## Safe areas

On vertical, nothing a plan draws leaves the reels safe zone: x 30-1010, y 150-1640 of 1080x1920
(`plan.py` SAFE: 5.6% left, 13.1% top, 13% right, 25% bottom). Cards and captions are centred, so they
keep the 13% margin on both sides (x 140-940); an overlay beside the head may reach x 60. That keeps
the top bar, the like and share rail and the username and description clear, and `check.py plan`
FAILs any card (behind cards too) or caption width outside it. Overlays never cover the head. A
scene's content sits in the renderer's scene box, inside the same zone. In split, a panel card fills
the top panel between the top 13.1% and the seam.
