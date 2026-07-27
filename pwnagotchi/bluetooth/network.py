import subprocess
import re
import logging
import time
import os
import socket


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
        """Setup network for interface using DHCP."""
        try:
            self.logger.info(f"Setting up network for {iface}...")

            # Ensure interface is up
            self.logger.info(f"Ensuring {iface} is up...")
            subprocess.run(
                ["sudo", "ip", "link", "set", iface, "up"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
            )

            return self._setup_dhclient_internal(iface)

        except subprocess.TimeoutExpired:
            self.logger.error("Network setup timed out")
            return False
        except Exception as e:
            self.logger.error(f"Network setup error: {e}")
            return False

    def _setup_dhclient_internal(self, iface):
        """Request DHCP on interface using available client."""
        try:
            self.logger.info(f"Setting up {iface} for DHCP...")

            # Bring interface up
            subprocess.run(
                ["sudo", "ip", "link", "set", iface, "up"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
            )

            # Check which DHCP client is available
            has_dhcpcd = (
                subprocess.run(["which", "dhcpcd"], capture_output=True).returncode == 0
            )
            has_dhclient = (
                subprocess.run(["which", "dhclient"], capture_output=True).returncode == 0
            )

            self.logger.info(f"Requesting DHCP on {iface}...")
            dhcp_success = False

            if has_dhcpcd:
                self.logger.info("Using dhcpcd...")
                # Release any existing lease first
                subprocess.run(
                    ["sudo", "dhcpcd", "-k", iface],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
                time.sleep(1)
                # Request new lease
                result = subprocess.run(
                    ["sudo", "dhcpcd", "-4", "-n", iface],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=20,
                )
                if result.stdout.strip():
                    self.logger.info(f"dhcpcd: {result.stdout.strip()}")
                if result.returncode == 0:
                    dhcp_success = True
                else:
                    self.logger.warning(f"dhcpcd failed: {result.stderr.strip()}")

            elif has_dhclient:
                self.logger.info("Using dhclient...")
                # Kill any existing dhclient for this interface
                self._kill_dhclient_for_interface(iface)
                time.sleep(0.5)

                # Request new lease
                try:
                    result = subprocess.run(
                        ["sudo", "dhclient", "-4", "-v", iface],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=30,
                    )
                    combined = f"{result.stdout} {result.stderr}".strip()

                    # Check for common errors
                    if "Network error: Software caused connection abort" in combined:
                        self.logger.warning("dhclient: Connection aborted by phone")
                        self.logger.warning("📱 Ensure Bluetooth tethering is ENABLED on your phone!")
                    elif "DHCPDISCOVER" in combined and "No DHCPOFFERS" in combined:
                        self.logger.warning("dhclient: No DHCP response from phone")
                        self.logger.warning("📱 Phone is not providing DHCP - enable Bluetooth tethering!")

                    if result.returncode == 0:
                        dhcp_success = True
                    else:
                        self.logger.warning(f"dhclient returned {result.returncode}")

                except subprocess.TimeoutExpired:
                    self.logger.warning("dhclient timed out after 30s")
                    try:
                        self._kill_dhclient_for_interface(iface)
                    except Exception:
                        pass
            else:
                self.logger.error("No DHCP client available (dhcpcd or dhclient)")

            return dhcp_success

        except Exception as e:
            self.logger.error(f"DHCP setup error: {e}")
            return False

    def _kill_dhclient_for_interface(self, iface):
        """Kill dhclient processes specifically managing the given interface."""
        try:
            result = subprocess.run(
                ["pidof", "dhclient"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=3,
            )

            if result.returncode != 0 or not result.stdout.strip():
                return

            pids = result.stdout.strip().split()
            for pid in pids:
                try:
                    ps_result = subprocess.run(
                        ["ps", "-p", pid, "-o", "args="],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=2,
                    )

                    if ps_result.returncode == 0:
                        cmdline = ps_result.stdout.strip()
                        args = cmdline.split()

                        # The interface must be the LAST argument and match EXACTLY
                        if args and args[-1] == iface:
                            self.logger.debug(f"Killing dhclient PID {pid} for {iface}")
                            subprocess.run(
                                ["sudo", "kill", pid],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                timeout=3,
                            )
                except Exception as e:
                    self.logger.debug(f"Error checking PID {pid}: {e}")

        except Exception as e:
            self.logger.debug(f"Error killing dhclient: {e}")

    def stop_dhclient(self, iface):
        """Stop dhclient for interface."""
        try:
            self._kill_dhclient_for_interface(iface)
            subprocess.run(
                ["sudo", "dhclient", "-r", iface],
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

    def check_internet_connectivity(self):
        """Check if internet is accessible via Bluetooth interface specifically"""
        try:
            bt_iface = self.get_interface_name() or "bnep0"

            # First verify interface has an IP
            ip_result = subprocess.run(
                ["ip", "addr", "show", bt_iface],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )

            if ip_result.returncode != 0:
                self.logger.warning(f"{bt_iface} interface not found")
                return False

            ip_match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", ip_result.stdout)
            if not ip_match or ip_match.group(1).startswith("169.254."):
                self.logger.warning(f"{bt_iface} has no valid IP")
                return False

            bt_ip = ip_match.group(1)
            self.logger.info(f"{bt_iface} has IP: {bt_ip}")

            # Log current routing table
            route_check = subprocess.run(
                ["ip", "route", "show"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            if route_check.returncode == 0:
                self.logger.info(f"Current routes:\n{route_check.stdout}")

            # Ping via the Bluetooth interface specifically
            self.logger.info(f"Testing connectivity to 8.8.8.8 via {bt_iface}...")
            result = subprocess.run(
                ["ping", "-c", "2", "-W", "3", "-I", bt_iface, "8.8.8.8"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                self.logger.info("✓ Ping to 8.8.8.8 successful")
                return True
            else:
                self.logger.warning("Ping to 8.8.8.8 failed")
                self.logger.warning(f"Ping stderr: {result.stderr}")
                self.logger.warning(f"Ping stdout: {result.stdout}")

                # Try to ping the gateway
                gateway_check = subprocess.run(
                    ["ip", "route", "show", "default"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=5,
                )
                if gateway_check.returncode == 0 and gateway_check.stdout:
                    match = re.search(r"default via ([\d.]+)", gateway_check.stdout)
                    if match:
                        gateway = match.group(1)
                        self.logger.info(f"Testing connectivity to gateway {gateway}...")
                        gw_result = subprocess.run(
                            ["ping", "-c", "2", "-W", "3", gateway],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            timeout=10,
                        )
                        if gw_result.returncode == 0:
                            self.logger.warning(
                                "Gateway ping works, but internet ping failed - possible NAT/firewall issue"
                            )
                        else:
                            self.logger.warning(
                                "Gateway ping also failed - phone may not be providing internet"
                            )

                return False
        except subprocess.TimeoutExpired:
            self.logger.warning("Ping timeout - no internet connectivity")
            return False
        except Exception as e:
            self.logger.error(f"Internet check error: {e}")
            return False

    def is_pan_active(self):
        """Check if any PAN interface (bnep/bt-pan) is active"""
        try:
            result = subprocess.run(
                ["ip", "link", "show"],
                capture_output=True,
                text=True,
                timeout=3,
            )

            has_bnep = "bnep" in result.stdout
            has_bt_pan = "bt-pan" in result.stdout

            if has_bnep or has_bt_pan:
                self.logger.debug(f"Found PAN interface (bnep={has_bnep}, bt-pan={has_bt_pan})")
                return True

            self.logger.debug("No PAN interface found")
            return False
        except Exception as e:
            self.logger.error(f"Failed to check PAN: {e}")
            return False

    def get_pan_interface(self):
        """Get the name of the Bluetooth PAN interface if it exists"""
        try:
            out = subprocess.check_output(["ip", "link"], text=True, timeout=5)
            for line in out.split("\n"):
                if "bnep" in line or "bt-pan" in line:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        iface = parts[1].strip()
                        return iface
            return None
        except Exception as e:
            self.logger.error(f"Failed to get PAN interface: {e}")
            return None

    def get_interface_ip(self, iface):
        """Get IP address of a network interface"""
        try:
            result = subprocess.check_output(
                ["ip", "-4", "addr", "show", iface], text=True, timeout=5
            )
            match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", result)
            if match:
                return match.group(1)
            return None
        except Exception as e:
            self.logger.debug(f"Failed to get IP for {iface}: {e}")
            return None

    def get_current_ip(self):
        """Get the current IP address from the Bluetooth PAN interface only"""
        try:
            pan_iface = self.get_pan_interface()
            if pan_iface:
                ip = self.get_interface_ip(pan_iface)
                if ip and not ip.startswith("169.254."):
                    self.logger.debug(f"Found BT IP {ip} on {pan_iface}")
                    return ip

            # Also check bnep0 explicitly
            ip = self.get_interface_ip("bnep0")
            if ip and not ip.startswith("169.254."):
                self.logger.debug(f"Found BT IP {ip} on bnep0")
                return ip

            self.logger.debug("No IP address found on Bluetooth interface")
            return None
        except Exception as e:
            self.logger.debug(f"Error getting current IP: {e}")
            return None

    def full_internet_test(self):
        """Test internet connectivity and return detailed results - comprehensive version"""
        result = {
            "ping_success": False,
            "dns_success": False,
            "bnep0_ip": None,
            "default_route": None,
            "dns_servers": None,
            "dns_error": None,
            "localhost_routes": None,
        }

        # Test ping
        try:
            ping_result = subprocess.run(
                ["ping", "-c", "2", "-W", "3", "8.8.8.8"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
            )
            result["ping_success"] = ping_result.returncode == 0
            self.logger.info(f"Ping test: {'Success' if result['ping_success'] else 'Failed'}")
        except Exception as e:
            self.logger.warning(f"Ping test error: {e}")

        # Test DNS
        try:
            socket.gethostbyname("google.com")
            result["dns_success"] = True
            self.logger.info("DNS test: Success")
        except socket.gaierror as e:
            result["dns_success"] = False
            result["dns_error"] = f"DNS resolution failed: {str(e)}"
            self.logger.warning(f"DNS test failed: {e}")
        except Exception as e:
            result["dns_success"] = False
            result["dns_error"] = str(e)
            self.logger.warning(f"DNS test error: {e}")

        # Get DNS servers
        try:
            with open("/etc/resolv.conf", "r") as f:
                resolv_content = f.read()
                dns_servers = []
                for line in resolv_content.split("\n"):
                    if line.strip().startswith("nameserver"):
                        dns_servers.append(line.strip().split()[1])
                result["dns_servers"] = ", ".join(dns_servers) if dns_servers else "None"
            self.logger.info(f"DNS servers: {result['dns_servers']}")
        except Exception as e:
            result["dns_servers"] = f"Error: {str(e)[:50]}"
            self.logger.warning(f"Get DNS servers error: {e}")

        # Get bnep0 IP
        try:
            ip_result = subprocess.run(
                ["ip", "addr", "show", "bnep0"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            if ip_result.returncode == 0:
                ip_match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", ip_result.stdout)
                if ip_match:
                    result["bnep0_ip"] = ip_match.group(1)
            self.logger.info(f"bnep0 IP: {result['bnep0_ip']}")
        except Exception as e:
            self.logger.warning(f"Get bnep0 IP error: {e}")

        # Get default route
        try:
            route_result = subprocess.run(
                ["ip", "route", "show", "default"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            if route_result.returncode == 0 and route_result.stdout:
                result["default_route"] = route_result.stdout.strip()
            self.logger.info(f"Default route: {result['default_route']}")
        except Exception as e:
            self.logger.warning(f"Get default route error: {e}")

        # Get localhost route
        try:
            localhost_result = subprocess.run(
                ["ip", "route", "get", "127.0.0.1"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            if localhost_result.returncode == 0 and localhost_result.stdout:
                result["localhost_routes"] = localhost_result.stdout.strip()
                if "lo" not in result["localhost_routes"] and "local" not in result["localhost_routes"]:
                    self.logger.warning("⚠️  WARNING: Localhost not routing through 'lo' interface!")
                    self.logger.warning(f"⚠️  This may prevent bettercap API from working: {result['localhost_routes']}")
                else:
                    self.logger.info(f"Localhost route: {result['localhost_routes']}")
            else:
                result["localhost_routes"] = "Error getting localhost route"
        except Exception as e:
            result["localhost_routes"] = f"Error: {str(e)}"
            self.logger.warning(f"Get localhost route error: {e}")

        return result
