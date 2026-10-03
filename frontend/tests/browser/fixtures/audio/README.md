# Audio transcription test fixture

`dictation-fixture.wav` is the speech fixture for `tests/browser/audio-transcription.spec.ts`
(Stage 6 task 6.4's audio journey; Stage 12 remediation Tranche 3, A21).

It is **synthetic speech**, generated offline with espeak-ng. It is not a recording of a person.

## Spoken text

> Audio note for chapter three. The lighthouse keeper, Marigold, lit the lantern at midnight. She wrote in the logbook that the fishing boats came home safely before the storm.

The spec passes only when the transcript contains at least **6** of these 9 words (case-insensitive):

`lighthouse`, `keeper`, `marigold`, `lantern`, `midnight`, `logbook`, `fishing`, `boats`, `storm`

The threshold allows for minor recognition differences on a synthetic voice. A silent or tone-only file cannot pass, because faster-whisper's voice-activity filter returns an empty transcript for it.

## File

| | |
|---|---|
| Format | WAV, PCM 16-bit, mono, 22050 Hz (espeak-ng's native rate; faster-whisper resamples) |
| Duration | 14.84 s |
| Size | 654,424 bytes |
| SHA-256 | `e355436e96aee6bda98640a2092f2f6c4e23332cf036ee6cc2cb7f2bc7bc4b64` |

## Regenerating it

espeak-ng is a tool for making this file only. It is **not** a NarratIQ runtime dependency, and nothing in the application uses it. It was generated on Ubuntu 22.04 with espeak-ng `1.50+dfsg-10ubuntu0.1` (eSpeak NG 1.50):

```bash
apt-get install -y espeak-ng
espeak-ng -v en-us -s 140 -g 4 -w dictation-fixture.wav \
  "Audio note for chapter three. The lighthouse keeper, Marigold, lit the lantern at midnight. She wrote in the logbook that the fishing boats came home safely before the storm."
sha256sum dictation-fixture.wav
```

With the same espeak-ng version the output is byte-identical (verified 2026-10-03). Another version may produce slightly different audio: re-run the spec, then update the checksum above.

If you change the text, also update `KEYWORDS` and `KEYWORD_MIN` in the spec.

Licence: espeak-ng is GPL-3.0-or-later. That licence covers the program, not the audio it produces.
