# If a script stops

| message | do |
|---|---|
| `no such file` / `ffmpeg could not read audio` | ask for the right path; never copy or convert the source |
| `faster-whisper missing` / `CrisperWhisper missing` | run with `python3 "$PY"`, or the setup skill's step 3 |
| `no ElevenLabs key` (exit 2) / `HTTP 4xx`, `unreachable` (3) | drop `--engine scribe`, or re-save the key with the setup skill |
| build `ERROR` on a quote | fix that span's quote or add `occurrence`, build again |
| `cannot derive a silence threshold` / `marked no silence` | speech and background are under 10 dB apart: `ffmpeg -i <source> -af volumedetect -vn -f null -`, pass `--noise` about 10 dB above the mean |
| render `ERROR ...` | say it; re-run render once |
