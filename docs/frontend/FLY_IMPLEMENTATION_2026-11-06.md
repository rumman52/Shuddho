# Rukh AI Fly coding workspace — 6 November 2026

## Product boundaries

- **AI Coworker** remains the default conversation-first workspace.
- **Fly** is the dedicated coding workspace at /fly.
- **Writing Assistant** remains a separate multilingual writing workspace at /writing, reusing the existing spelling, grammar, punctuation, clarity, rewriting and Deep AI Review engine.
- **Web Editor has been removed** from user-facing navigation, workspace directory, artifact links and application routing. The old /editor path falls back to the workspace directory.

## Figma source

The approved Figma file is eIeIHgClMJia6kRi484Xsl, with desktop Coworker node 3:181 and mobile Coworker node 4:1703. The Figma connector reached its Starter-plan request limit during this implementation. The workbench therefore uses the committed exports in docs/frontend/design-reference/design.json and design-tokens.json, including the approved Rukh green (#245A43), neutral palette, Inter typography, borders, spacing and responsive breakpoints.

The exported Figma file contains Coworker and the former Web Editor screens, but no dedicated Fly screen. Fly's IDE arrangement is a new product implementation using the approved Rukh design tokens and a Codex-inspired coding-workbench layout; it is not represented as an existing Figma frame.

## Fly interface

- Three-pane coding workbench: project/file explorer, source editor and Rukh Agent panel.
- Multi-file local source drafts (up to 12 files, 512 KB per file), scoped by account and browser tab.
- Text-source import and download for common programming languages and formats.
- Line-numbered source editor with lightweight syntax highlighting, language selection, file create/remove and keyboard shortcuts.
- Responsive desktop, tablet and mobile layout; mobile file tabs scroll horizontally and the editor, terminal and Rukh Agent remain available.
- Project selection and optional linking of saved source snapshots to an existing Coworker project.
- Prompt-based Rukh Agent handoff that saves and attaches the active source file, dispatches the user's request to a real Coworker conversation, then opens that conversation for the response.
- Verified private source snapshots in Rukh Files. The current upload API accepts document formats ending in .txt, so snapshots are stored as filename.ext.txt; Fly retains the original extension in the editor and downloads.
- Actual isolated Python 3.11 execution through the existing code_task sandbox API, only when the server capability reports enabled.
- Python execution output/history, cancellation and isolated sandbox artifact preview.
- HTML preview in a sandboxed iframe with scripts, network access and form submission disabled.

## Explicit backend limitations

This is not full Codex/Claude Code execution parity. The current backend exposes only isolated Python 3.11 execution. It does not expose a persistent repository checkout, arbitrary shell, Git clone/commit/push, remote file writes, package installation or Node/Java/Rust/other language runtimes. The UI states these limits rather than simulating a terminal or pretending repository changes were made.

The Rukh Agent panel currently hands the active file and the user's prompt to Coworker; it does not stream an in-panel response or directly modify local source files. Proposed changes must be reviewed and applied by the user. Local drafts remain in the current browser tab until saved to Rukh Files. Saving creates a new text snapshot and does not overwrite the original file.

## Verification status

The branch includes updated route, workspace-directory, Fly SSR and browser workflow assertions. Exact-head CI, browser screenshots, authentication, runtime availability and deployment preview must be checked before claiming production qualification.
