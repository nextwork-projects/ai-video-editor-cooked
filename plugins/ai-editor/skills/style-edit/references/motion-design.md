# Motion design

The default look and motion of every card over the footage, for every style (samples and the user's own),
unless the style's own measured fields say otherwise (style.json `graphics.entrances`, `exits`,
`secondary_motion`, `layout`). Read it before writing visuals.json (style-edit step 3, the `visual-prep`
and `template-filler` agents, the overlays skill). plan.py and the renderer already hold the numbers in
code; this file is what Claude decides with.

Measured from a working short-form studio's 300+ built clips and 298 timed card events. The numbers are
for a 1080x1920 frame.

## The four rules

1. **Always moving.** Nothing is a still on screen. A card enters, moves while it is up (a slow push or
   drift, its parts landing one by one) and leaves. A built animation beats a screenshot.
2. **On the word.** A card lands 0.1 s before the word that names it. Its parts (a counter's number, a
   note's line, a terminal's output, a mark) each land on their own word.
3. **Big, in the band above the head.** Cards fill the band from the safe zone's top (y 250) down to
   the hairline, as wide as the band (800 px centred, x 140-940), and tuck behind the hair. Never a
   small window in the middle of the band, never small chips in a row.
4. **Real things.** The real app, page, logo (in its brand colours, never black), the user's own photo
   or clip. A real screenshot with its logo beats a lone logo. Never a stock picture, an icon tile or
   words on a plain ground.

## What a beat becomes

Most beats are animations built from what the speaker says. In a card edit, aim for at least half the
cards moving formats, one capture per page, and a line with nothing to show left to the face.

**The order for a card edit beat.** Fill each beat in this order and stop at the first that fits: the user's added image or link, a real capture or screenshot, a logo (logo-pack), a motion clip (the motion skill builds one per moving beat), a visual template (`likes` counting, `progress` with the take's frames, `curve`, `side_by_side` of real frames). Never a card of words alone: nothing visual fits, no card on that beat. A `notes`, `terminal` or `chat` card of lines of words only is a text card: plan.py leaves it out and check.py plan FAILs it.

| the line says | the card | it moves by |
|---|---|---|
| a number of people, likes, views, comments | `likes`: the platform's logo, a red heart badge counting up to the number said, comments stacking in beside it | the count ticks on its word; each comment slides in and pushes the older ones down |
| something is being made, rendered, uploaded | `progress`: an app window, the label, a bar filling, the user's own frames lighting up as it passes | the bar fills over the card's life; the percent counts |
| smooth, motion, easing, animation | `curve`: an easing curve drawing itself, a dot riding it, the user's still moving on the same curve | the path draws; the dot and the still follow it |
| feedback, notes, fixes, steps the speaker lists | `notes`: a real notes panel, the speaker's avatar and the title in its header, beside each line the frame of the take where it is said (plan.py fills both from the take), a green tick drawing in on each line | lines land one by one, each tick draws in after its line |
| a command, a tool run, code | `terminal`: commands type in, output lands under them. A card edit: only as a motion clip with the real tool's logo or UI, never the bare window of words | typing, then the output |
| a question to an AI, a reply | `chat` | messages pop on their words |
| alerts, messages, sign-ups | `toasts` | each slides in from the top and stacks |
| before and after, this vs that | `side_by_side` with `"arrow": true` | a then b land, the arrow draws from a to b |
| how work moves between real things | `flow` | nodes land on their words, wires draw |
| the product, the repo, the doc | `capture` `shot` (a window cropped to the line) or `browser` (the page scrolling to the line), once per page | push into the mark; the browser scrolls and clicks |
| a brand in passing | `logo` (a big logo card, 200+ px, brand colours) | pops in on the word |
| the hook | a `title` card at the open | pops in, breathes, leaves |
| the ask ("comment edit") | a `cta` pill | pops in on the word |

Numbers on a card are only the ones said (or the user gave). A counter counts up to the said number from 0.

Each moving format above is the fallback: the motion skill builds a bespoke clip for each such beat (style.json
`motion`), lands its parts on their words and keeps this card only where the clip fails its checks.

## Look

- **Surfaces:** white cards (`#FFFFFF`) with a soft three-layer shadow, radius about 22-30 px; dark cards
  (`#111214`) for notes and terminals. A real app window has traffic lights and its name.
- **Ink and accent:** one ink (`#141414`) and at most one accent, used only when the colour is the
  information (red `#FF3040` for a like badge or a strike, green `#3DDC84` for "fixed"). Drawn boards:
  one ink plus one accent.
- **Type:** TikTok Sans, bold, sentence case. Text on a card is at least 30 px tall; a counter uses
  tabular figures so the digits do not jitter.
- **Title card:** one plain white box, black bold text, tight to the words, no border, no shadow, the
  user's emoji kept. It sits on the lower chest (its bottom on y 1440) for the first ~4 s; captions wait.
- **CTA:** a black pill, a small label over the big quoted word, white type, in the band above the head.
- **Captions:** one word, plain white, no box, no shadow, at the chin line under the mouth (face.py's head
  box), inside the safe zone. plan.py moves a caption line off the face by itself.

## Size and place

- The band: y 250 to the hairline, plus the tuck behind the hair (the head box's top 40%). plan.py grows a
  card down behind the hair as long as its key part (its marks, or the top of a window) stays clear.
- Crop a screenshot to the band's shape (about 2:1) round what the line is about, so it fills the band's
  width. A 16:10 window shrinks to half the width.
- Subjects at least 200 px; a subject logo about 240 px. Cards 800 px wide.
- Everything inside the reels safe zone, x 30-1010, y 150-1640.

## Motion

| part | default |
|---|---|
| entrance | a pop: scale 0.54 to 1 in 0.23 s, `power2.out`, fully opaque from the first frame (60%); or a rise from 4% below with a fade, 0.3 s `power3.out` (40%) |
| exit | out in 0.2 s, `power2.in`, scaling to 0.9 with a fade; the next card lands after it is gone (a swap in place, never two at once) |
| hold | a slow push (to about 1.03) or a sideways drift over the card's life, `sine.inOut`; its parts land one by one |
| parts | siblings 0.12-0.3 s apart; a counter ticks 0.5 s `power2.out` per step; a path draws `sine.inOut` |
| timing | card 0.1 s before its word, logo 0.3 s, a part on its word |
| holds | median screenshot 2.6 s, logo 2.6 s, photo 1.7 s; in a fast card edit 1-2 s each |
| density | a new card every 1-2 s in a card edit's run, then a stretch of face; never more than 8 s with no change |

Banned: `back`, `elastic` and `expo` overshoot on entrances, bounce, shake, motion blur, 3D flips, neon,
glow, gradients of our own, icon tiles, emoji outside the title, ALL CAPS labels, a zoom in and out per card.

## Check it moving

Stills hide flicker. Before showing a render, make consecutive-frame strips (10 fps, 0.4 s before to
1.1 s after) round at least three card entrances and look for: a card that pops on one frame and vanishes,
a blank frame between two cards, a part that never moves while held, a card over the face, a caption on
the face. Draw the safe-zone box on a still with captions.
