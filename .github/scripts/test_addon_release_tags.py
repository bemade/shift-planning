# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from addon_release_tags import discover_release_tags


class TestDiscoverReleaseTags(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary_directory.name)
        self._git("init", "--initial-branch=19.0")
        self._git("config", "user.name", "CI Test")
        self._git("config", "user.email", "ci@example.com")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _git(self, *args):
        return subprocess.run(
            ["git", *args],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def _write_manifest(self, addon, version):
        addon_directory = self.repo / addon
        addon_directory.mkdir(parents=True, exist_ok=True)
        (addon_directory / "__manifest__.py").write_text(
            repr({"name": addon, "version": version}) + "\n",
            encoding="utf-8",
        )

    def _commit(self, message):
        self._git("add", "--all")
        self._git("commit", "--message", message)
        return self._git("rev-parse", "HEAD")

    def test_version_change_publishes_addon_version_tag(self):
        self._write_manifest("hr_shift", "19.0.1.0.0")
        before = self._commit("Initial version")

        self._write_manifest("hr_shift", "19.0.1.0.1")
        after = self._commit("Release hr_shift")

        releases = discover_release_tags(self.repo, before, after)

        self.assertEqual(
            [(release.addon, release.version, release.tag) for release in releases],
            [("hr_shift", "19.0.1.0.1", "hr_shift/19.0.1.0.1")],
        )

    def test_manifest_change_without_version_change_does_not_publish(self):
        self._write_manifest("hr_shift", "19.0.1.0.0")
        before = self._commit("Initial version")

        manifest = self.repo / "hr_shift" / "__manifest__.py"
        manifest.write_text(
            repr({"name": "Employees Shifts", "version": "19.0.1.0.0"}) + "\n",
            encoding="utf-8",
        )
        after = self._commit("Change metadata only")

        self.assertEqual(discover_release_tags(self.repo, before, after), [])

    def test_new_addon_and_multiple_version_changes_are_sorted(self):
        self._write_manifest("hr_shift", "19.0.1.0.0")
        self._write_manifest("hr_shift_request", "19.0.1.0.0")
        before = self._commit("Initial versions")

        self._write_manifest("hr_shift_request", "19.0.1.1.0")
        self._write_manifest("hr_shift", "19.0.1.0.1")
        self._write_manifest("hr_shift_new", "19.0.1.0.0")
        after = self._commit("Release several addons")

        releases = discover_release_tags(self.repo, before, after)

        self.assertEqual(
            [release.tag for release in releases],
            [
                "hr_shift/19.0.1.0.1",
                "hr_shift_new/19.0.1.0.0",
                "hr_shift_request/19.0.1.1.0",
            ],
        )

    def test_deleted_addon_is_ignored(self):
        self._write_manifest("hr_shift", "19.0.1.0.0")
        before = self._commit("Initial version")

        (self.repo / "hr_shift" / "__manifest__.py").unlink()
        after = self._commit("Remove addon")

        self.assertEqual(discover_release_tags(self.repo, before, after), [])

    def test_invalid_version_is_rejected(self):
        self._write_manifest("hr_shift", "19.0.1.0.0")
        before = self._commit("Initial version")

        self._write_manifest("hr_shift", "not-a-version")
        after = self._commit("Invalid release")

        with self.assertRaisesRegex(ValueError, "Invalid Odoo version"):
            discover_release_tags(self.repo, before, after)


if __name__ == "__main__":
    unittest.main()
