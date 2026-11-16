import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path[:0] = [
    str(Path(__file__).resolve().parents[1] / "scripts"),
    str(Path(__file__).resolve().parents[1] / "src"),
]
from publication_guard import report


class GuardReportingTests(unittest.TestCase):
    def setUp(self):
        self.pr = {"state": "open", "base": {"ref": "main"}, "head": {"sha": "a" * 40}}
        self.statuses = []

        def api(method, path, data=None):
            if method == "GET":
                self.assertEqual(path, "/pulls/10")
                return copy.deepcopy(self.pr)
            self.assertEqual(path, "/statuses/" + "a" * 40)
            self.assertEqual(data["context"], "publication-safety")
            self.statuses.append(data["state"])

        self.github = SimpleNamespace(api=api)

    def test_success_is_posted_only_after_running_guard(self):
        def checked(github, head):
            self.assertIs(github, self.github)
            self.assertEqual(head, "a" * 40)
            self.assertEqual(self.statuses, ["pending"])

        with patch("publication_guard.check", side_effect=checked) as guard:
            report(self.github, 10, "a" * 40)
        guard.assert_called_once()
        self.assertEqual(self.statuses, ["pending", "success"])

    def test_unsafe_publication_reports_failure(self):
        with (
            patch("publication_guard.check", side_effect=ValueError("Unsafe")),
            self.assertRaisesRegex(ValueError, "Unsafe"),
        ):
            report(self.github, 10, "a" * 40)
        self.assertEqual(self.statuses, ["pending", "failure"])

    def test_queued_check_never_reports_on_a_new_head(self):
        with (
            patch("publication_guard.check") as guard,
            self.assertRaisesRegex(ValueError, "changed"),
        ):
            report(self.github, 10, "b" * 40)
        guard.assert_not_called()
        self.assertFalse(self.statuses)

    def test_head_change_during_validation_cannot_report_success(self):
        def changed(*args):
            self.pr["head"]["sha"] = "b" * 40

        with (
            patch("publication_guard.check", side_effect=changed),
            self.assertRaisesRegex(ValueError, "changed"),
        ):
            report(self.github, 10, "a" * 40)
        self.assertEqual(self.statuses, ["pending", "failure"])

    def test_closed_or_retargeted_pr_is_rejected(self):
        for changes in ({"state": "closed"}, {"base": {"ref": "other"}}):
            with (
                self.subTest(changes=changes),
                patch("publication_guard.check") as guard,
            ):
                self.pr.update(changes)
                with self.assertRaises(ValueError):
                    report(self.github, 10, "a" * 40)
                guard.assert_not_called()
        self.assertFalse(self.statuses)
