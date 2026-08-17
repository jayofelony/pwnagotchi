import subprocess
import os
import re
import logging
import tempfile
import time


class PairingAgent:
    """Manages the persistent bluetoothctl pairing agent."""

    _ANSI = re.compile(r"(\x1b\[[0-9;]*m|\x08)")

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.process = None
        self.log_fd = None
        self.log_path = None
        self.current_passkey = None

    def start(self):
        """Start the persistent pairing agent."""
        try:
            if self.process and self.process.poll() is None:
                self.logger.info("Pairing agent already running")
                return True

            self.logger.info("Starting persistent pairing agent...")

            agent_commands = """power on
agent KeyboardDisplay
default-agent
"""

            env = dict(os.environ)
            env["NO_COLOR"] = "1"
            env["TERM"] = "dumb"

            self.log_fd, self.log_path = tempfile.mkstemp(prefix="bt-agent-", suffix=".log")
            self.logger.info(f"Agent output will be logged to: {self.log_path}")

            self.process = subprocess.Popen(
                ["bluetoothctl"],
                stdin=subprocess.PIPE,
                stdout=self.log_fd,
                stderr=self.log_fd,
                text=False,
                env=env,
            )

            try:
                self.process.stdin.write(agent_commands.encode())
                self.process.stdin.flush()
            except BrokenPipeError:
                self.logger.warning("Agent process stdin pipe broken - process may have exited")
                return False

            self.logger.info("✓ Persistent pairing agent started (KeyboardDisplay mode)")
            return True

        except Exception as e:
            self.logger.error(f"Failed to start pairing agent: {e}")
            self.cleanup()
            return False

    def stop(self):
        """Stop the pairing agent and cleanup resources."""
        try:
            if self.process and self.process.poll() is None:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=1)
        except Exception as e:
            self.logger.debug(f"Error stopping agent: {e}")

        self.cleanup()

    def cleanup(self):
        """Clean up temporary log file and file descriptors."""
        try:
            if self.log_fd:
                if isinstance(self.log_fd, int):
                    os.close(self.log_fd)
                else:
                    self.log_fd.close()
                self.log_fd = None
        except Exception as e:
            self.logger.debug(f"Failed to close agent log fd: {e}")

        try:
            if self.log_path and os.path.exists(self.log_path):
                os.remove(self.log_path)
                self.log_path = None
        except Exception as e:
            self.logger.debug(f"Failed to remove agent log: {e}")

    def confirm(self):
        """Answer 'yes' to a pending passkey confirmation on the agent's stdin."""
        try:
            if self.process and self.process.poll() is None and self.process.stdin:
                self.process.stdin.write(b"yes\n")
                self.process.stdin.flush()
                return True
        except Exception as e:
            self.logger.debug(f"Agent confirm failed: {e}")
        return False

    def watch_and_confirm(self, stop_event, timeout=90):
        """Tail the agent log during pairing and auto-confirm the passkey.

        With KeyboardDisplay the association uses numeric comparison, so BlueZ asks
        the agent to confirm the passkey. Nobody is at the Pi's console, so we
        answer 'yes' the moment the prompt appears (the user still confirms the
        matching code on the phone). Captures the passkey for the UI too.
        """
        if not self.log_path:
            return
        try:
            with open(self.log_path, "r", errors="ignore") as f:
                f.seek(0, 2)  # tail from the end
                start = time.time()
                while not stop_event.is_set() and time.time() - start < timeout:
                    line = f.readline()
                    if not line:
                        time.sleep(0.1)
                        continue
                    clean = self._ANSI.sub("", line.strip())
                    low = clean.lower()
                    if "passkey" in low or "confirm" in low:
                        m = re.search(r"(\d{6})", clean)
                        if m:
                            self.current_passkey = m.group(1)
                            self.logger.warning(f"🔑 PASSKEY: {self.current_passkey} - confirm on phone!")
                        if self.confirm():
                            self.logger.info("✅ Auto-confirmed passkey on the Pi side")
        except Exception as e:
            self.logger.debug(f"Agent log watch error: {e}")
