# Rukh AI Fly and Writing Assistant frontend — 6 November 2026

## Product boundaries

- **AI Coworker** remains the default conversation-first application.
- **Fly** is a separate coding workspace exposed at /fly and in primary navigation.
- **Web Editor** remains the approved visual website canvas at /editor; its website-building purpose and existing implementation are preserved.
- **Writing Assistant** is the existing multilingual writing application exposed directly at /writing. The existing spelling, grammar, punctuation, clarity, rewriting and Deep AI Review implementation is reused.

## Figma source

The approved Figma file is eIeIHgClMJia6kRi484Xsl, with desktop Coworker node 3:181 and mobile Coworker node 4:1703. The Figma connector returned its Starter-plan rate limit during this continuation. Implementation therefore follows the committed exports in docs/frontend/design-reference/design.json and design-tokens.json, together with the approved Coworker/Web Editor shell already merged in PR #636.

The committed export contains Coworker and Web Editor frames, but no dedicated Fly or separate Writing Assistant frame. Fly is a new workspace extension using the exported palette, typography, spacing, border and responsive shell tokens. No new Figma frame is claimed.

## Fly capabilities implemented

- Multi-file local source drafts (up to 12 files, 512 KB per file), scoped by account and browser tab.
- Text-source import and download for common programming languages and formats.
- Line-numbered editor with lightweight syntax highlighting, language selection, file create/remove, and keyboard shortcuts.
- Verified private source snapshots in Rukh Files. The current upload API accepts document formats ending in .txt, so snapshots are stored as filename.ext.txt; Fly retains the original extension in the editor and downloads.
- Optional linking of saved source snapshots to an existing Coworker project.
- Actual isolated Python 3.11 execution through the existing code_task sandbox API, only when its server capability reports enabled.
- Python output/history, cancellation and the existing short-lived isolated sandbox artifact preview.
- HTML preview in a sandboxed iframe with scripts, network access and form submission disabled.
- Coworker Agent code-review handoff with the verified source version attached. The prompt requests static analysis and a proposed unified diff; it does not claim to modify local source.

## Explicit backend limitations

This is not yet full Codex/Claude Code parity. The current backend exposes only the isolated Python 3.11 sandbox for code execution. It does not expose a persistent repository checkout, arbitrary shell, Git clone/commit/push, remote file writes, package installation or Node/Java/Rust/other language runtimes. Those controls are intentionally not simulated or enabled.

Local drafts remain in the current browser tab until saved to Rukh Files. Saving creates a new text snapshot and does not overwrite the original file. Agent review is a Coworker task, not a remote repository edit.

## Verification status

The source branch includes route, navigation, workspace-directory and Fly SSR regression tests. Exact-head CI and browser checks must be read before claiming they pass. This document does not claim deployment, live authentication, runtime availability, staging qualification or production activation.
