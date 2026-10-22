"""visage --diagnose: a failing check is logged and the rest still run."""

from __future__ import annotations


def test_a_failing_step_is_logged_and_the_run_continues(tmp_path):
    from visage.diagnose import _Log, _step

    log = _Log(tmp_path / "d.txt")

    def boom():
        raise RuntimeError("no GPU here")

    _step(log, "GPU", boom)
    _step(log, "CPU", lambda: log("   fine"))
    text = (tmp_path / "d.txt").read_text()
    assert "FAILED: RuntimeError: no GPU here" in text
    assert "== CPU" in text and "fine" in text


def test_cli_has_the_diagnose_flag():
    from visage.cli import build_parser

    assert build_parser().parse_args(["--diagnose"]).diagnose


def test_cli_can_skip_the_browser_test():
    from visage.cli import build_parser

    args = build_parser().parse_args(["--diagnose", "--no-browser"])
    assert args.diagnose and args.no_browser
