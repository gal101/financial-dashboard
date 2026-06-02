# Project Documentation Map (Quick Reference for Next Agent)

This document serves as a map to the repository's documentation ecosystem. Before starting any work or modifications, refer to this guide to find the source of truth for requirements, code implementation steps, API structures, or domain formulas.

---

## Documentation Ecosystem at a Glance

| File | Purpose | When to Consult | Stiff / Current State |
| :--- | :--- | :--- | :--- |
| **`NEW-PRD.md`** | Core product specification for the Tradeville API migration. | To understand **what** features need to be built, user stories, and high-level architectural decisions. | **Current & Active.** Contains the final approved design. |
| **`HANDOFF.md`** | Step-by-step developer implementation recipe. | To know **how** to write the code. Contains structural steps (Steps 1–8), error-handling logic, and Chart.js code structures. | **Current & Active.** Follow this to execute the migration. |
| **`TRADEVILLE-API-DOCS.md`** | Technical reference for the Tradeville API. | To view exact **JSON payloads** (requests/responses), connection endpoints, and response schemas for BVB queries. | **Current & Active.** Reference cheat sheet. |
| **`CONTEXT.md`** | Project glossary and financial calculations source of truth. | To understand BVB-specific calculations (e.g. TTM P/E using quarterly derived figures, EPS, profit margins). | **Stable.** Read to keep domain logic aligned. |
| **`FEATURES.md`** | Project backlog and roadmap. | To review completed features (`✅`) vs. future unimplemented features (`❌`). | **Stable.** Refer to for project context and future goals. |
| **`README.md`** | Repository setup guide and overview. | To understand how to run the project locally. | **Lagging Behind.** Currently describes the old Yahoo Finance setup. *Needs update at the start of implementation.* |
| **`OLD-PRD.md`** | MVP specification (Yahoo Finance). | Retained strictly as historical reference. | **Archived.** |
| **`references/bvb-scraping-recipe.md`** | Scraping methodology guide for BVB.ro. | Refer to when developing future web scraping tasks. | **Archived.** |

---

## Recommended Handoff Read Order for Next Session

To ramp up on the Tradeville migration task efficiently, read the files in the following order:

1. **`DOCS-MAP.md`** (This file) — To understand the documentation layout.
2. **`NEW-PRD.md`** — To understand the migration goals, the hybrid streaming/on-demand design, and user expectations.
3. **`TRADEVILLE-API-DOCS.md`** — To familiarize yourself with the Tradeville WebSocket commands, payloads, and columnar responses.
4. **`HANDOFF.md`** — To get the step-by-step implementation cookbook (including the single-gateway proxy design, thread-safe queues, and parallel push workers).
