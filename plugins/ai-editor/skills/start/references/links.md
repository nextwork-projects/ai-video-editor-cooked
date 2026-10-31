# Link items: notes, logins and exits

`links.py route` prints each item with a `kind`. The edges it cannot decide for you:

- An item with a `note` (Instagram profiles, Spotify, app stores, OneDrive): say the note once.
- `fetch` exit 3 means the site wants a login: ask in the question box "Use your browser's login for
  this one download?" (No, I'll download it myself (Recommended) / Yes, Chrome / Yes, another
  browser), and only on a yes re-run with `--cookies-from-browser <browser>`.
- Exit 1: say its message.
- Only download what the user may edit; a creator's video is for the teardown, not to re-edit.
