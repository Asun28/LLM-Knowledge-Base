"""Cycle 97 — bounded wiki-page BODY read in the paired-context path.

Closes the cycle-96 R1 F1 residual (Phase 4.5 MEDIUM). Cycle 96 bounded the
SOURCE reads behind ``kb_review_page`` / ``kb_lint_deep``; the page body itself
was still pulled in whole through ``load_page_frontmatter`` before
``_cap_page_content`` trimmed it for assembly. This suite pins the other half.

Divergence discipline (cycle-11 L2 / cycle-16 L2 / cycle-24 L4): every test here
must FAIL against the pre-cycle-97 implementation. The two probes that carry
that weight are
``TestBoundedPageRead::test_read_call_is_bounded_by_the_budget`` (records the
argument passed to ``read``) and
``TestSharedHotPathUntouched::test_paired_path_does_not_use_the_cached_full_read``
(the unbounded cached reader is made explosive).
"""

import re
from pathlib import Path

import pytest

from kb.errors import PageReadBudgetError, ValidationError
from kb.review import context

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _write_page(wiki: Path, page_id: str, *, title: str = "T", body: str = "b", source=None):
    """Write a wiki page with a well-formed frontmatter block."""
    path = wiki / f"{page_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    src_block = ""
    if source:
        src_block = "source:\n" + "".join(f'  - "{s}"\n' for s in source)
    path.write_text(f'---\ntitle: "{title}"\n{src_block}---\n\n{body}\n', encoding="utf-8")
    return path


def _write_raw(root: Path, rel: str, text: str) -> str:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return rel


def _pair(tmp_kb_env, page_id, **kwargs):
    return context.pair_page_with_sources(
        page_id,
        wiki_dir=tmp_kb_env / "wiki",
        raw_dir=tmp_kb_env / "raw",
        project_root=tmp_kb_env,
        **kwargs,
    )


class _RecordingHandle:
    """Wraps a binary file handle and records every ``read`` size requested."""

    def __init__(self, fh, sizes):
        self._fh = fh
        self._sizes = sizes

    def read(self, n=-1):
        self._sizes.append(n)
        return self._fh.read(n)

    def fileno(self):
        return self._fh.fileno()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return self._fh.__exit__(*exc)


# --------------------------------------------------------------------------
# AC01 — the constant
# --------------------------------------------------------------------------


class TestPageReadBudgetConstant:
    def test_constant_exists_and_sits_above_the_assembly_cap(self):
        """A read cap below the downstream assembly cap would make the READ the
        binding constraint on ordinary pages — the budget is a pathology bound,
        not a content policy.

        The factor of 4 is the worst-case UTF-8 bytes per character: 80,000
        chars of assembly budget can cost 320,000 bytes to read. Pinning the
        RELATION rather than the value is the point — raising
        ``QUERY_CONTEXT_MAX_CHARS`` to 300,000 without raising this constant
        would silently make the read binding, and this test is the tripwire.
        """
        import kb.config as config

        assert isinstance(config.PAIRED_PAGE_READ_MAX_BYTES, int)
        assert config.PAIRED_PAGE_READ_MAX_BYTES >= 4 * config.QUERY_CONTEXT_MAX_CHARS

    def test_page_budget_is_not_drawn_from_the_source_pool(self, tmp_kb_env):
        """Shrinking the SOURCE budget to nothing must not truncate the PAGE.

        The two budgets are deliberately separate pools: an even split would let
        one huge source starve the page body, and vice versa.
        """
        wiki = tmp_kb_env / "wiki"
        ref = _write_raw(tmp_kb_env, "raw/articles/a.md", "S" * 5_000)
        _write_page(wiki, "concepts/p", body="P" * 5_000, source=[ref])

        result = _pair(tmp_kb_env, "concepts/p", read_budget=10)

        first = result["source_contents"][0]
        assert first.get("truncated") or first.get("skipped"), "source budget should have bitten"
        assert "page_truncated" not in result
        assert "P" * 5_000 in result["page_content"]


# --------------------------------------------------------------------------
# AC02 / AC03 — the bounded reader
# --------------------------------------------------------------------------


