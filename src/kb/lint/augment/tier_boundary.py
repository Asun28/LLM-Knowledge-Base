"""Scan-tier → orchestrate-tier boundary verifier.

Cycle 73 AC03 introduced ``_validate_tier_boundary`` inside
``orchestrator.py``; cycle 74 AC02 extracts it into this leaf module so
``proposer.py`` (which ``orchestrator.py`` imports at module level) can
apply the same re-gate at its two scan-tier ``_call_llm_json`` call sites
without a circular import. ``orchestrator.py`` re-exports both names, so
the cycle-73 monkeypatch surface (``orch_mod._validate_tier_boundary``)
is unchanged.

Purpose: bound the BLAST RADIUS of cycle-72's prompt-injection
probability reduction (T4 EscalationOfPrivilege per cycle-73 threat
model). The cycle-7..72 wrap_wiki_context family REDUCES the
probability that an LLM follows attacker instructions, but does NOT
stop a successful injection from propagating malformed JSON into the
orchestrate-tier consumers. This validator re-gates the scan-tier
output against orchestrate-tier consumption rules — a stricter pass
than the JSON-schema validation already performed inside
``_call_llm_json``.

Default bounds (per cycle-73 design-decision Q3 + cycle-74 AC01):
  - max_depth=4    — root + 3 sub-levels covers article-extraction
                      schemas with 1 level of slack (extraction →
                      evidence list → claim dict → leaf strings).
  - max_string_len=4096 — near-neighbour of MAX_ISSUE_DESCRIPTION_LEN
                           (4000) with 96-char slack for IDs/timestamps.
  - max_keys=500   — cycle-74 AC01 (closes cycle-73 R2 DeepSeek F-2):
                      caps the key count of the root dict AND every
                      nested dict so a scan-tier-with-broad-schema
                      response cannot exhaust memory in the depth
                      walker before the depth/type checks fire.

Anti-spoofing (T5): callers MUST derive ``expected_keys`` (and cycle-74
AC03's ``required_keys``) from the locally-built JSONSchema (e.g.
``frozenset(schema['properties'].keys())`` /
``frozenset(schema.get('required', []))``) — NEVER from
``scan_output.keys()`` itself.
"""

from __future__ import annotations

from collections.abc import Mapping

from kb.errors import TierBoundaryError, ValueDomainError

_TBV_ALLOWED_VALUE_TYPES = (str, int, float, type(None), list, dict)


