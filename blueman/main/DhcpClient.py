from gi.repository import GObject
from gi.repository import GLib
import socket
import subprocess
import logging
from blueman.Functions import have, get_local_interfaces
from blueman.bluemantyping import GSignals


class DhcpClientError(Exception):
    pass


class DhcpClient(GObject.GObject):
    __gsignals__: GSignals = {
        # arg: interface name eg. ppp0
        'connected': (GObject.SignalFlags.NO_HOOKS, None, (str,)),
        'error-occurred': (GObject.SignalFlags.NO_HOOKS, None, (int,)),
    }

    COMMANDS = [
        ["dhclient", "-e", "IF_METRIC=100", "-1"],
        ["dhcpcd", "-m", "100"],
        ["udhcpc", "-t", "20", "-x", "hostname", socket.gethostname(), "-n", "-i"]
    ]

    querying: list[str] = []
    _client: subprocess.Popen[bytes]
    _timeout_source_id: int | None

    def __init__(self, interface: str, timeout: int = 30) -> None:
        """The interface name has to be trusted / sanitized!"""
        super().__init__()

        self._interface = interface
        self._timeout = timeout
        self._timeout_source_id = None

        self._command = None
        for command in self.COMMANDS:
            path = have(command[0])
            if path:
                self._command = [path] + command[1:] + [self._interface]
                break

    def run(self) -> None:
        if not self._command:
            raise DhcpClientError("No DHCP client found, please install dhclient, dhcpcd, or udhcpc")

        if self._interface in DhcpClient.querying:
            raise DhcpClientError("DHCP already running on this interface")
        else:
            DhcpClient.querying.append(self._interface)

        try:
            self._client = subprocess.Popen(self._command)
        except OSError:
            DhcpClient.querying.remove(self._interface)
            raise

        GLib.timeout_add(1000, self._check_client)
        self._timeout_source_id = GLib.timeout_add(self._timeout * 1000, self._on_timeout)

    def _clear_timeout(self) -> None:
        if self._timeout_source_id is not None:
            GLib.source_remove(self._timeout_source_id)
            self._timeout_source_id = None

    def _on_timeout(self) -> bool:
        self._timeout_source_id = None
        if self._client.poll() is None:
            logging.warning("Timeout reached, terminating DHCP client")
            self._client.terminate()
        return False

    def _check_client(self) -> bool:
        netifs = get_local_interfaces()
        status = self._client.poll()
        if status == 0:
            def complete() -> bool:
                ip = netifs[self._interface][0]
                logging.info("bound to %s", ip)
                self.emit("connected", ip)
                return False

            self._clear_timeout()
            GLib.timeout_add(1000, complete)
            DhcpClient.querying.remove(self._interface)
            return False
        elif status:
            self._clear_timeout()
            logging.error("dhcp client failed with status code %s", status)
            self.emit("error-occurred", status)
            DhcpClient.querying.remove(self._interface)
            return False
        else:
            return True
