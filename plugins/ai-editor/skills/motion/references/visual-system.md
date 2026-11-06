# The visual system

The rules every motion clip follows. Each one is a correction a working short-form studio made across
300+ built clips, not a preference someone chose. Where a rule carries a number, the number was measured.

A clip plays in one of two places:

- **a card** over the footage, in the band above the speaker's head (the card edit and every style that
  lays cards on the word). Canvas about 1200x500, shown about 760 px wide. Its ground is the look's card
  ground (white) or the real surface; never cream paper, which this editor bans as a generated-look tell.
- **the whole frame or a panel** (the 50/50 style). Canvas 1080x1920, fitted by its ink band. Its ground
  is the look's paper.

The rest is the same in both.

## Tokens

The look comes from `looks.md`: `default` unless the style names another. Default:

| token | value | what it is |
|---|---|---|
| ground | `#FFFFFF` | a card's surface, every frame (the other cards in the edit are white too) |
| paper | `#FDF8EC` | the ground of a whole-frame or panel clip |
| ink | `#171614` | everything we author |
| frame | 30 fps | 1200x630 card, 1080x1920 frame, 1920x1080 wide |
| type | TikTok Sans | only where text IS the mechanism |

The authored accent is near-black. Not a brand colour, not an accent palette.

## Colour

**Ink on the ground is the default. Colour is a deliberate exception.**

Real brand logos carry the frame's colour, and that is the point: colour appears exactly where a real
product appears and nowhere else. An **authored** colour is spent only where the colour IS the
information: a threat, a pass/fail verdict, a state change, a like badge.

The test: if the colour could be swapped for ink without losing meaning, it should be ink. One colour per
clip at most. Never a gradient, never a palette, never an accent of ours. Stop red `#FF3040`, fixed green
`#3DDC84`, and only for a stop or a pass.

## Logos

1. Real marks, in their real brand colours. Never recoloured, never redrawn.
2. **A missing mark is a sourcing problem, never a licence to substitute.** `simple-icons` dropped some
   marks (OpenAI, Slack, Salesforce, Twilio) over trademark requests; they still exist elsewhere. Fetch from
   iconify (`logos:` and `simple-icons:`) or the vendor's brand page. capture.mjs and the logo-pack skill
   put the edit's marks in `images/logo-*.svg`. A generic glyph in a named product's slot is wrong.
3. Marks do **not** share a viewBox (simple-icons are 24, others 256 and up). Size them **optically, not
   numerically**: a dense closed mark next to a spiky star needs to be smaller to read as the same weight.
4. One mark means one thing. Never the same logo for a company and its product on screen together.
5. Prefer a brand's mark over its wordmark: a wordmark reads as text on screen.

## Icons

Drawn icons are for generic things: file, key, lock, cpu, shield, folder, envelope, monitor, server,
database, browser, user, cloud, globe, clock, plug, home, queue, arrow, card, gem, network.

Spec: **1.6 stroke on a 24 viewBox, round caps, single ink, no fill** except tiny dots. Draw anything
missing to the same spec so the set reads as designed.

**Check a new icon through the renderer, not ImageMagick.** ImageMagick's SVG renderer drops strokes and
paints only fills, so a stroke-based set previews blank; it also chokes on some valid arc syntax.

## Labelling

**Real logo, then drawn icon, then redesign the beat.** A word is not the third option.

When three of something are needed, three *different real products* are more honest than three identical
boxes: an app stack becomes Notion / Linear / Stripe, a package source becomes GitHub and npm.

## No text

Zero authored text. The picture carries the beat; the words are the speaker's voice and the captions,
both outside the clip.

The only exception is text that **is** the mechanism: a real counter, a draining balance, real code on a
screen, a typed command, a comment or note the speaker reads out, the words in a real capture. A label
naming the thing on screen is a caption. Mark mechanism text with a `real-text:` comment.

Also banned: the **eyebrow stack** (a small muted line above a big dark line, top-left: the generated
explainer tell), and the **caption pill** (white-on-black rounded box).

A clip with no glyphs drops the font link and the `font-family` entirely.

## Floating and drift

Three layers, on different nodes:

| layer | where | what |
|---|---|---|
| shadow | outer `.node` | `filter: drop-shadow(0 14px 18px rgba(60,45,20,0.16))` |
| entrance | outer `.node` | the slide or fade in |
| drift + swing | inner `.hov` | the idle float and pendulum |

