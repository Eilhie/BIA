# Mimir Memory — Convention

This folder is Mimir's own memory store: knowledge that doesn't live in code
docstrings or the README, captured explicitly (never auto-detected, never
guessed) by one of two recorders:

- **Claude Code**, during a development session — writes files here directly,
  following the exact format below, then rebuilds Mimir's index.
- **Mimir itself**, during everyday use — a message starting with `catat:` in
  the chat drafts a memory (decision/correction/process) via the local LLM,
  shown for confirmation before saving. The sidebar's "Tambah Artifact Excel"
  uploader captures Excel file structure the same way.

Every memory here gets embedded into Mimir's index alongside README.md and
`heimdall/` docstrings — see `indexer.py`'s `collect_memories()`.

## File format

One memory per file, in the matching subfolder:

```
decisions/<slug>.md
corrections/<slug>.md
processes/<slug>.md
artifacts/<slug>-structure.md
artifacts/<slug>-purpose.md
```

```markdown
---
name: <slug>
type: decision | correction | process | artifact-structure | artifact-purpose
tags: [tag1, tag2]
date: YYYY-MM-DD
source_file: <optional -- original path, for artifact-* types>
---

<content -- for decision/correction: what + why, following the same
shape as Claude's own memory files (rule, then **Why:** and **How to
apply:**). For process: the actual end-to-end sequence, not a restatement
of a docstring. For artifact-structure: sheet names, columns, notable
formulas. For artifact-purpose: what the file is for, in the user's own
words -- never auto-generated.>
```

## Types, in one line each

| Type | Captures |
|---|---|
| `decision` | Why something was built/changed a certain way |
| `correction` | A mistake made once, so it isn't repeated |
| `process` | How something works end-to-end |
| `artifact-structure` | Sheet names/columns/formulas of a real Excel file — auto-extracted via `openpyxl`, safe since it's shape, not real figures |
| `artifact-purpose` | What that file is *for* — always human-written, never inferred from structure (guessing "why" is exactly the kind of unverified claim Mimir avoids everywhere else) |

## What NOT to put here

- Real data/figures from Excel files (sales numbers, claims, etc.) — only
  structure (`artifact-structure`) and human-stated purpose
  (`artifact-purpose`) belong here, never the data itself.
- Anything already accurate in a docstring or README — this is for
  knowledge that has no other home.

`MEMORY.md` in this folder is a human-readable index (for browsing and
avoiding duplicate memories) — it is not read by the retrieval system
itself, unlike the individual memory files.
