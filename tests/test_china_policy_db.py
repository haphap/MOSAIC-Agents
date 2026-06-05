from __future__ import annotations

from pathlib import Path

from mosaic.dataflows import china_policy_db


def test_ensure_local_repo_clones_missing_configured_dir(tmp_path, monkeypatch):
    root = tmp_path / "china-policy-db"
    calls: list[tuple[list[str], Path | None]] = []
    monkeypatch.setenv("MOSAIC_CHINA_POLICY_DB_DIR", str(root))
    monkeypatch.setenv("MOSAIC_CHINA_POLICY_DB_REPO_URL", "https://example.test/policy.git")
    monkeypatch.setenv("MOSAIC_CHINA_POLICY_DB_AUTO_SYNC", "1")

    def fake_run_git(args: list[str], *, cwd: Path | None = None) -> str:
        calls.append((args, cwd))
        if args[:2] == ["clone", "--depth=1"]:
            clone_root = Path(args[-1])
            clone_root.mkdir(parents=True)
            (clone_root / ".git").mkdir()
        return ""

    monkeypatch.setattr(china_policy_db, "_run_git", fake_run_git)

    found = china_policy_db.ensure_local_repo()

    assert found == (root, str(root))
    assert calls == [
        (["clone", "--depth=1", "https://example.test/policy.git", str(root)], None)
    ]
    assert (root / ".git" / "mosaic-sync.json").is_file()
