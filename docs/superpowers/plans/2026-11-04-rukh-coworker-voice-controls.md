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

- [ ] Add failing tests for recognition, language selection, error recovery and read-aloud lifecycle.
- [ ] Implement typed browser speech helpers.
- [ ] Add the accessible dictation control to the existing composer.
- [ ] Add Read aloud/Stop controls to completed assistant replies.
- [ ] Add responsive styles using the existing Rukh tokens.
- [ ] Run focused tests, all web-editor tests, and relevant builds.
- [ ] Review the complete desktop/mobile interaction path and record exact-head CI evidence.
