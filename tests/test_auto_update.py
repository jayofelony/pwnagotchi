"""Exercise the standalone updater without network, installation or reboot."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "stage3/06-patches/files/auto-update.sh"


class AutoUpdateTest(unittest.TestCase):
    def run_updater(self, failure="", current=False, existing=True):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            files = repo / "stage3/06-patches/files"
            files.mkdir(parents=True)
            (files / "pwnlib").write_text("updated system file\n")
            if existing:
                (repo / ".git").mkdir()
            (root / "bin").mkdir()
            (root / "etc/systemd/system").mkdir(parents=True)
            (root / "etc/update-motd.d").mkdir()
            (root / "activate").write_text("deactivate() { :; }\n")
            commands = {
                "wget": 'if [ "$1" = -qO- ]; then echo \'{"tag_name":"v9.1"}\'; fi',
                "pwnagotchi": 'echo "$INSTALLED"',
                "git": '[ "$FAILURE" != "git-$1" ] || exit 42',
                "pip3": '[ "$FAILURE" != pip ] || exit 43',
                "cp": '[ "$FAILURE" != copy ] || exit 44; exec /bin/cp "$@"',
                "systemctl": '[ "$FAILURE" != systemctl ] || exit 45',
                "sync": ":",
                "reboot": 'touch "$MARKER"',
            }
            for name, body in commands.items():
                path = root / "bin" / name
                path.write_text("#!/bin/bash\n" + body + "\n")
                path.chmod(0o755)
            source = SCRIPT.read_text().replace("/opt/pwnagotchi", str(repo))
            source = source.replace("/opt/.pwn/bin/activate", str(root / "activate"))
            source = source.replace("/usr/bin/", str(root / "bin") + "/")
            source = source.replace("/etc/", str(root / "etc") + "/")
            script = root / "updater.sh"
            script.write_text(source)
            marker = root / "rebooted"
            env = dict(os.environ, PATH=f"{root / 'bin'}:/usr/bin:/bin",
                       FAILURE=failure, INSTALLED="9.1" if current else "9.0",
                       MARKER=str(marker))
            result = subprocess.run(["bash", str(script)], env=env,
                                    capture_output=True, text=True)
            return result, marker.exists(), repo.exists()

    def test_failures_do_not_reboot_or_remove_checkout(self):
        for failure in ("git-fetch", "git-reset", "git-clone", "pip", "copy", "systemctl"):
            with self.subTest(failure=failure):
                result, rebooted, checkout_exists = self.run_updater(
                    failure, existing=failure != "git-clone")
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("not rebooting", result.stderr)
                self.assertFalse(rebooted)
                self.assertTrue(checkout_exists)

    def test_current_version_does_not_reboot(self):
        result, rebooted, checkout_exists = self.run_updater(current=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("already up to date", result.stdout)
        self.assertFalse(rebooted)
        self.assertTrue(checkout_exists)

    def test_successful_update_reboots(self):
        result, rebooted, checkout_exists = self.run_updater()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(rebooted)
        self.assertFalse(checkout_exists)


if __name__ == "__main__":
    unittest.main()