`drop-shadow`, never `box-shadow`: box-shadow draws a rectangle behind a transparent SVG instead of
following its silhouette. Entrance on the outer node, drift on the inner. **Never both on one element**:
they fight and one silently wins.

Float goes on everything, 16-37 px on a 1920-tall frame (the template scales it to the canvas). Swing goes
on a **subset** hung from an origin above itself (`transformOrigin: '50% -70%'`) so it reads as swinging
from a string. If everything swings, nothing reads as hanging. **Never swing a member of a grid.**

## Motion

Smooth, sliding, never jarring. Long ease-outs; elements glide and settle. No bounce, no pop, no hard
cut-in. `power3.out` for entrances, `sine.inOut` for idle, `power2.inOut` for travel.

Nothing is ever stationary. A frame where everything has settled reads as a still image.

### A beat change the viewer SEES is a push, not a cross-fade

Inside one clip, a fade-out and a fade-in are two unrelated events at the same spot: either a blank frame
between them, or both pictures on screen at about 28% each. The stage is `overflow: hidden`, so the
outgoing beat LEAVES through the top while the incoming one arrives from the bottom, same duration, same
ease:

```js
function pushUp (outSel, inSel, t, d) {
  d = d || 0.58;
  tl.to(outSel, { y: -H * 0.375, duration: d, ease: "power2.inOut" }, t);
  tl.to(outSel, { opacity: 0, duration: 0.001, ease: "none" }, t + d);
  tl.fromTo(inSel, { y: H * 0.375, opacity: 1 },
    { y: 0, opacity: 1, duration: d, ease: "power2.inOut", immediateRender: false }, t);
}
```

`opacity` belongs in BOTH vars of the `fromTo`: a property named only in `from` tweens back to the
element's current value. A push crosses the stage edge on purpose. Where a change is hidden (behind a
full-face cutaway, between cards), a fade is fine. **Any fade that stays gets a direction**: out drifts up
34 px, in arrives from 34 px below.

## Scale

A phone screen. First renders come out too small far more often than too large.

**200 px is the floor for any element the beat is ABOUT** (on a 1920-tall frame; on a 630-tall card,
about 130 px, which plays at about 90 px over the footage). It is not a blanket floor: texture and
background layers at 55-140 px are what separate the best clips from the worst. A frame with nothing under
150 px has no texture layer.

**A logo that is the SUBJECT of a beat wants about 240 px**, not 200 (card: about 160). At 150 it reads as
a speck beside the object it is meant to own.

**Stroke weights**, so containers do not recede into the ground:

| what | weight |
|---|---|
| containers: cards, slabs, enclosures | **6 px** |
| connectors, routes, traffic paths | **3 px** |
| icons | their 1.6-on-24 spec, at whatever the scale-up gives |

Set container strokes in absolute px, never inherited from the icon spec: a 1.6-on-24 icon blown up 6.5x
lands at about 10 px, and a container left at 2.5 px dissolves beside it.

## The safe zone

