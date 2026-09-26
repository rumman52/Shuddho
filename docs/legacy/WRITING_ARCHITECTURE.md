# Shuddho repaired architecture

Shuddho is an original Bangla writing assistant. The repaired architecture keeps the existing Python Bangla NLP app as the linguistic source of truth and makes the TypeScript API a common gateway for web, extension, and future clients.

## Current repaired architecture

```mermaid
flowchart TD
  WebEditor[Web Editor / Vite] --> Gateway[Common TypeScript API Gateway]
  Next[Next App MVP] --> Gateway
  Extension[Chrome Extension] --> Gateway
  Future[Future Desktop/Mobile/API Clients] --> Gateway
  Gateway --> Prefs[Preferences Store MVP]
  Gateway --> Docs[Document Store MVP]
  Gateway --> Events[Privacy-safe Event Sink]
  Gateway --> Sync[WebSocket Document Sync]
  Gateway --> Privacy[Privacy / DLP Preprocessor]
  Privacy --> Provider{Bangla Provider}
  Provider --> Python[Python FastAPI Bangla Engine]
  Provider --> Fallback[Conservative Bangla Local Fallback]
  Python --> Pipeline[Normalizer + Sentence Splitter + Tokenizer + Rule + Spell + Grammar + Tone + Rewrite]
  Pipeline --> Canonical[Canonical CheckResponse]
  Fallback --> Canonical
```

## Check request flow

```mermaid
sequenceDiagram
  participant Client
  participant Gateway
  participant Privacy
  participant Python as Python Bangla API
  participant Fallback as Local Bangla Fallback
  participant Events
  Client->>Gateway: POST /api/check {text, language: bn, revision}
  Gateway->>Gateway: validate size/language and assign requestId
  Gateway->>Privacy: redact/log policy hook
  Gateway->>Python: POST /analyze
  alt Python available
    Python-->>Gateway: legacy AnalyzeResponse
    Gateway->>Gateway: adapt to canonical suggestions + UTF-16 spans
  else Python unavailable and fallback enabled
    Gateway->>Fallback: run conservative Bangla rules
    Fallback-->>Gateway: canonical CheckResponse + warning
  end
  Gateway->>Events: suggestion_generated without raw text
  Gateway-->>Client: CheckResponse
```

## Bangla NLP pipeline

```mermaid
flowchart LR
  Text[Bangla text] --> NFC[NFC normalization]
  NFC --> Split[Bangla sentence splitter]
  Split --> Tokens[Tokenizer / grapheme span mapper]
  Tokens --> Rules[Rule engine]
  Tokens --> Spell[Spell engine]
  Tokens --> Grammar[Grammar checks]
  Tokens --> Tone[Tone engine]
  Tokens --> Rewrite[Rewrite engine]
  Rules --> Rank[Rank + dedupe]
  Spell --> Rank
  Grammar --> Rank
  Tone --> Rank
  Rewrite --> Rank
  Rank --> Suggestions[Normalized Suggestion Response]
```

## WebSocket document sync flow

```mermaid
sequenceDiagram
  participant ClientA
  participant WS as /ws/docs/:documentId
  participant Store as InMemory DocumentStore
  ClientA->>WS: client_hello
  WS-->>ClientA: server_hello {document, revision}
  ClientA->>WS: edit {baseRevision, text/op}
  WS->>Store: applyDelta
  alt revision matches
    Store-->>WS: document revision+1
    WS-->>ClientA: ack + latest document
  else mismatch
    Store-->>WS: authoritative document
    WS-->>ClientA: resync_required
  end
```

The MVP sync protocol is intentionally not OT/CRDT; it is a server-authoritative revision skeleton that can evolve into full collaborative editing.

## Future hybrid on-device/cloud architecture

```mermaid
flowchart TD
  Client[Client] --> LocalPolicy{Can local model handle privately?}
  LocalPolicy -- yes --> OnDevice[On-device Bangla provider]
  LocalPolicy -- no / low confidence --> Gateway[API Gateway]
  Gateway --> Policy[Enterprise/privacy policy]
  Policy --> Cloud[Cloud Bangla orchestrator]
  Cloud --> Python[Python rule/spell/grammar]
  Cloud --> ML[Future ML/LLM adapter]
  OnDevice --> Merge[Merge + rank]
  Python --> Merge
  ML --> Merge
  Merge --> UI[Suggestion UI]
  UI --> Events[Consent-aware feedback]
```

## Decisions

- Python Bangla engine remains the source of linguistic truth.
- TypeScript API is the common gateway and provider orchestrator.
- Frontends should call `/api/check` and receive canonical `CheckResponse`.
- Suggestion IDs and suppression keys are stable hashes, never request IDs.
- Python code point offsets are converted to browser UTF-16 offsets; grapheme snapping avoids splitting Bangla clusters.
- The Next MVP uses a textarea and side-panel cards instead of mutating `contentEditable` HTML every render.
- Events are privacy-safe and do not store raw full user text.
- Postgres and Redis are prepared for durable production mode; local dev can use memory mode.
