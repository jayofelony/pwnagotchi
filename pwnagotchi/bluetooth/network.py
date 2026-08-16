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

    # DHCP tuning
    DHCP_RELEASE_WAIT = 1
    DHCP_KILL_WAIT = 0.5
    DHCPCD_FAST_CONF = "/tmp/bt-tether-dhcpcd.conf"
    DHCLIENT_FAST_CONF = "/tmp/bt-tether-dhclient.conf"

    def __init__(self, logger=None, options=None):
        self.logger = logger or logging.getLogger(__name__)
        self.options = options or {}
        self.fast_dhcp = self.options.get("fast_dhcp", True)

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
                    # Anchor and exclude ':'/'@' so we don't capture the trailing
                    # colon ("bnep0:") or altname form ("bnep0@if3") - a bad name
                    # here goes straight to `ping -I` and fails the internet check.
                    match = re.search(r"^\d+:\s+([^:@\s]+)", line)
                    if match:
                        return match.group(1)
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
        """Ensure 127.0.0.1 routes via 'lo', repairing it if a PAN/DHCP route shadowed it.

        Critical for bettercap: a phone's Bluetooth PAN can push a route that
        shadows loopback, which silently breaks bettercap's localhost API after
        tethering comes up. We check the actual loopback route and fix it in place.
        """
        try:
            result = subprocess.run(
                ["ip", "route", "get", "127.0.0.1"],
                capture_output=True,
                text=True,
                timeout=self.SUBPROCESS_TIMEOUT_MEDIUM,
            )
            out = result.stdout or ""
            if "lo" in out or "local" in out:
                return True

            self.logger.warning("Localhost not routing via 'lo' - repairing loopback route")
            subprocess.run(
                ["sudo", "ip", "link", "set", "lo", "up"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=self.SUBPROCESS_TIMEOUT_STANDARD,
            )
            # May already exist - ignore a "File exists" error
            subprocess.run(
                ["sudo", "ip", "route", "add", "127.0.0.0/8", "dev", "lo"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=self.SUBPROCESS_TIMEOUT_STANDARD,
            )
            return True
        except Exception as e:
            self.logger.debug(f"Failed to verify/repair localhost route: {e}")
            return False

    def wait_for_pan_interface(self, timeout=6):
        """Poll for the PAN interface (bnepX/bt-pan) to appear after a NAP connect.

        The kernel creates the interface a moment after NAP connects, so a single
        immediate check can miss it. Returns the interface name or None.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            iface = self.get_pan_interface()
            if iface:
                return iface
            time.sleep(0.5)
        return None

    def wait_for_interface_ip(self, iface, timeout=8):
        """Poll for a usable address (IPv4, or global IPv6) on the interface.

        Returns the address once the DHCP lease lands (or SLAAC assigns IPv6),
        else None on timeout.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            ip = self.get_interface_ip(iface)
            if ip and not ip.startswith("169.254."):
                return ip
            v6 = self.get_global_ipv6(iface)
            if v6:
                return v6
            time.sleep(0.5)
        return None

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
                time.sleep(self.DHCP_RELEASE_WAIT)
                # dhcpcd ARP-probes the address for ~5-6s (duplicate-address
                # detection). That's pointless on a point-to-point Bluetooth PAN
                # link, so disable it via a minimal config - it's the single
                # biggest chunk of connect time. Skipped when fast_dhcp is off.
                cf_args = []
                if self.fast_dhcp:
                    try:
                        with open(self.DHCPCD_FAST_CONF, "w") as cf:
                            cf.write("noarp\n")
                        cf_args = ["-f", self.DHCPCD_FAST_CONF]
                    except Exception as e:
                        self.logger.debug(f"dhcpcd cf write failed: {e}")
                # Request new lease
                result = subprocess.run(
                    ["sudo", "dhcpcd", "-4"] + cf_args + ["-n", iface],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=20,
                )
                # If our noarp config made dhcpcd unhappy (unusual version), retry
                # once with a plain invocation so we still get a lease anywhere.
                if result.returncode != 0 and cf_args:
                    self.logger.info("dhcpcd config rejected - retrying without noarp tuning")
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
                time.sleep(self.DHCP_KILL_WAIT)

                # dhclient's default initial DISCOVER backoff is a random delay of
                # up to ~10s, which dominates lease time on a fast PAN link. A tiny
                # config makes it retry quickly so the lease lands in ~1-2s.
                # Skipped when fast_dhcp is off.
                cf_args = []
                if self.fast_dhcp:
                    try:
                        with open(self.DHCLIENT_FAST_CONF, "w") as cf:
                            cf.write("initial-interval 1;\nbackoff-cutoff 3;\ntimeout 25;\n")
                        cf_args = ["-cf", self.DHCLIENT_FAST_CONF]
                    except Exception as e:
                        self.logger.debug(f"dhclient cf write failed: {e}")

                # Request new lease
                try:
                    result = subprocess.run(
                        ["sudo", "dhclient", "-4", "-v"] + cf_args + [iface],
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
            "ipv6": None,
            "default_route": None,
            "localhost_routes": None,
        }

        iface = self.get_interface_name()
        if iface:
            result["bnep0_ip"] = self.get_ip(iface)
            result["ipv6"] = self.get_global_ipv6(iface)

        result["default_route"] = self.get_default_route_interface()

        # IPv4 ping, then fall back to IPv6 (dual-stack tethering may be v6-only)
        try:
            ping_result = subprocess.run(
                ["ping", "-c", "1", "8.8.8.8"],
                capture_output=True,
                timeout=self.SUBPROCESS_TIMEOUT_STANDARD,
            )
            result["ping_success"] = ping_result.returncode == 0
            if not result["ping_success"]:
                v6_ping = subprocess.run(
                    ["ping", "-6", "-c", "1", "2001:4860:4860::8888"],
                    capture_output=True,
                    timeout=self.SUBPROCESS_TIMEOUT_STANDARD,
                )
                if v6_ping.returncode == 0:
                    result["ping_success"] = True
        except Exception:
            result["ping_success"] = False

        # Resolve via Python's resolver - no external binary (nslookup/dig aren't
        # installed on the image).
        try:
            socket.gethostbyname("google.com")
            result["dns_success"] = True
        except Exception as e:
            result["dns_success"] = False
            result["dns_error"] = str(e)

        try:
            with open("/etc/resolv.conf", "r") as f:
                servers = [line.split()[1] for line in f if line.startswith("nameserver")]
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
        """Check internet via the Bluetooth interface (IPv4 or IPv6).

        Dual-stack: some Android tethering setups provide IPv6-only connectivity
        on the PAN side (no IPv4), so a v4-only check would falsely report "no
        internet". Tries IPv4 first when present, then falls back to IPv6.
        """
        try:
            bt_iface = self.get_interface_name() or "bnep0"

            # Verify the interface has any usable address (IPv4 or global IPv6)
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

            ipv4_match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", ip_result.stdout)
            has_ipv4 = bool(ipv4_match) and not ipv4_match.group(1).startswith("169.254.")
            ipv6 = self.get_global_ipv6(bt_iface)

            if not has_ipv4 and not ipv6:
                self.logger.warning(f"{bt_iface} has no valid IP (IPv4 or IPv6)")
                return False
            if has_ipv4:
                self.logger.info(f"{bt_iface} has IPv4: {ipv4_match.group(1)}")
            if ipv6:
                self.logger.info(f"{bt_iface} has IPv6: {ipv6}")

            # Log current routing table for diagnostics
            route_check = subprocess.run(
                ["ip", "route", "show"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            if route_check.returncode == 0:
                self.logger.info(f"Current routes:\n{route_check.stdout}")

            # Try IPv4 connectivity first (when an IPv4 address is present)
            if has_ipv4:
                self.logger.info(f"Testing IPv4 connectivity to 8.8.8.8 via {bt_iface}...")
                result = subprocess.run(
                    ["ping", "-c", "2", "-W", "3", "-I", bt_iface, "8.8.8.8"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    self.logger.info("✓ IPv4 ping to 8.8.8.8 successful")
                    return True

                self.logger.warning("IPv4 ping to 8.8.8.8 failed")
                self.logger.debug(f"Ping stderr: {result.stderr}")

                # Gateway diagnostic to distinguish link vs internet issues
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

            # Fall back to IPv6 if IPv4 was absent or its ping failed
            if ipv6:
                self.logger.info(f"Testing IPv6 connectivity via {bt_iface}...")
                # Literal target (Google public DNS v6) - avoids depending on
                # working IPv6 DNS, mirroring the IPv4 use of a literal.
                v6_result = subprocess.run(
                    ["ping", "-6", "-c", "2", "-W", "3", "-I", bt_iface, "2001:4860:4860::8888"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=10,
                )
                if v6_result.returncode == 0:
                    self.logger.info("✓ IPv6 connectivity verified")
                    return True
                self.logger.warning("IPv6 ping failed")
                self.logger.debug(f"IPv6 ping stderr: {v6_result.stderr}")

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

    def get_global_ipv6(self, iface=None):
        """Get a global (non-link-local) IPv6 address from the PAN interface.

        Some Android Bluetooth tethering setups provide IPv6-only connectivity
        (no IPv4 on the PAN side, address via SLAAC). `scope global` excludes
        fe80:: link-local automatically. Returns the address or None.
        """
        try:
            if iface is None:
                iface = self.get_pan_interface() or "bnep0"
            result = subprocess.check_output(
                ["ip", "-6", "addr", "show", iface, "scope", "global"],
                text=True,
                timeout=self.SUBPROCESS_TIMEOUT_STANDARD,
            )
            for line in result.splitlines():
                line = line.strip()
                if line.startswith("inet6"):
                    addr = line.split()[1].split("/")[0]
                    # Belt-and-suspenders: skip link-local even if the scope
                    # filter was bypassed by an unusual iproute2 build.
                    if not addr.lower().startswith("fe80"):
                        return addr
            return None
        except Exception as e:
            self.logger.debug(f"Failed to get IPv6 for {iface}: {e}")
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
