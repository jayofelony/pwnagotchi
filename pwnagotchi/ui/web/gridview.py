"""One seam over pwngrid for the web inbox pages. Each method returns (data, error);
grid is injected (defaulting to the real module) so the mapping is testable.
"""
import base64
import logging


def _friendly_grid_error(e):
    """Map a raw grid/requests exception to a short, user-facing message."""
    name = type(e).__name__
    text = str(e)
    if "ConnectionError" in name or "Connection refused" in text or "Max retries" in text:
        return "pwngrid isn't reachable — is the pwngrid-peer service running?"
    if "Timeout" in name or "timed out" in text:
        return "pwngrid took too long to respond — try again."
    if "not connected" in text.lower():
        return "pwngrid isn't connected to the mesh yet."
    return "couldn't reach pwngrid."


class GridView:
    def __init__(self, grid=None):
        if grid is None:
            from pwnagotchi import grid as _grid
            grid = _grid
        self._grid = grid

    def _fetch(self, fn, default, log_msg, require_connected):
        """Run a grid call, returning (data, error) per the connection policy."""
        if require_connected and not self._grid.is_connected():
            return default, "pwngrid isn't connected yet — waiting for the mesh."
        try:
            return fn(), None
        except Exception as e:
            logging.exception(log_msg)
            return default, _friendly_grid_error(e)

    def inbox(self, page):
        return self._fetch(
            lambda: self._grid.inbox(page, with_pager=True),
            {"pages": 1, "records": 0, "messages": []},
            "error while reading pwnmail inbox",
            require_connected=True,
        )

    def profile(self):
        # get_advertisement_data reads local pwngrid data - no connection needed.
        return self._fetch(
            self._grid.get_advertisement_data, {},
            "error while reading pwngrid data",
            require_connected=False,
        )

    def peers(self):
        # memory() reads the local peers file - no connection needed.
        return self._fetch(
            self._grid.memory, {},
            "error while reading pwngrid peers",
            require_connected=False,
        )

    def message(self, id):
        def _get():
            message = self._grid.inbox_message(id)
            if message.get("data"):
                message["data"] = base64.b64decode(message["data"]).decode("utf-8")
            return message
        return self._fetch(
            _get, {},
            "error while reading pwnmail message %s" % id,
            require_connected=True,
        )

    def send(self, to, message):
        # Only the error matters to the caller (JSON {"error": ...}); the send
        # result is discarded so the contract is always (None, error).
        _, error = self._fetch(
            lambda: self._grid.send_message(to, message), None,
            "error while sending pwnmail",
            require_connected=True,
        )
        return None, error