class TestBoundedPageRead:
    def test_read_call_is_bounded_by_the_budget(self, tmp_kb_env, monkeypatch):
        """The cap applies to the READ, not the result (cycle-96 FW-1).

        Records the argument handed to ``read``. A ``read_text()[:n]`` or a bare
        ``read()`` implementation records ``-1`` / no bounded call and fails.
        """
        wiki = tmp_kb_env / "wiki"
        page_path = _write_page(wiki, "concepts/big", body="x" * 40_000)
        sizes: list[int] = []
        real_open = Path.open

        def _spy_open(self, *args, **kwargs):
            fh = real_open(self, *args, **kwargs)
            if Path(self) == page_path:
                return _RecordingHandle(fh, sizes)
            return fh

        monkeypatch.setattr(Path, "open", _spy_open)
        result = _pair(tmp_kb_env, "concepts/big", page_read_budget=1_000)

        assert sizes, "the page file was never opened through Path.open"
        assert all(n == 1_000 for n in sizes), f"unbounded read call recorded: {sizes}"
        # An implementation that opens once to scan for the closing fence and
        # again to parse spends the budget twice and passes the check above.
        assert len(sizes) == 1, f"page body read {len(sizes)} times, expected 1"
        assert result["page_truncated"] is True

    def test_truncation_reports_bytes_read_and_total(self, tmp_kb_env):
        wiki = tmp_kb_env / "wiki"
        page_path = _write_page(wiki, "concepts/big", body="x" * 40_000)
        total = page_path.stat().st_size

        result = _pair(tmp_kb_env, "concepts/big", page_read_budget=1_000)

        assert result["page_truncated"] is True
        assert result["page_bytes_read"] == 1_000
        assert result["page_bytes_total"] == total
        assert len(result["page_content"]) < 40_000
        assert result["page_metadata"]["title"] == "T", "frontmatter must survive truncation"

    def test_absence_of_caveat_keys_means_no_caveat(self, tmp_kb_env):
        """cycle-73 ``get_prompt_version`` / cycle-88 ``durable`` convention."""
        _write_page(tmp_kb_env / "wiki", "concepts/small", body="tiny")

        result = _pair(tmp_kb_env, "concepts/small")

        assert "page_truncated" not in result
        assert "page_bytes_read" not in result
        assert "page_bytes_total" not in result
        assert result["page_content"].strip() == "tiny"

    def test_budget_resolves_at_call_time(self, tmp_kb_env, monkeypatch):
        """cycle-18 L1 / cycle-19 L2 — a def-time default defeats monkeypatching."""
        _write_page(tmp_kb_env / "wiki", "concepts/p", body="y" * 20_000)

        monkeypatch.setattr(context, "PAIRED_PAGE_READ_MAX_BYTES", 900)
        result = _pair(tmp_kb_env, "concepts/p")

        assert result["page_truncated"] is True
        assert result["page_bytes_read"] == 900

    def test_multibyte_cut_is_boundary_safe(self, tmp_kb_env):
        """A budget landing mid-sequence must not raise and must not emit U+FFFD."""
        wiki = tmp_kb_env / "wiki"
        _write_page(wiki, "concepts/cjk", body="漢" * 2_000)
        page_path = wiki / "concepts/cjk.md"
        head = len(page_path.read_bytes()) - 3_000

        for offset in range(3):
            result = _pair(tmp_kb_env, "concepts/cjk", page_read_budget=head + offset)
            assert "error" not in result, result.get("error")
            assert "�" not in result["page_content"]
            assert result["page_truncated"] is True

    def test_invalid_utf8_inside_the_window_still_errors(self, tmp_kb_env):
        """Not ``errors='ignore'`` — corrupt bytes stay loud (cycle-96 FW-2)."""
        wiki = tmp_kb_env / "wiki"
        page_path = wiki / "concepts" / "corrupt.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_bytes(b'---\ntitle: "T"\n---\n\ngood \xff\xfe bad\n' + b"z" * 5_000)

        result = _pair(tmp_kb_env, "concepts/corrupt", page_read_budget=1_000)

        assert "error" in result
        assert result["page_id"] == "concepts/corrupt"

    def test_incomplete_trailing_sequence_at_eof_is_not_silently_clean(self, tmp_kb_env):
        """cycle-96 R1 F5, page half: ``final`` is conditional, not constant.

        The SAME trailing bytes must read clean when the BUDGET cut them off and
        error when the FILE ends that way — a ``final=False``-always or
        ``final=True``-always implementation fails one half of this test.
        """
        wiki = tmp_kb_env / "wiki"
        prefix = b'---\ntitle: "T"\n---\n\nhello\xe2'

        at_eof = wiki / "concepts" / "tail_eof.md"
        at_eof.parent.mkdir(parents=True, exist_ok=True)
        at_eof.write_bytes(prefix)
        whole = _pair(tmp_kb_env, "concepts/tail_eof", page_read_budget=len(prefix))
        assert "error" in whole, "an incomplete sequence at EOF is a corrupt file"

        # Same bytes at the same offset — but here the BUDGET made the cut, so
        # the partial sequence is a boundary artefact and must be dropped.
        by_budget = wiki / "concepts" / "tail_cut.md"
        by_budget.write_bytes(prefix + "漢字tail".encode() * 50)
        cut = _pair(tmp_kb_env, "concepts/tail_cut", page_read_budget=len(prefix))
        assert "error" not in cut, cut.get("error")
        assert cut["page_truncated"] is True
        assert cut["page_content"].rstrip().endswith("hello")

    def test_bytes_total_comes_from_the_open_descriptor(self, tmp_kb_env, monkeypatch):
        """cycle-96 FW-3 — size and bytes come from one file description, so a
        separate ``path.stat()`` cannot disagree with what was read.

        Calls the reader directly: ``Path.exists`` goes through ``Path.stat``
        too, so patching it around the whole pairing call would only prove the
        existence check runs first.
        """
        page_path = _write_page(tmp_kb_env / "wiki", "concepts/p", body="q" * 9_000)
        real_size = page_path.stat().st_size

        def _lying_stat(self, *a, **kw):
            raise AssertionError("size must come from os.fstat on the open handle")

        monkeypatch.setattr(Path, "stat", _lying_stat)
        _meta, _body, bytes_read, bytes_total = context._read_page_within_budget(page_path, 500)

        assert bytes_total == real_size
        assert bytes_read == 500

    def test_budget_exactly_at_eof_is_not_a_truncation(self, tmp_kb_env):
        """An off-by-one here flips a whole legal page into a truncated one."""
        page_path = _write_page(tmp_kb_env / "wiki", "concepts/p", body="exact")
        total = page_path.stat().st_size

        result = _pair(tmp_kb_env, "concepts/p", page_read_budget=total)

        assert "page_truncated" not in result
        assert "exact" in result["page_content"]

    def test_truncated_body_still_pairs_every_source(self, tmp_kb_env):
        """The harm of a botched page read is not a short body — it is an empty
        ``source_contents``. A fidelity review then scores every claim as
        unsourced against material that was there all along."""
        one = _write_raw(tmp_kb_env, "raw/articles/one.md", "first source body")
        two = _write_raw(tmp_kb_env, "raw/articles/two.md", "second source body")
        _write_page(tmp_kb_env / "wiki", "concepts/p", body="B" * 30_000, source=[one, two])

        result = _pair(tmp_kb_env, "concepts/p", page_read_budget=1_500)

        assert result["page_truncated"] is True
        assert len(result["source_contents"]) == 2
        assert all(s.get("content") for s in result["source_contents"])


