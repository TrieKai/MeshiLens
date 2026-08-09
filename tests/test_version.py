from __future__ import annotations

import json
from pathlib import Path
import re
import tomllib
import unittest

from meshi_lens import __version__


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class VersionTests(unittest.TestCase):
    def test_release_version_is_synchronized(self) -> None:
        manifest = json.loads(
            (PROJECT_ROOT / "extension/manifest.json").read_text(encoding="utf-8")
        )
        pyproject = tomllib.loads(
            (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        lock_text = (PROJECT_ROOT / "uv.lock").read_text(encoding="utf-8")
        changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        lock_match = re.search(
            r'\[\[package\]\]\nname = "meshilens"\nversion = "([^"]+)"',
            lock_text,
        )
        changelog_match = re.search(
            r"^## \[(\d+\.\d+\.\d+)\]",
            changelog,
            re.MULTILINE,
        )
        self.assertIsNotNone(lock_match)
        self.assertIsNotNone(changelog_match)
        versions = {
            manifest["version"],
            pyproject["project"]["version"],
            __version__,
            lock_match.group(1),
            changelog_match.group(1),
        }
        self.assertEqual(versions, {__version__})


if __name__ == "__main__":
    unittest.main()
