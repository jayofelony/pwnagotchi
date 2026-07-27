import subprocess
import re
import logging
import time


class NetworkManager:
    """Manages PAN network interfaces and connectivity checks."""

    SUBPROCESS_TIMEOUT_SHORT = 1
    SUBPROCESS_TIMEOUT_MEDIUM = 2
    SUBPROCESS_TIMEOUT_NORMAL = 3
    SUBPROCESS_TIMEOUT_STANDARD = 5

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)

    def get_interface_name(self):
        """Get the PAN interface name (bnep0, bt-pan, etc.)."""
        try:
            result = subprocess.run(
                ["ip", "link", "show"],
                capture_output=True,
                text=True,
                timeout=self.SUBPROCESS_TIMEOUT_MEDIUM,
            )
            for line in result.stdout.split("\n"):
                if "bnep" in line or "bt-pan" in line:
                    match = re.search(r"(\d+):\s+(\S+)", line)
                    if match:
                        return match.group(2)
        except Exception as e:
            self.logger.debug(f"Failed to get interface name: {e}")
        return None

    def get_ip(self, iface):
        """Get IP address for interface."""
        if not iface:
            return None
        try:
            result = subprocess.run(
                ["ip", "addr", "show", iface],
                capture_output=True,
                text=True,
                timeout=self.SUBPROCESS_TIMEOUT_MEDIUM,
            )
            for line in result.stdout.split("\n"):
                match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", line)
                if match:
                    return match.group(1)
        except Exception as e:
            self.logger.debug(f"Failed to get IP for {iface}: {e}")
        return None

    def get_default_route_interface(self):
        """Get interface that has the default route."""
        try:
            result = subprocess.run(
                ["ip", "route", "show"],
                capture_output=True,
                text=True,
                timeout=self.SUBPROCESS_TIMEOUT_MEDIUM,
            )
            for line in result.stdout.split("\n"):
                if line.startswith("default via"):
                    match = re.search(r"dev\s+(\S+)", line)
                    if match:
                        return match.group(1)
        except Exception as e:
            self.logger.debug(f"Failed to get default route: {e}")
        return None

    def is_internet_available(self):
        """Check if internet is available via ping."""
        try:
            subprocess.run(
                ["ping", "-c", "1", "8.8.8.8"],
                capture_output=True,
                timeout=self.SUBPROCESS_TIMEOUT_SHORT,
            )
            return True
        except Exception:
            return False

    def is_pan_active(self):
        """Check if PAN interface has IP and is up."""
        iface = self.get_interface_name()
        if not iface:
            return False
        ip = self.get_ip(iface)
        return ip is not None

    def verify_localhost(self):
        """Verify localhost routing (critical for bettercap API)."""
        try:
            result = subprocess.run(
                ["ip", "route", "show", "0/0"],
                capture_output=True,
                text=True,
                timeout=self.SUBPROCESS_TIMEOUT_MEDIUM,
            )
            return "lo" in result.stdout or "local" in result.stdout
        except Exception as e:
            self.logger.debug(f"Failed to verify localhost: {e}")
            return False

    def setup_dhcp(self, iface):
        """Setup DHCP on interface."""
        try:
            self.logger.info(f"Setting up DHCP for {iface}")
            subprocess.run(
                ["dhclient", iface],
                timeout=self.SUBPROCESS_TIMEOUT_STANDARD,
                capture_output=True,
            )
            time.sleep(1)
            return True
        except Exception as e:
            self.logger.warning(f"DHCP setup failed: {e}")
            return False

    def stop_dhclient(self, iface):
        """Stop dhclient for interface."""
        try:
            subprocess.run(
                ["dhclient", "-r", iface],
                timeout=self.SUBPROCESS_TIMEOUT_MEDIUM,
                capture_output=True,
            )
            time.sleep(0.5)
        except Exception as e:
            self.logger.debug(f"Failed to stop dhclient: {e}")

    def test_internet_connectivity(self):
        """Test internet connectivity and return detailed results."""
        result = {
            "ping_success": False,
            "dns_success": False,
            "dns_servers": None,
            "dns_error": None,
            "bnep0_ip": None,
            "default_route": None,
            "localhost_routes": None,
        }

        iface = self.get_interface_name()
        if iface:
            result["bnep0_ip"] = self.get_ip(iface)

        result["default_route"] = self.get_default_route_interface()

        try:
            subprocess.run(
                ["ping", "-c", "1", "8.8.8.8"],
                capture_output=True,
                timeout=self.SUBPROCESS_TIMEOUT_SHORT,
            )
            result["ping_success"] = True
        except Exception:
            result["ping_success"] = False

        try:
            subprocess.run(
                ["nslookup", "google.com"],
                capture_output=True,
                timeout=self.SUBPROCESS_TIMEOUT_SHORT,
            )
            result["dns_success"] = True
        except Exception as e:
            result["dns_success"] = False
            result["dns_error"] = str(e)

        try:
            dns_result = subprocess.run(
                ["cat", "/etc/resolv.conf"],
                capture_output=True,
                text=True,
                timeout=self.SUBPROCESS_TIMEOUT_SHORT,
            )
            servers = [line.split()[1] for line in dns_result.stdout.split("\n") if line.startswith("nameserver")]
            result["dns_servers"] = ", ".join(servers) if servers else None
        except Exception:
            pass

        try:
            route_result = subprocess.run(
                ["ip", "route", "show", "0/0"],
                capture_output=True,
                text=True,
                timeout=self.SUBPROCESS_TIMEOUT_MEDIUM,
            )
            result["localhost_routes"] = ", ".join(route_result.stdout.split()) if route_result.stdout else None
        except Exception:
            pass

        return result