# --------------------------------------------------------------------------
# AC04 — fail-closed when the budget cuts the frontmatter block itself
# --------------------------------------------------------------------------


class TestFrontmatterCutByBudget:
    def test_unclosed_frontmatter_is_a_distinct_error(self, tmp_kb_env):
        """Silently yielding empty metadata + a garbage body is the failure this
        rejects: the caller cannot tell it from a page that genuinely has no
        frontmatter, and the review context would then score a page whose type,
        confidence and sources all read as 'unknown'."""
        wiki = tmp_kb_env / "wiki"
        page_path = wiki / "concepts" / "fat.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(
            '---\ntitle: "T"\nnotes: "' + "n" * 8_000 + '"\n---\n\nbody\n', encoding="utf-8"
        )

        result = _pair(tmp_kb_env, "concepts/fat", page_read_budget=1_000)

        assert "error" in result
        assert "Malformed YAML" not in result["error"], "must not conflate with the parse error"
        assert "budget" in result["error"].lower()
        assert result["page_id"] == "concepts/fat"
        assert "page_content" not in result, "fail closed — no partial page is handed on"

    def test_error_type_is_not_a_valueerror_subclass(self):
        """The broad ``except (OSError, ValueError, ...)`` in the pairing helper
        would otherwise swallow it and re-label it as malformed YAML."""
        assert issubclass(PageReadBudgetError, ValidationError)
        assert not issubclass(PageReadBudgetError, ValueError)

    def test_page_with_no_frontmatter_at_all_is_not_flagged(self, tmp_kb_env):
        """A body-only page is legal — flagging it would be a false positive."""
        wiki = tmp_kb_env / "wiki"
        page_path = wiki / "concepts" / "bare.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text("no frontmatter here\n" + "w" * 9_000, encoding="utf-8")

        result = _pair(tmp_kb_env, "concepts/bare", page_read_budget=1_000)

        assert "error" not in result, result.get("error")
        assert result["page_metadata"] == {}
        assert result["page_truncated"] is True

    def test_closed_empty_frontmatter_block_is_not_flagged(self, tmp_kb_env):
        """``---\\n---\\n`` parses to empty metadata but IS closed — an
        empty-metadata heuristic would misreport it."""
        wiki = tmp_kb_env / "wiki"
        page_path = wiki / "concepts" / "empty.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text("---\n---\n\n" + "e" * 9_000, encoding="utf-8")

        result = _pair(tmp_kb_env, "concepts/empty", page_read_budget=1_000)

        assert "error" not in result, result.get("error")
        assert result["page_truncated"] is True

    def test_unclosed_frontmatter_on_a_COMPLETE_read_keeps_legacy_behaviour(self, tmp_kb_env):
        """When the budget did NOT bite, an unclosed block is a genuinely
        malformed page and must behave exactly as it did pre-cycle-97."""
        wiki = tmp_kb_env / "wiki"
        page_path = wiki / "concepts" / "broken.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text('---\ntitle: "T"\nno closing delimiter\n', encoding="utf-8")

        result = _pair(tmp_kb_env, "concepts/broken", page_read_budget=1_000_000)

        assert "error" not in result, result.get("error")
        assert result["page_metadata"] == {}

    def test_legal_frontmatter_larger_than_10kb_is_not_flagged(self):
        """``kb.utils.markdown.FRONTMATTER_RE`` is the obvious helper to reach
        for and is wrong for this job: it is bounded at ``.{0,10000}?``, so a
        legal 12 KB block reads as unclosed and a fine page is refused."""
        block = '---\ntitle: "T"\nnotes: "' + "n" * 12_000 + '"\n---\n'
        assert context._frontmatter_resolved(block + "body")

    @pytest.mark.parametrize("budget", [1, 2, 3])
    def test_prefix_too_short_to_classify_fails_closed(self, tmp_kb_env, budget):
        """A 2-byte prefix of ``--`` does not match the opener, and concluding
        'body-only page' from it returns an empty body with ZERO sources —
        exactly the failure AC04 exists to stop, through the side door."""
        ref = _write_raw(tmp_kb_env, "raw/articles/a.md", "source body")
        _write_page(tmp_kb_env / "wiki", "concepts/p", body="B" * 2_000, source=[ref])

        result = _pair(tmp_kb_env, "concepts/p", page_read_budget=budget)

        assert "error" in result
        assert "budget" in result["error"].lower()

    def test_boundary_regex_matches_the_parser(self):
        """The detection must agree with python-frontmatter's own split, or the
        two disagree about what 'closed' means. Pinned so a library change is a
        loud CI failure rather than a silent divergence."""
        from frontmatter.default_handlers import YAMLHandler

        assert context._FM_BOUNDARY.pattern == YAMLHandler.FM_BOUNDARY.pattern
        assert context._FM_BOUNDARY.flags & re.MULTILINE


