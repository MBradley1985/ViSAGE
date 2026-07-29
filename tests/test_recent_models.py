"""Session-models registry: remembers boxes + lightcones for the Launch menu."""

from __future__ import annotations

from visage.utils import recent_models as rm


def _touch(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("")
    return str(p)


def test_record_dedup_promote_and_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "_REGISTRY", tmp_path / "session_models.json")

    millennium = _touch(tmp_path / "sims" / "millennium.par")
    lightcone = _touch(tmp_path / "out" / "lightcone.h5")

    rm.record("millennium", "box", millennium)
    rm.record("lc", "lightcone", lightcone)
    entries = rm.load()
    # most-recent first
    assert [e["name"] for e in entries] == ["lc", "millennium"]
    assert [e["kind"] for e in entries] == ["lightcone", "box"]

    # re-recording the box promotes it to the front, no duplicate
    rm.record("millennium", "box", millennium)
    entries = rm.load()
    assert [e["name"] for e in entries] == ["millennium", "lc"]
    assert len(entries) == 2

    # dedup is per (kind, path): same path, different kind => separate entry
    rm.record("millennium", "lightcone", millennium)
    assert len(rm.load()) == 3

    # cap
    for i in range(20):
        rm.record(f"m{i}", "box", _touch(tmp_path / "sims" / f"m{i}.par"))
    assert len(rm.load()) <= rm._CAP


def test_load_missing_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "_REGISTRY", tmp_path / "nope.json")
    assert rm.load() == []


def test_load_prunes_entries_whose_file_no_longer_exists(
    tmp_path, monkeypatch
):
    # A path can go stale (moved, deleted, or a throwaway test file from
    # outside a normal session) — load() must drop it rather than keep
    # showing a dead entry in the Launch-mode dropdown forever.
    monkeypatch.setattr(rm, "_REGISTRY", tmp_path / "session_models.json")

    kept = _touch(tmp_path / "real.par")
    gone = tmp_path / "deleted.h5"
    _touch(gone)
    rm.record("real", "box", kept)
    rm.record("deleted", "lightcone", str(gone))
    assert len(rm.load()) == 2

    gone.unlink()
    entries = rm.load()
    assert [e["name"] for e in entries] == ["real"]

    # ...and that pruning is persisted, not just filtered for this call.
    assert len(rm._load_raw()) == 1


def test_record_also_prunes_before_inserting(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "_REGISTRY", tmp_path / "session_models.json")

    gone = tmp_path / "deleted.h5"
    _touch(gone)
    rm.record("deleted", "lightcone", str(gone))
    gone.unlink()

    new = _touch(tmp_path / "new.par")
    entries = rm.record("new", "box", new)
    assert [e["name"] for e in entries] == ["new"]
