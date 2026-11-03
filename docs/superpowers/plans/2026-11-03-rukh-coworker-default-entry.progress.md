# SDD ledger — plan: docs/superpowers/plans/2026-11-03-rukh-coworker-default-entry.md

## Setup
- Repository: rumman52/Shuddho
- Base: main at 70349358c1300414221bb811abc3367da9acd60e
- Isolated branch: feat/rukh-coworker-default-entry-20261103
- Existing ProductOS active project is an unrelated Dust2Glow demo; it will not be used.
- Baseline evidence: previous Coworker CI run reported 1,731 passed, 72 skipped, 2 failures; Coworker integration job also failed. Treat these as pre-existing until a fresh final-head run distinguishes them.

## Pre-flight
- Task 1 produces route mapping consumed by WorkspaceShell; Task 2 only changes header destinations and therefore consumes the same route contract without changing it.
- Task 2's navigation test imports the existing Coworker standalone App; it must remain server-renderable with Coworker disabled.

## Task progress
- Task 1: pending
- Task 2: pending
- Task 3: pending
