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


class StackChoice(unittest.TestCase):
    """--stack staging points every command at the rehearsal copy; without it nothing changes (production), and production's files are never touched."""

    def setUp(self):
        ops.use_stack("production")

    def tearDown(self):
        ops.use_stack("production")

    @staticmethod
    def _command(project=None):
        with mock.patch.object(ops.subprocess, "run", return_value=argparse.Namespace(returncode=0, stdout="", stderr="")) as run:
            ops.compose(["ps"], project)
        return run.call_args[0][0]

    def test_production_is_the_default_and_is_unchanged(self):
        cmd = self._command()
        self.assertEqual(cmd[cmd.index("-p") + 1], "cdr-prod")
        self.assertEqual(cmd[cmd.index("--env-file") + 1], ".env.production")

    def test_staging_uses_its_own_project_and_secrets(self):
        ops.use_stack("staging")
        cmd = self._command()
        self.assertEqual(cmd[cmd.index("-p") + 1], "cdr-staging")
        self.assertEqual(cmd[cmd.index("--env-file") + 1], ".env.staging")

    def test_the_drill_project_keeps_the_env_file_of_the_stack_it_rehearses(self):
        ops.use_stack("staging")
        cmd = self._command(ops.DRILL)
        self.assertEqual(cmd[cmd.index("-p") + 1], "cdr-drill")
        self.assertEqual(cmd[cmd.index("--env-file") + 1], ".env.staging")

    def test_staging_status_file_never_overwrites_the_one_production_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, folder_name in (("production", "status"), ("staging", "staging-status")):
                ops.use_stack(name)
                out = pathlib.Path(tmp) / ("prod" if name == "production" else "staging")
                folder = out / "20261115T000000Z"
                folder.mkdir(parents=True)
                (folder / "db.dump").write_bytes(b"x")
                (folder / "uploads.tar").write_bytes(b"x")
                ops.write_status(out, "20261115T000000Z", folder, "rev", None, None)
                self.assertTrue((pathlib.Path(tmp) / folder_name / "last_backup.json").is_file(), name)
            self.assertEqual(sorted(p.name for p in pathlib.Path(tmp).iterdir() if p.name.endswith("status")), ["staging-status", "status"])

    def test_the_drill_teardown_refuses_staging_and_production(self):
        for stack in ("production", "staging"):
            ops.use_stack(stack)
            with mock.patch.object(ops, "compose") as c:
                ops.teardown_drill()
            self.assertEqual(c.call_args[0][1], "cdr-drill")

    def test_staging_is_never_scheduled(self):
        ops.use_stack("staging")
        with mock.patch.object(ops.subprocess, "run") as run:
            self.assertEqual(ops.cmd_schedule(argparse.Namespace(time="02:00", remove=False, copy_to=None, no_purge=False)), 2)
        run.assert_not_called()

    def test_restore_needs_the_word_of_its_own_stack(self):
        ops.use_stack("staging")
        with mock.patch.object(ops, "verify_sums", return_value=[]), mock.patch.object(ops, "compose") as c, \
                mock.patch("builtins.input", return_value="RESTORE-PRODUCTION"):
            self.assertEqual(ops.cmd_restore(argparse.Namespace(backup="x", no_safety_backup=True)), 1)
        c.assert_not_called()

    def _run_main(self, *argv):
        seen = {}
        def fake(a):
            seen["stack"], seen["out"] = ops.ACTIVE["name"], getattr(a, "out", None)
            return 0
        with mock.patch.object(ops, "cmd_status", fake), mock.patch("sys.argv", ["prod_ops.py", *argv]):
            self.assertEqual(ops.main(), 0)
        return seen

    def test_the_option_works_before_and_after_the_command(self):
        self.assertEqual(self._run_main("status"), {"stack": "production", "out": "backups/prod"})
        self.assertEqual(self._run_main("--stack", "staging", "status"), {"stack": "staging", "out": "backups/staging"})
        self.assertEqual(self._run_main("status", "--stack", "staging"), {"stack": "staging", "out": "backups/staging"})

    def test_an_explicit_out_folder_is_kept(self):
        self.assertEqual(self._run_main("status", "--stack", "staging", "--out", "somewhere")["out"], "somewhere")

    def test_a_stack_that_is_not_set_up_here_is_reported_not_run(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(ops, "ROOT", pathlib.Path(tmp)), mock.patch("sys.argv", ["prod_ops.py", "backup", "--stack", "staging"]), \
                mock.patch.object(ops, "cmd_backup") as backup:
            self.assertEqual(ops.main(), 2)
        backup.assert_not_called()


class RestoreUploadsOnLinux(unittest.TestCase):
    """On Linux the copied archive keeps the host user as owner, so root inside the hardened container cannot chmod or remove it (found on Ubuntu)."""

    def setUp(self):
        ops.use_stack("production")
        self.calls = []

    def _fake_run(self, failing):
        def run(cmd, **kw):
            self.calls.append(cmd)
            tail = " ".join(cmd)
            rc = 1 if any(word in tail for word in failing) else 0
            return argparse.Namespace(returncode=rc, stdout="", stderr="Operation not permitted" if rc else "")
        return run

    def test_chmod_and_removal_may_fail_without_failing_the_restore(self):
        with mock.patch.object(ops.subprocess, "run", self._fake_run(["chmod", "rm -f"])):
            ops.restore_uploads(ops.DRILL, "somewhere")
        joined = [" ".join(c) for c in self.calls]
        self.assertTrue(any("tar -C /app -xf" in c for c in joined), "the archive must still be unpacked")

    def test_a_failure_to_unpack_still_stops_the_restore(self):
        with mock.patch.object(ops.subprocess, "run", self._fake_run(["tar -C /app -xf"])):
            with self.assertRaises(ops.Fail):
                ops.restore_uploads(ops.DRILL, "somewhere")

    def test_nothing_fails_when_everything_works(self):
        with mock.patch.object(ops.subprocess, "run", self._fake_run([])):
            ops.restore_uploads(ops.DRILL, "somewhere")
        self.assertEqual(len(self.calls), 4)


if __name__ == "__main__":
    unittest.main()