def _validate_tier_boundary(
    scan_output: object,
    *,
    expected_keys: frozenset[str],
    required_keys: frozenset[str] = frozenset(),
    allowed_values: Mapping[str, frozenset] | None = None,
    max_depth: int = 4,
    max_string_len: int = 4096,
    max_keys: int = 500,
) -> dict:
    """Re-gate a scan-tier ``_call_llm_json`` output before orchestrate-tier
    consumption. Raises ``TierBoundaryError`` on any rejection; returns
    ``scan_output`` unchanged on acceptance.

    Rejections (per cycle-73 design-decision §3 + threat-model T4/T5/T6,
    extended by cycle-74 AC01/AC03):
        1. Top-level not a ``dict``.
        2. Root dict (or any nested dict) with more than ``max_keys``
           keys (cycle-74 AC01 DoS bound — checked BEFORE the extra-key
           set difference so a pathological key count never reaches the
           more expensive checks).
        3. Any key not in ``expected_keys`` (rejects LLM-injected
           ``side_effects`` / ``__proto__`` / etc.).
        4. Any key in ``required_keys`` MISSING from the root dict
           (cycle-74 AC03 — derived from the schema's ``"required"``
           list; the empty default preserves the cycle-73 contract that
           optional-field subsets are accepted).
        5. Any ROOT-LEVEL key listed in ``allowed_values`` whose value is
           outside its permitted set (cycle-86 AC02 — raises the
           ``ValueDomainError`` subclass so callers can split-catch it
           for a forensically distinct manifest reason).
        6. Any string value longer than ``max_string_len`` (length bound).
        7. Any nested structure deeper than ``max_depth`` (DoS bound).
        8. Any value not in ``_TBV_ALLOWED_VALUE_TYPES`` (rejects custom
           classes if Pydantic / pickle is bypassed). ``bool`` is
           explicitly accepted via the int branch (it's a Python bool
           subclass) — JSON true/false round-trip cleanly.

    Missing keys outside ``required_keys`` are NOT a rejection cause —
    schema-level optional fields are allowed. Downstream consumers use
    ``.get(...)`` to handle missing.

    ``allowed_values`` (cycle-86 AC02) closes the VALUE domain, which the
    cycle-73/74 key-domain checks left open: ``{"action": "exfiltrate"}``
    has a legal key set and a legal shape, so before cycle 86 it passed
    the boundary untouched and each call site re-implemented the
    membership test by hand. Scope is deliberately ROOT-LEVEL keys only —
    supporting nested paths (``items[].kind``) would mean inventing a
    path mini-language inside a security validator. Nested enums stay
    enforced by ``_call_llm_json``'s jsonschema pass; see the cycle-86
    design doc Q3 for the full argument and the filed follow-up.

    A key named in ``allowed_values`` but ABSENT from ``scan_output`` is
    NOT a rejection — absence is the ``required_keys`` check's job, and
    conflating the two would make every optional enum field mandatory.

    Anti-spoofing (T5, carried over unchanged from cycle 73): the
    permitted sets MUST be derived from the LOCAL schema (e.g.
    ``frozenset(schema['properties']['action']['enum'])``) — NEVER from
    ``scan_output`` itself, which would let the response authorise its
    own vocabulary.
    """
    if not isinstance(scan_output, dict):
        raise TierBoundaryError(
            "tier-boundary verification failed: scan_output is "
            f"{type(scan_output).__name__}, expected dict"
        )

    # Cycle-74 AC01 — cheap-first: bound the root key count before any
    # O(n) set arithmetic over the keys.
    if len(scan_output) > max_keys:
        raise TierBoundaryError(
            "tier-boundary verification failed: root dict has "
            f"{len(scan_output)} keys, exceeds max_keys={max_keys}"
        )

    extra = set(scan_output.keys()) - set(expected_keys)
    if extra:
        raise TierBoundaryError(
            "tier-boundary verification failed: extra key(s) not in "
            f"expected_keys: {sorted(extra)!r}"
        )

    # Cycle-74 AC03 — required-keys enforcement (schema "required" list).
    missing_required = set(required_keys) - set(scan_output.keys())
    if missing_required:
        raise TierBoundaryError(
            "tier-boundary verification failed: required key(s) missing: "
            f"{sorted(missing_required)!r}"
        )

    # Cycle-86 AC02 — value-domain gate. Runs AFTER the key-domain checks
    # (so an unexpected key is still reported as an unexpected key rather
    # than as a vocabulary miss) and BEFORE the depth walk (a rejected
    # vocabulary should not pay for a full traversal). Only root-level
    # keys present in BOTH maps are checked; absence is required_keys'
    # job, not this gate's.
    for key, permitted in (allowed_values or {}).items():
        if key not in scan_output:
            continue
        value = scan_output[key]
        # Membership on an unhashable value (list / dict) raises TypeError
        # rather than returning False, so screen for it explicitly — an
        # enum-typed field arriving as a list is itself out-of-vocabulary.
        try:
            in_vocabulary = value in permitted
        except TypeError:
            in_vocabulary = False
        if not in_vocabulary:
            raise ValueDomainError(
                "tier-boundary verification failed: value for key "
                f"{key!r} is not in the permitted vocabulary "
                f"{sorted(permitted, key=repr)!r} (got {value!r})"
            )

    # Walk values for depth + length + type. Depth counts the root dict
    # as level 1 — so max_depth=4 admits root → list → dict → str (4).
    def _walk(value: object, depth: int, key_path: str) -> None:
        if depth > max_depth:
            raise TierBoundaryError(
                "tier-boundary verification failed: nested structure "
                f"deeper than max_depth={max_depth} at {key_path!r}"
            )
        # bool is a subclass of int — handle it via the int branch (no
        # extra check needed; True/False are valid JSON literals).
        if isinstance(value, bool):
            return
        if not isinstance(value, _TBV_ALLOWED_VALUE_TYPES):
            raise TierBoundaryError(
                "tier-boundary verification failed: unsupported value "
                f"type {type(value).__name__} at {key_path!r}"
            )
        if isinstance(value, str):
            if len(value) > max_string_len:
                raise TierBoundaryError(
                    "tier-boundary verification failed: string at "
                    f"{key_path!r} exceeds max_string_len={max_string_len}"
                    f" (len={len(value)})"
                )
        elif isinstance(value, dict):
            # Cycle-74 AC01 — nested dicts get the same key-count bound
            # as the root (the extra-key check only covers the root, so
            # nested dicts are the realistic mass-key DoS surface).
            if len(value) > max_keys:
                raise TierBoundaryError(
                    "tier-boundary verification failed: nested dict at "
                    f"{key_path!r} has {len(value)} keys, exceeds "
                    f"max_keys={max_keys}"
                )
            for k, v in value.items():
                _walk(v, depth + 1, f"{key_path}.{k}")
        elif isinstance(value, list):
            for i, v in enumerate(value):
                _walk(v, depth + 1, f"{key_path}[{i}]")
        # int / float / None — leaf, no further checks.

    for key, val in scan_output.items():
        _walk(val, 2, key)  # root dict is level 1; values start at 2

    return scan_output