# --------------------------------------------------------------------------
# AC05 — the truncation is announced
# --------------------------------------------------------------------------


class TestTruncationIsAnnounced:
    def _big_page(self, tmp_kb_env):
        ref = _write_raw(tmp_kb_env, "raw/articles/a.md", "source text")
        _write_page(tmp_kb_env / "wiki", "concepts/p", body="z" * 40_000, source=[ref])

    def test_review_context_announces_page_truncation(self, tmp_kb_env, monkeypatch):
        self._big_page(tmp_kb_env)
        monkeypatch.setattr(context, "PAIRED_PAGE_READ_MAX_BYTES", 800)

        out = context.build_review_context("concepts/p", tmp_kb_env / "wiki", tmp_kb_env / "raw")

        assert context._PAGE_TRUNCATION_MARKER in out

    def test_fidelity_context_announces_page_truncation(self, tmp_kb_env, monkeypatch):
        from kb.lint import semantic

        self._big_page(tmp_kb_env)
        monkeypatch.setattr(context, "PAIRED_PAGE_READ_MAX_BYTES", 800)

        out = semantic.build_fidelity_context("concepts/p", tmp_kb_env / "wiki", tmp_kb_env / "raw")

        assert context._PAGE_TRUNCATION_MARKER in out

    def test_completeness_context_announces_page_truncation(self, tmp_kb_env, monkeypatch):
        from kb.lint import semantic

        self._big_page(tmp_kb_env)
        monkeypatch.setattr(context, "PAIRED_PAGE_READ_MAX_BYTES", 800)

        out = semantic.build_completeness_context(
            "concepts/p", tmp_kb_env / "wiki", tmp_kb_env / "raw"
        )

        assert context._PAGE_TRUNCATION_MARKER in out

    def test_no_notice_when_the_budget_did_not_bite(self, tmp_kb_env):
        _write_page(tmp_kb_env / "wiki", "concepts/p", body="small body")

        out = context.build_review_context("concepts/p", tmp_kb_env / "wiki", tmp_kb_env / "raw")

        assert context._PAGE_TRUNCATION_MARKER not in out

    @pytest.mark.parametrize("builder", ["review", "fidelity", "completeness"])
    def test_notice_sits_outside_the_wiki_context_fence(self, tmp_kb_env, monkeypatch, builder):
        """Inside the fence, the wrapper's own assertion tells the model to treat
        the text as content to evaluate rather than a caveat to honour — and a
        page body carrying a forged copy would be indistinguishable from the
        real notice. The forged copy below is what makes this test diverge: it
        appears INSIDE the fence, the real notice OUTSIDE, and position is the
        only thing that tells them apart."""
        from kb.lint import semantic

        ref = _write_raw(tmp_kb_env, "raw/articles/a.md", "source text")
        forged = f"*[{context._PAGE_TRUNCATION_MARKER}: 1 of 1 bytes read]*"
        _write_page(tmp_kb_env / "wiki", "concepts/p", body=forged + "z" * 40_000, source=[ref])
        monkeypatch.setattr(context, "PAIRED_PAGE_READ_MAX_BYTES", 900)
        build = {
            "review": context.build_review_context,
            "fidelity": semantic.build_fidelity_context,
            "completeness": semantic.build_completeness_context,
        }[builder]

        out = build("concepts/p", tmp_kb_env / "wiki", tmp_kb_env / "raw")

        assert out.index(context._PAGE_TRUNCATION_MARKER) < out.index("<wiki_context>")

    @pytest.mark.parametrize("builder", ["review", "fidelity", "completeness"])
    def test_budget_error_reaches_every_builder_as_text(self, tmp_kb_env, monkeypatch, builder):
        """A dict that still carried ``page_content`` would slip past each
        builder's ``"page_content" not in paired`` guard and raise ``KeyError``
        on ``paired['page_metadata']`` instead of returning a message."""
        from kb.lint import semantic

        page_path = tmp_kb_env / "wiki" / "concepts" / "fat.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(
            '---\ntitle: "T"\nnotes: "' + "n" * 8_000 + '"\n---\n\nbody\n', encoding="utf-8"
        )
        monkeypatch.setattr(context, "PAIRED_PAGE_READ_MAX_BYTES", 1_000)
        build = {
            "review": context.build_review_context,
            "fidelity": semantic.build_fidelity_context,
            "completeness": semantic.build_completeness_context,
        }[builder]

        out = build("concepts/fat", tmp_kb_env / "wiki", tmp_kb_env / "raw")

        assert out.startswith("Error")
        assert "budget" in out.lower()

    def test_fidelity_context_announces_source_truncation(self, tmp_kb_env, monkeypatch):
        """Design-gate T5.1 — cycle 96 wired the SOURCE notice into
        ``build_review_context`` only, so ``kb_lint_deep`` rendered a
        partially-read source as if it were whole. Shipping the page half into
        three builders while leaving this asymmetric would repeat, in the same
        commit, the defect the cycle is closing."""
        from kb.lint import semantic

        ref = _write_raw(tmp_kb_env, "raw/articles/a.md", "S" * 20_000)
        _write_page(tmp_kb_env / "wiki", "concepts/p", body="short", source=[ref])
        monkeypatch.setattr(context, "PAIRED_SOURCE_READ_MAX_BYTES", 1_000)

        out = semantic.build_fidelity_context("concepts/p", tmp_kb_env / "wiki", tmp_kb_env / "raw")

        assert context._SOURCE_TRUNCATION_MARKER in out

    def test_page_notice_is_distinct_from_the_source_notice(self):
        """Different remedies: raise the page budget vs raise the source budget.
        One shared string would send the operator to the wrong constant."""
        assert context._PAGE_TRUNCATION_MARKER != context._SOURCE_TRUNCATION_MARKER

    def test_review_context_stays_within_the_assembly_cap_with_the_notice(
        self, tmp_kb_env, monkeypatch
    ):
        """cycle-96 AC03 invariant must survive the added notice."""
        self._big_page(tmp_kb_env)
        monkeypatch.setattr(context, "PAIRED_PAGE_READ_MAX_BYTES", 800)
        monkeypatch.setattr(context, "QUERY_CONTEXT_MAX_CHARS", 4_000)

        out = context.build_review_context("concepts/p", tmp_kb_env / "wiki", tmp_kb_env / "raw")

        assert len(out) <= 4_000


