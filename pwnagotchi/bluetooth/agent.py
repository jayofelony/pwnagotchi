import subprocess
import os
import logging
import tempfile
import time


class PairingAgent:
    """Manages the persistent bluetoothctl pairing agent."""

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

    def get_latest_passkey(self):
        """Extract the latest passkey from agent log."""
        if not self.log_path or not os.path.exists(self.log_path):
            return None

        try:
            with open(self.log_path, "r", errors="ignore") as f:
                content = f.read()
                lines = content.split("\n")
                for line in reversed(lines):
                    if "Passkey" in line or "passkey" in line:
                        return line
        except Exception as e:
            self.logger.debug(f"Failed to read passkey: {e}")

        return None
