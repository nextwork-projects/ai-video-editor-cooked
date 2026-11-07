# What verify says

`verify_cut.py` diffs the cut's transcript with the kept words. Exit 1 stops the chain.

- **MISSING**: a kept word is not in the render. Raise `--pad` (or narrow the span), rebuild, re-render.
- **SURVIVED**: a span to add for a real repeat or stumble, never one that cuts a kept line.
- **HEARD DIFFERENTLY** ("jev -> jeff") and filler notes are transcriber variance: no rebuild.
- **DOUBLED**: words said twice in a row. Natural ("very, very"): keep. A stumble: add its span.
- **N join(s) in speech**: listen. Clipped: `splice_check.py edits/<name> --fix`, re-render.
