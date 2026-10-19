"""
Tests for the scheduled-backup parts of scripts/prod_ops.py. They need only Python 3 (no Docker, no database):

    python -m unittest scripts/test_prod_ops.py -v        (from the project folder)

What went wrong in real use, and what these tests keep from coming back:
  * the scheduler's command line wrote to backup.log, the same file prod_ops appends to  -> PermissionError, backup failed;
  * the 02:00 run started before Docker Desktop was ready                                -> "failed to connect to the docker API";
  * a failed attempt left an empty dated folder that counted as a backup in the retention count.
"""
import argparse
import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("prod_ops_under_test", HERE / "prod_ops.py")
ops = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ops)


def args(**kw):
    base = dict(out="x", keep=14, copy_to=None, wait_docker=0, retries=0, retry_wait=0)
    base.update(kw)
    return argparse.Namespace(**base)


class ScheduledCommandLine(unittest.TestCase):
    def test_it_writes_to_its_own_log_not_to_backup_log(self):
        text = ops.run_backup_cmd_text(r"C:\cdr", r"C:\Py\python.exe", r"D:\off", True)
        self.assertIn(r">> backups\prod\scheduled_run.log 2>&1", text)
        self.assertNotIn(r">> backups\prod\backup.log", text)

    def test_it_waits_for_docker_and_retries(self):
        text = ops.run_backup_cmd_text(r"C:\cdr", r"C:\Py\python.exe")
        self.assertIn("--wait-docker 10", text)
        self.assertIn("--retries 2", text)
        self.assertIn("--purge", text)

    def test_purge_and_copy_target_are_optional(self):
        text = ops.run_backup_cmd_text(r"C:\cdr", r"C:\Py\python.exe", None, False)
        self.assertNotIn("--purge", text)
        self.assertNotIn("--copy-to", text)
        self.assertIn('--copy-to "D:\\off"', ops.run_backup_cmd_text(r"C:\cdr", "p", r"D:\off"))

    def test_the_task_is_allowed_to_run_on_battery_catch_up_and_wake(self):
        ps = ops.task_settings_ps()
        for flag in ("-AllowStartIfOnBatteries", "-DontStopIfGoingOnBatteries", "-StartWhenAvailable", "-WakeToRun", "-RestartCount 3"):
            self.assertIn(flag, ps)
        self.assertIn("'CDR-Backup'", ps)


class DockerWait(unittest.TestCase):
    def test_no_wait_asked_means_no_check(self):
        with mock.patch.object(ops, "docker_ready", side_effect=AssertionError("must not be asked")):
            self.assertTrue(ops.ensure_docker(0))

    def test_ready_at_once(self):
        with mock.patch.object(ops, "docker_ready", return_value=True):
            self.assertTrue(ops.ensure_docker(5))

    def test_becomes_ready_while_waiting(self):
        answers = iter([False, False, True])
        with mock.patch.object(ops, "docker_ready", side_effect=lambda: next(answers)), mock.patch.object(ops, "SLEEP", 0.001), \
                mock.patch.object(ops.time, "sleep"):
            self.assertTrue(ops.ensure_docker(5))

    def test_gives_up_after_the_time_allowed(self):
        with mock.patch.object(ops, "docker_ready", return_value=False), mock.patch.object(ops, "SLEEP", 0.001):
            self.assertFalse(ops.ensure_docker(0.0003))      # about 0.02 s


class Retries(unittest.TestCase):
    def test_second_attempt_succeeds(self):
        calls = []

        def fake(*a, **k):
            calls.append(1)
            if len(calls) == 1:
                raise ops.Fail("docker compose exec -T db ... failed (exit 1)")
            return ("folder", None)
        with mock.patch.object(ops, "make_backup", side_effect=fake), mock.patch.object(ops, "ensure_docker", return_value=True), \
                mock.patch.object(ops.time, "sleep"):
            self.assertEqual(ops.backup_with_retries(args(retries=2)), ("folder", None))
        self.assertEqual(len(calls), 2)

    def test_it_stops_after_the_last_attempt(self):
        with mock.patch.object(ops, "make_backup", side_effect=ops.Fail("down")) as m, mock.patch.object(ops, "ensure_docker", return_value=True), \
                mock.patch.object(ops.time, "sleep"):
            with self.assertRaises(ops.Fail):
                ops.backup_with_retries(args(retries=2))
        self.assertEqual(m.call_count, 3)

    def test_no_retries_by_default(self):
        with mock.patch.object(ops, "make_backup", side_effect=ops.Fail("down")) as m, mock.patch.object(ops, "ensure_docker", return_value=True):
            with self.assertRaises(ops.Fail):
                ops.backup_with_retries(args())
        self.assertEqual(m.call_count, 1)

    def test_docker_never_ready_ends_with_a_clear_message(self):
        with mock.patch.object(ops, "make_backup") as m, mock.patch.object(ops, "ensure_docker", return_value=False), mock.patch.object(ops.time, "sleep"):
            with self.assertRaises(ops.Fail) as cm:
                ops.backup_with_retries(args(wait_docker=10, retries=1))
        self.assertIn("Docker is not running", str(cm.exception))
        m.assert_not_called()

    def test_docker_ready_on_a_later_attempt_still_backs_up(self):
        ready = iter([False, True])
        with mock.patch.object(ops, "make_backup", return_value=("f", None)) as m, mock.patch.object(ops, "ensure_docker", side_effect=lambda _m: next(ready)), \
                mock.patch.object(ops.time, "sleep"):
            # first pass: Docker not ready but a retry remains -> the attempt is still made and may fail; here it succeeds
            self.assertEqual(ops.backup_with_retries(args(wait_docker=10, retries=1)), ("f", None))
        self.assertEqual(m.call_count, 1)


class FailedAttemptLeavesNothing(unittest.TestCase):
    def test_partial_folder_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(ops, "sh_in", side_effect=ops.Fail("db down")):
            with self.assertRaises(ops.Fail):
                ops.make_backup(tmp, 14)
            self.assertEqual([p for p in pathlib.Path(tmp).iterdir()], [])

    def test_a_locked_log_does_not_fail_the_backup(self):
        # a folder that does not exist cannot be opened for writing: the history line is skipped with a warning, no exception
        ops.append_log(pathlib.Path(tempfile.gettempdir()) / "no-such-folder-cdr", "x\n")


if __name__ == "__main__":
    unittest.main()