A clip is judged inside a phone app that draws its own furniture over it. Everything a viewer must read
stays inside **x 30-1010, y 150-1640** of the 1080x1920 frame (style-edit's `SAFE`, checked by `check.py`).
A card already sits inside it; a whole-frame clip keeps its art inside it. Check a render with the box
drawn: `motion.py strips <render> --at <t> --safe`. The speaker's body may run below the line; the face,
the artwork, the marks and the captions may not.

## What is on screen has to be the thing the sentence is about

The test, per beat, out loud: **what does this picture make the viewer understand that the words alone do
not?** If the answer is "it shows the topic exists", the beat is decoration and it is wrong, however real
the capture is. A count of repositories answers how many exist; a line about the danger of installing one
needs the install command and the advisory for that exact package.

- **Show the act, not the category.** The install command, not the directory of things you could install.
  The invoice, not a picture of money.
- **Name the specific thing.** "this package, Critical" beats "these can be dangerous".
- **A capture must be legible at phone size or it is texture.** Check the crop, not the panel.

## One exhibit a beat, unless the second one explains it

Two pictures on screen at once are two things to look at and no instruction which. The viewer picks one,
misses the other, and the sentence lands on neither. It also halves the size of both.

Two exhibits are right when the second is part of the SAME explanation: the struck-out install line with
the chatbot it sends you to instead, two advisories that together say "more than one", a capture with the
artefact it produced beside it. Test: can you say in one clause what the pair means together ("not this
one, that one")? If it needs an "and also", they are two beats: split on the sentence turn, and pay the
halved dwell back out of the beat (drop what the picture already says), not out of the reader.

Several marks on ONE capture are one exhibit. The mark is not the exhibit.

## Make it fill the frame

The panel is already as wide as it can be, so **the only lever on apparent size is the crop**. A capture at
its native crop lands as a small object floating on the ground; the same capture cropped to the part the
beat is about fills the card at 3-4x the type size. **Crop to the thing, then let the width do the
enlarging.** If a capture still leaves more than about a third of the stage empty, it is cropped too
loosely for a phone. In a card: no inner margin of ground, the content runs edge to edge.

## Tilted cards, for a beat about how much of something there is

A single cropped strip of UI is a fact; it can only show one. For quantity, two or three REAL pages as
tilted cards:

```css
.card { position: absolute; will-change: transform; }
#c-a { left: 52px;  top: 70px;  width: 560px; height: 640px;
       transform: perspective(1600px) rotateY(9deg) rotate(-5deg);  z-index: 2; }
#c-b { left: 462px; top: 160px; width: 560px; height: 640px;
       transform: perspective(1600px) rotateY(-9deg) rotate(4deg);  z-index: 3; }
```

- **The tilt lives on a wrapper.** `.card` carries the perspective, the `.panel` inside keeps its
  `overflow: hidden`, the `.push` keeps its scale. All three on one node fight.
- **Both cards scroll, at different rates** (-300 px and -180 px over 2.45 s): alive from frame 0, and the
  rate difference stops it reading as one flat image.
- **They drift apart, not together**: `xPercent ±1.4`, `yPercent ∓1.2` on `sine.inOut`. Parallax.
- **Rotation eats width**: a 560x640 card at 5° needs about 60 px more than its box.
- **The strike is the punctuation**: a red line drawn along its length across both cards on the word that
  turns the sentence.

A screen recording of the same pages is better still when it exists.

## A hub of role marks, for a beat about who a thing is for

The thing itself in the middle (a document or the product's mark); the roles arrive around it on an arc,
one at a time, each a person glyph carrying a real product logo (a code bracket, then Figma, Notion, Gmail,
Linear). The centre is drawn first and stays; the ring builds while the speaker lists them, so the picture
finishes on the last word. Reach for it on any line that means "this is not only for X".

## The full-face cutaway settles, it does not sweep

A cutaway resolves out of a slight punch-in and shrinks back; it never crosses the frame (1080 px in 0.5 s
is the fastest, most whip-prone motion in a cut). From-state in CSS (gotcha 12):

```css
.slab { opacity: 0; transform: scale(1.06); }
```
```js
function slabIn (sel, t, d) { tl.to(sel, { opacity: 1, scale: 1, duration: d || 0.55, ease: "power2.out" }, t); }
function slabOut(sel, t)    { tl.to(sel, { opacity: 0, scale: 0.965, duration: 0.55, ease: "power2.inOut" }, t); }
```

## A crop that is a strip is not a card

Cropping tight to a headline gives a 1150x148 strip; two stacked read as labels floating on the ground.
Take the crop from the full capture at the width it was captured (headline, the block under it, about
1280x620): it lands as a card with proportions a viewer recognises as a real page.

## A drawing that reads as a glitch loses to the UI that says it

A drawn theft of keys (a box, dashed slots, chips flying out past a red line) has to be decoded, and
mid-flight it looks like a rendering fault. The real configuration tab that asks for the token and marks it
**required** says it with nothing to decode. **Before drawing a mechanism, ask what the real product says
about itself**: a permissions screen, a required field, a scope list, a consent dialog.

When a drawing IS the only option, nothing travels across empty space. Objects arriving and settling read
as motion graphics; objects flying between two positions read as a glitch.

## A fading cutaway hides nothing until it is opaque

A cutaway that FADES shows the stage through it for the length of the fade, so a swap inside that window
ghosts two pictures. Swaps go inside the **fully opaque** window. Keep the opacity leg short (0.26 s) and let
the scale settle run longer (0.55 s).

## The space above the speaker is never empty

Any layout that puts the speaker under a stage owes that stage content for every second it exists. A beat
with nothing to show does not hold an empty band: the face takes the whole frame instead. Check it as a
timeline pass: list every second, mark what is above the speaker, and give every unmarked run an exhibit or
the face.

## A short capture does not leave the rest of the stage empty

A one-line verdict, a secret field, a command: cropped tight, they leave empty ground above them. **Give the
leftover space the mark, not the capture**: a tick or a cross drawn along its length at 200-300 px above
the card, landing on the word. A drawn tick is a stroke with `stroke-dasharray` and `strokeDashoffset` to 0
over about 0.45 s, and it is the one mark allowed on a capture that already says the thing: it says the
RESULT as a shape.

## A named platform gets its real mark, landing on its word

A platform the speaker names has a mark, so it gets used, never a neutral drawn stand-in. Over the
footage, the marks sit straight on the frame, one landing per name as it is said, no container around them.

## A built clip fills its card at EVERY moment, not by the end

A clip that ACCUMULATES down a column is empty at the top of its run, so the first half of the beat is a big
box with a speck in it, and `measure_ink.py` cannot see it (it reports the union across the run). **A clip
that lands several pictures replaces rather than accumulates**: one object at a time, each filling the
card, handing over to the next. Accumulation is allowed only when it IS the mechanism (a counter's field
growing, a list the line counts out); then the card is still full on frame one. Check it the way it is
watched: sample four or five points, each alone, at the card's size.

## A GIF, once, on the beat that is a feeling

A GIF belongs on a beat about how something FEELS (the cost landing, the exasperation), where evidence
would be weaker. It is wrong on any beat that needs to be believed. Loop it to the beat's length
(`ffmpeg -stream_loop 6 -i in.gif -t 2.10 -vf "scale=900:-2,fps=30" out.mp4`), keep its own colour, one a
video at most.

## A capture upscales 1.5x, never more

Past 1.5x every letter edge goes soft and reads as a bad photo of a screen, worse than small. Take a bigger
crop of the same capture, or re-capture at a higher device scale factor (2x on a 640 px window gives 1280).

## Cards may overlap. Their TEXT may not

Overlap is fine when what overlaps is frame (a corner, an empty margin). Cards carrying headlines are
separated, tilted apart with a real gap: two cards where three would fit.

## An annotation layer is not free

**Mark a capture only where the capture does not say it.** If the finding is already printed, coloured or
boxed in the real UI, a mark is clutter. One box around the thing named is the ceiling.

## No free-floating label pills

A black capsule floating over a screenshot is the most generated-looking object in the kit. The one survivor
is a node label inside a drawing, when deleting it would stop the picture parsing.

## A connector touches what it names

A static connector starts ON its source's edge and ends ON its target; a line stopping in space reads as
unfinished. A leader ends at the pill's edge. A refusal mark crosses the line it refuses, square and
centred. A dimmed branch dims to **0.45**, not 0.30.

## Watch the animation FINISH

**A draw-on, wipe, stagger or scroll ends at least 0.25 s (8 frames) before its beat leaves.** A strike
authored to end three frames before the cut ships as a stub. `check --at-transitions` samples exactly these
moments, and motion.py place starts the clip late (`start_s`) when its motion would run past the card.

## When a mark earns its place, it names, it never states a statistic

A pill carries a NAME in one to three plain words. A number in a capsule reads as an infographic badge.
Red is for a stop, not for emphasis.

## Composition

Where the marks go. Measured across 25 clips ranked by eye, then checked against numbers from the render.

### The gates (`check_composition.py`, advisory for card clips)

| gate | threshold |
|---|---|
| dead band | no empty horizontal run taller than **0.25** of the height |
| dead strip | no empty vertical run wider than **0.30** of the width |
| ink coverage | **>= 6%** of the frame at the densest frame |
| stroke range | **>= 3** distinct rendered stroke widths, heaviest / lightest **>= 2.5** (tall), **>= 1.45** (wide) |

Rendered, not authored: an authored `stroke-width` times its svg's own scale. The dead band sorts clips
almost exactly as the eye does (best 0.11-0.20, worst 0.31-0.43). Ink extent does not substitute: one card
plus a second card far away spans the frame and is the cheapest picture in the set.

These gates are for DRAWN beats. A clip that is mostly a captured screen scores 0 stroke weights (a CSS
border has no stroke-width) and often fails the band; judge it by "Captured screens" below.

### Density floor

**Eight distinct drawn objects at the densest moment** (a logo, an icon, a card, a connector run, a rule;
a stack of greeked lines in a card counts as one). Necessary, not sufficient: nine identical squares at
equal spacing read as cheap as two objects.

### No empty containers

**A drawn container holds at least three marks.** One glyph centred in a big box is the most reliable cheap
frame there is. If the beat has nothing to put inside the box, the box is not the drawing.

### Silhouette

**At most half the drawn objects may be a plain rounded rectangle.** Composite silhouettes: a package with a
lid, an envelope with a flap, a monitor with a neck and foot, a speech bubble with a tail, a bucket with no
top edge, a tree, a spine.

### Overlap

**At least one pair of objects crosses or occludes.** Objects that never touch read as a labelled diagram.

### Repeats

An evenly spaced run of identical shapes reads as a diagram at any count. Scatter them (offsets and
rotations), or run a tone gradient through them packed edge to edge, or make them different real products.

### Stroke weight is a depth control

Something sits deliberately lighter than the connector weight, to make a background plane: a 0.72 px
greeked line is the texture layer, not a mistake. The best clips run five or six weights over a 10x spread.

### The ground

The ground is a material in the composition, not the margin round it. In good frames it shows through
between scattered elements; in cheap ones it is one unbroken rectangle under the drawing.

## Captured screens

A real screenshot or recording is a node like any other: the same card, stroke, shadow and drift. On a
paper ground it does not get its own colour temperature:

- **Light capture on paper: multiply it by the paper**
  (`magick shot.png \( +clone -fill '#FDF8EC' -colorize 100 \) -compose Multiply -composite out.png`):
  white lands on the paper, brand colours survive. **Dark capture:** `+level-colors '<ink>,<paper>'`. Never
  `+level-colors` on a light capture (it desaturates the brand colour) and never `-modulate` (white only
  greys). On a white card ground nothing is graded: white is white.
- **Frame it:** `rx: 28`, 6 px ink stroke (or the look's card radius with no stroke on a white card), 30 px
  of ground padding round a light capture, a dark capture flush. A drawn browser shell only when the point
  is that it is a browser. **Never cut the background away**: a masked-out text block reads as type we set.
- **Scale it:** body text lands at **16 px or more on a 1080-wide frame** (on a card: 24 px or more on the
  1200 canvas, so 16 on screen): `source_text_px * (display_width / source_width) >= 16`. Taller than about
  500 px on frame: **crop, don't shrink**.
- **Float it:** drift on `.hov`, 16-37 px. **No swing on a captured screen**: a tilted screenshot reads as
  a crooked photo.
- **Disqualified:** nav chrome, sidebars, cookie banners, consent bars, floating CTAs (crop them out or drop
  the capture); a whole long page squeezed into a card (a page whose length is the point is a `browser`
  scroll); body text that cannot reach 16 px; a second saturated colour against the beat's own; a capture of
  a surface the line does not cite (the crop is the authority: if the product does not say it, the script
  bends, not the crop).

### Moving captures (a `<video>` in a clip)

```html
<video id="v1" data-start="0" data-duration="6.0" data-media-start="2.0"
       data-track-index="0" src="assets/clip.mp4" muted playsinline></video>
```

- `muted` and `playsinline` are both required. `data-media-start` is the in-point, `data-start` the
  composition time, `data-duration` the window. One `data-track-index` per video (same-track clips cannot
  overlap). Frame 0 already shows the in-point.
- **Grade with ffmpeg before the render**, never a CSS filter: light,
  `colorchannelmixer=rr=..:gg=..:bb=..` = paper / the capture's own white (read it from a frame's
  histogram); dark, `colorlevels` from the capture's black point onto the two tokens. Conform `fps=30`, strip
  audio (`-an`) in the same pass. Judge the grade against the paper in the same render (the renderer writes
  tv-range bt709, so `#FDF8EC` comes back as 247,246,231).
- `overflow: hidden` on the card wrapper rounds the video's corners.
- **Media running out inside the window holds its last frame**; pick a window whose last frame is worth
  holding. **The window closing while media remains leaves an empty card**: give the video a duration that
  covers its idea, or fade the `.node` at the same instant.
- A recording cannot be cropped to the sentence because the sentence moves: crop to a sub-region first,
  size second, in the same ffmpeg pass. Disqualified: text that cannot reach 16 px, a cursor that leaves
  the crop, two `<video>` with identical src and timing (lint `duplicate_media_discovery_risk`), a source
  that is not 30 fps, an audio track.

## Photos of the speaker

Only when they are genuinely part of what is shown: their own result, their own screen, a person-shaped node
in a diagram about people. Not decoration. No stock photos of people: a generic person is a stick person in
the ink style.
