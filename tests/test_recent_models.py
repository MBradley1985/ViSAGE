"""Session-models registry: remembers boxes + lightcones for the Launch menu."""

from __future__ import annotations

from visage.utils import recent_models as rm


def test_record_dedup_promote_and_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "_REGISTRY", tmp_path / "session_models.json")

    rm.record("millennium", "box", "/sims/millennium.par")
    rm.record("lc", "lightcone", "/out/lightcone.h5")
    entries = rm.load()
    # most-recent first
    assert [e["name"] for e in entries] == ["lc", "millennium"]
    assert [e["kind"] for e in entries] == ["lightcone", "box"]

    # re-recording the box promotes it to the front, no duplicate
    rm.record("millennium", "box", "/sims/millennium.par")
    entries = rm.load()
    assert [e["name"] for e in entries] == ["millennium", "lc"]
    assert len(entries) == 2

    # dedup is per (kind, path): same path, different kind => separate entry
    rm.record("millennium", "lightcone", "/sims/millennium.par")
    assert len(rm.load()) == 3

    # cap
    for i in range(20):
        rm.record(f"m{i}", "box", f"/sims/m{i}.par")
    assert len(rm.load()) <= rm._CAP


def test_load_missing_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "_REGISTRY", tmp_path / "nope.json")
    assert rm.load() == []