# --------------------------------------------------------------------------
# AC06 / AC07 — the shared hot path is untouched
# --------------------------------------------------------------------------


class TestSharedHotPathUntouched:
    def test_load_page_frontmatter_still_reads_whole_and_still_caches(self, tmp_kb_env):
        """The lint/query hot path keeps its unbounded cached read — bounding it
        would change what every caller sees, which is why cycle 96 deferred it."""
        from kb.utils import pages as pages_mod

        page_path = _write_page(tmp_kb_env / "wiki", "concepts/p", body="v" * 40_000)
        pages_mod.load_page_frontmatter.cache_clear()

        _metadata, body = pages_mod.load_page_frontmatter(page_path)

        assert len(body) >= 40_000
        assert hasattr(pages_mod.load_page_frontmatter, "cache_clear")
        assert pages_mod._load_page_frontmatter_cached.cache_info().maxsize == 8192

    def test_paired_path_does_not_use_the_cached_full_read(self, tmp_kb_env, monkeypatch):
        """AC07 — deliberate contract change vs cycle-13 AC12. Making the old
        reader explosive is what makes every other test in this file honest: if
        the paired path still routed through it, the bound would be cosmetic."""
        from kb.utils import pages as pages_mod

        _write_page(tmp_kb_env / "wiki", "concepts/p", body="v" * 5_000)

        def _boom(*args, **kwargs):
            raise AssertionError("paired context must use the bounded page reader")

        monkeypatch.setattr(pages_mod, "_load_page_frontmatter_cached", _boom)
        monkeypatch.setattr(context, "load_page_frontmatter", _boom, raising=False)

        result = _pair(tmp_kb_env, "concepts/p")

        assert "error" not in result, result.get("error")
        assert result["page_metadata"]["title"] == "T"

    def test_missing_page_still_reports_not_found(self, tmp_kb_env):
        result = _pair(tmp_kb_env, "concepts/absent")

        assert result["error"].startswith("Page not found")

    def test_traversal_guard_runs_before_any_read(self, tmp_kb_env):
        result = _pair(tmp_kb_env, "../../etc/passwd")

        assert "escapes wiki directory" in result["error"]


@pytest.mark.parametrize("budget", [0, -1])
def test_non_positive_budget_does_not_crash(tmp_kb_env, budget):
    """A misconfigured cap must degrade to a loud refusal, not a crash and not a
    silently empty page."""
    _write_page(tmp_kb_env / "wiki", "concepts/p", body="body text")

    result = _pair(tmp_kb_env, "concepts/p", page_read_budget=budget)

    assert "error" in result
    assert "budget" in result["error"].lower()
