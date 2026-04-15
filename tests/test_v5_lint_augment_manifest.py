"""Manifest state machine: per-gap pending → proposed → fetched → saved → extracted → ingested → verdict → done."""
import json
import uuid


def _make_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr("kb.lint._augment_manifest.MANIFEST_DIR", tmp_path)
    from kb.lint._augment_manifest import Manifest
    run_id = str(uuid.uuid4())
    stubs = [
        {"page_id": "concepts/foo", "title": "Foo"},
        {"page_id": "entities/bar", "title": "Bar"},
    ]
    return Manifest.start(run_id=run_id, mode="propose", max_gaps=5, stubs=stubs), run_id


def test_start_writes_initial_manifest(tmp_path, monkeypatch):
    m, run_id = _make_manifest(tmp_path, monkeypatch)
    files = list(tmp_path.glob("augment-run-*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["run_id"] == run_id
    assert data["schema"] == 1
    assert data["ended_at"] is None
    assert len(data["gaps"]) == 2
    for gap in data["gaps"]:
        assert gap["state"] == "pending"
        assert gap["transitions"] == [{"state": "pending", "ts": gap["transitions"][0]["ts"]}]


def test_advance_appends_transition(tmp_path, monkeypatch):
    m, run_id = _make_manifest(tmp_path, monkeypatch)
    m.advance("concepts/foo", "proposed", payload={"urls": ["https://wikipedia.org/wiki/Foo"]})
    data = json.loads((tmp_path / f"augment-run-{run_id[:8]}.json").read_text())
    foo_gap = next(g for g in data["gaps"] if g["page_id"] == "concepts/foo")
    assert foo_gap["state"] == "proposed"
    assert len(foo_gap["transitions"]) == 2
    assert foo_gap["transitions"][1]["state"] == "proposed"
    assert foo_gap["transitions"][1]["payload"]["urls"] == ["https://wikipedia.org/wiki/Foo"]


def test_advance_to_terminal_state(tmp_path, monkeypatch):
    m, run_id = _make_manifest(tmp_path, monkeypatch)
    m.advance("entities/bar", "abstained", payload={"reason": "out of scope"})
    data = json.loads((tmp_path / f"augment-run-{run_id[:8]}.json").read_text())
    bar_gap = next(g for g in data["gaps"] if g["page_id"] == "entities/bar")
    assert bar_gap["state"] == "abstained"


def test_close_writes_ended_at(tmp_path, monkeypatch):
    m, run_id = _make_manifest(tmp_path, monkeypatch)
    m.close()
    data = json.loads((tmp_path / f"augment-run-{run_id[:8]}.json").read_text())
    assert data["ended_at"] is not None
    # ISO 8601 with Z or +00:00
    assert "T" in data["ended_at"]


def test_resume_finds_incomplete_run(tmp_path, monkeypatch):
    monkeypatch.setattr("kb.lint._augment_manifest.MANIFEST_DIR", tmp_path)
    from kb.lint._augment_manifest import Manifest
    run_id = "abcd1234-5678-90ab-cdef-1234567890ab"
    initial = {
        "schema": 1, "run_id": run_id, "started_at": "2026-04-15T14:00:00Z",
        "ended_at": None, "mode": "auto_ingest", "max_gaps": 5,
        "gaps": [
            {"page_id": "concepts/x", "state": "ingested", "transitions": []},
            {"page_id": "concepts/y", "state": "fetched", "transitions": []},
        ],
    }
    (tmp_path / f"augment-run-{run_id[:8]}.json").write_text(json.dumps(initial))
    m = Manifest.resume(run_id_prefix="abcd1234")
    assert m is not None
    assert m.run_id == run_id
    incomplete = m.incomplete_gaps()
    assert {g["page_id"] for g in incomplete} == {"concepts/y"}


def test_resume_returns_none_for_unknown_run(tmp_path, monkeypatch):
    monkeypatch.setattr("kb.lint._augment_manifest.MANIFEST_DIR", tmp_path)
    from kb.lint._augment_manifest import Manifest
    assert Manifest.resume(run_id_prefix="zzzzzzzz") is None


def test_runs_index_is_appended_on_close(tmp_path, monkeypatch):
    monkeypatch.setattr("kb.lint._augment_manifest.MANIFEST_DIR", tmp_path)
    monkeypatch.setattr("kb.lint._augment_manifest.RUNS_INDEX_PATH", tmp_path / "augment_runs.jsonl")
    m, run_id = _make_manifest(tmp_path, monkeypatch)
    m.advance("concepts/foo", "done")
    m.advance("entities/bar", "abstained", payload={"reason": "x"})
    m.close()
    lines = (tmp_path / "augment_runs.jsonl").read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["run_id"] == run_id
    assert entry["gaps_succeeded"] == 1  # done
    assert entry["gaps_abstained"] == 1
    assert entry["gaps_failed"] == 0
