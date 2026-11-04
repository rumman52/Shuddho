# Rukh AI Coworker voice controls — implementation plan

**Base:** `main 9811c7179ce0980aac6f49179f1f84f8c01736d1`  
**Branch:** `feat/rukh-coworker-voice-controls-20261104`

## Goal

Add optional browser-native dictation and read-aloud controls to the existing Coworker conversation interface without changing the server, provider, database, or execution model.

## Constraints

- Microphone access starts only after the user presses Dictate.
- Speech is transcribed into the draft only; it is never sent until the user presses Send/Save.
- Audio is not uploaded, stored, or logged.
- Read aloud uses the browser's installed speech synthesis; it is not represented as generated AI audio.
- Preserve Bangla and English selection, device-language fallback, keyboard/touch access, existing theme tokens, and graceful unsupported-browser states.
- Stop/abort recognition on user stop, route/thread changes, composer disablement, and unmount.
- No new runtime dependencies, backend endpoints, provider calls, schema changes, or feature-gate changes.

## Acceptance

1. Standard and WebKit-prefixed SpeechRecognition are feature-detected; unsupported browsers receive an explicit disabled state.
2. Only final transcript segments are appended; interim text is not inserted and repeated final results are not duplicated.
3. User-selected Bangla/English or the device locale is passed to recognition.
4. Permission, microphone, no-speech, and network errors have specific recovery copy.
5. Completed AI replies expose Read aloud/Stop controls when browser speech synthesis is available.
6. Read-aloud and dictation clean up on unmount; controls have accessible names/status and at least 44px touch targets.
7. Focused frontend tests, the complete web-editor suite, and Coworker/Editor builds pass.

## Tasks

- [x] Add behavior tests for recognition, language selection, error recovery and read-aloud lifecycle; verify RED on test-only commit `a980a09` in CI run #41809748139.
- [x] Implement typed browser speech helpers with standard/WebKit feature detection and final-segment deduplication.
- [x] Add the accessible dictation control to the existing composer.
- [x] Add Read aloud/Stop controls to completed assistant replies.
- [x] Add responsive styles using the existing Rukh tokens and 44px touch targets.
- [ ] Re-run the complete web-editor tests, root test-and-build and mandatory Coworker job on the final exact head.
- [ ] Review the complete desktop/mobile interaction path on a fresh Vercel preview and test real microphone/TTS behavior. The latest preview is currently blocked by Vercel's daily deployment limit.

## Verification record

- **RED:** [CI run #41809748139](https://github.com/rumman52/Shuddho/actions/runs/41809748139), test-only commit `a980a09aea31700776f64d59cc603c98ada6b054`. The frontend test step failed on the expected new speech-helper assertions and the missing read-aloud control before production implementation was present.
- **GREEN (predecessor):** [CI run #41810362794](https://github.com/rumman52/Shuddho/actions/runs/41810362794), implementation commit `3f5fef0ecf27b997d7035661844b131606671086`. The complete `Frontend tests and builds` job passed. Subsequent commits add Bangla TTS locale detection, mobile select sizing and this handoff; exact-head CI remains required.
- **Deployment limitation:** Vercel's GitHub bot reported the free daily deployment limit (>100) after an earlier preview was ready. The Render staging Postgres database is suspended after expiry on 31 October. No staging or production activation is claimed.
- **Scope boundary:** browser speech APIs only. No audio upload, persistence, provider-generated audio, backend endpoint, migration, or feature-flag change.
