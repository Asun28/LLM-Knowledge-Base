# Cycle 13 — Step 3 Brainstorming

**Date:** 2026-04-19
**Scope ref:** `docs/superpowers/decisions/2026-04-19-cycle13-requirements.md`
**Threat ref:** `docs/superpowers/decisions/2026-04-19-cycle13-threat-model.md`

## Approach A — Read-only-only migration + CLI sweep + raw_dir derivation (RECOMMENDED)

Migrate **only** the 5 read-only `frontmatter.load(str(...))` sites identified in the BACKLOG. Pin the 3 write-back sites (augment.py:914/1026/1053) with a negative test (AC13) so future "fix everything" sweeps don't silently break YAML key ordering. Wire `sweep_orphan_tmp` into the `cli` group entry callback, sweeping both `PROJECT_ROOT/.data` and `WIKI_DIR`. Add the `wiki_dir != WIKI_DIR ⇒ raw_dir = wiki_dir.parent / "raw"` branch in `run_augment` mirroring the existing `effective_data_dir` derivation.

**Pros:** Smallest blast radius. Each change has a clean test boundary. No interactions with the YAML-key-ordering footgun (cycle 7 R1 Codex M3). All three BACKLOG cycle-13 targets close in one cycle. CLI-boot sweep means the `sweep_orphan_tmp` helper actually runs in shipped code.

**Cons:** Three augment.py write-back sites stay on the un-cached `frontmatter.load` path; they re-parse YAML on every call. Acceptable because they're exactly 3 sites called at most once per augment run (not in a per-page hot loop).

**Trade-off:** Defers full migration but explicitly documents it. Lesson L3 from cycle 12 (PARTIAL handling) means out-of-scope concerns get a follow-up entry; here, write-back migration is captured as cycle-13 BACKLOG addition (item AC17) tied to the YAML-ordering fix needed for safe `Post(content, **metadata)` reconstruction.

## Approach B — Full 8-site migration via `Post`-reconstruction wrapper

Add a `_save_page_frontmatter(page_path, metadata, body)` write-back wrapper alongside `load_page_frontmatter`; reconstruct `frontmatter.Post(body, **metadata)` and `dumps(post, sort_keys=False)` to preserve key order. Migrate all 8 sites (5 read-only + 3 write-back).

**Pros:** Single coherent migration. Cache helper covers the entire frontmatter surface. Resolves the YAML-key-ordering footgun centrally.

**Cons:** New write-back wrapper has its own fan-out testing burden. Risk of cycle-7 R1 Codex M3 alphabetisation regression if I miss `sort_keys=False`. Cache invalidation after write needs explicit thought (single-key clear vs. full cache_clear). Three augment.py write-back sites have subtle differences (record_attempt flushes a single timestamp; mark_page_augmented mutates content + metadata). Larger diff = harder review.

**Trade-off:** Doubles cycle 13 scope without a critical-path benefit. Same-class-completeness arguments from cycle 12 self-review weigh in favour, but the YAML-ordering risk dominates.

## Approach C — Defer all three cycle-13 BACKLOG items to a Phase-5-augment refactor cycle

Pass on cycle 13 entirely; bundle these three into a Phase-5 `lint/augment.py` cleanup that also handles `run_augment(resume=...)` re-wiring (Phase 5 pre-merge MEDIUM) and the YAML-ordering write-back wrapper.

**Pros:** Single coherent augment refactor with one design pass.

**Cons:** Loses three months of compound benefit from the cached helper. Leaves `sweep_orphan_tmp` un-wired (the helper shipped in cycle 12 but is dead code without a caller). Mixes mechanical migrations with feature work (resume wiring) — exactly the anti-pattern feature-dev's group-fix-by-file batching opposes.

## Decision

**Approach A.** Smallest blast radius, three explicit BACKLOG closes, no YAML-ordering risk, predictable test footprint. Approach B's same-class argument is weakened by the write-back footgun; approach C trades immediate value for a hypothetical bigger refactor that may never happen.

## Open questions for Step 5 decision gate

- **Q1.** CLI sweep target list — `.data` only, or `.data + WIKI_DIR`? Conservative-low-cost says BOTH (helper is no-op on missing dirs); minimal-blast-radius says `.data` only (where atomic-writes happen most often).
- **Q2.** CLI sweep ERROR handling — wrap entire boot sweep in `try/except` swallow, or trust the helper's own swallowing? Helper already returns 0 on every error class except programming bugs; trust it.
- **Q3.** AC13 negative-pin test mechanism — assert via `inspect.getsource` substring (BANNED per cycle-11 L1 / Red Flag #21), or `Path.read_text` + `splitlines` (also BANNED per cycle-11 L1), or via a `monkeypatch`-based call-site spy that confirms the function still calls `frontmatter.load` (the LIVE path)? Cycle-11 lesson says the spy is the only behavioural option — the negative-pin must EXERCISE the production code path, not just grep its source.
- **Q4.** `run_augment` raw_dir derivation default — should it ALSO honour `KB_RAW_ROOT` env var (mirroring cycle-12 `KB_PROJECT_ROOT`)? Cycle-12 design rejected env-var fanout for niche overrides; do not introduce here.
- **Q5.** Migration of `graph/export.py:132` — wrap as `Path(path)` or change `build_graph` to store `Path` objects directly? Latter has wider blast radius (every consumer of the `path` attribute would change); former is one-line. Pick wrapper.
- **Q6.** Write-back negative-pin scope — pin all 3 (augment.py:914 + 1026 + 1053) or just one canonical site? Pin all 3 because each has different mutation semantics and a refactor could change them at different times.
- **Q7.** Test isolation for the CLI-boot sweep — the AC14 test invokes `runner.invoke(cli, ["--version"])`; how do we prove `sweep_orphan_tmp` was called WITHOUT depending on real `.data` directory state? Use `monkeypatch.setattr(kb.cli, "sweep_orphan_tmp", spy)` and assert `spy.call_args_list` contains both expected paths.
