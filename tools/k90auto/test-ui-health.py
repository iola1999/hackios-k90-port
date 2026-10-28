#!/usr/bin/env python3
"""覆盖已发生的 backboardd 漏报、日志截断和重复采集边界。"""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("ui_health", Path(__file__).with_name("ui-health.py"))
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)


class UIHealthTests(unittest.TestCase):
    def inspect(self, *texts, processes=("SpringBoard", "backboardd")):
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for index, text in enumerate(texts):
                path = Path(directory) / f"{index}.log"
                path.write_text(text)
                paths.append(path)
            return health.inspect_logs(paths, processes)

    def test_backboard_abort_survives_nul_and_duplicate_captures(self):
        log = "SpringBoard[30:1] ready\x00\nbackboardd[34:2] ready\nuserabort: backboardd[34] aborts\n"
        result = self.inspect(log, log)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failures"], ["backboardd: userabort"])

    def test_restart_detected_across_nonoverlapping_logs(self):
        result = self.inspect("SpringBoard[30:1]\nbackboardd[34:2]\n", "SpringBoard[67:1]\nbackboardd[65:2]\n")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["process_pids"]["backboardd"], [34, 65])

    def test_repeated_same_pid_is_observed(self):
        log = "SpringBoard[30:1]\nbackboardd[34:2]\n"
        result = self.inspect(log, log)
        self.assertEqual(result["status"], "observed")

    def test_missing_log_data_requires_review(self):
        result = self.inspect("SpringBoard[30:1] ready\n")
        self.assertEqual(result["status"], "review_required")
        self.assertEqual(result["missing_processes"], ["backboardd"])

    def test_unassigned_assertion_requires_review(self):
        result = self.inspect("SpringBoard[30:1]\nbackboardd[34:2]\nAssertion failed: (found), function push_surface\n")
        self.assertEqual(result["status"], "review_required")
        self.assertEqual(result["unassigned_assertion_count"], 1)

    def test_foreground_trap_is_checked_when_requested(self):
        result = self.inspect("SpringBoard[30:1]\nbackboardd[34:2]\nusertrap: Preferences[64] fault\n", processes=("SpringBoard", "backboardd", "Preferences"))
        self.assertIn("Preferences: usertrap", result["failures"])

    def test_unrelated_process_does_not_add_ui_restart(self):
        result = self.inspect("SpringBoard[30:1]\nbackboardd[34:2]\nuserabort: wifid[40] aborts\n")
        self.assertEqual(result["status"], "observed")

    def test_kernel_panic_fails(self):
        result = self.inspect("SpringBoard[30:1]\nbackboardd[34:2]\x00panic(cpu 0 caller 0x1): fault\n")
        self.assertIn("kernel panic", result["failures"])


if __name__ == "__main__":
    unittest.main()
