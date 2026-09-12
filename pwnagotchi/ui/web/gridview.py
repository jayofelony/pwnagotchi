"""GridView — one seam over the ``pwnagotchi.grid`` module for the web inbox pages.

The inbox/profile/peers/message/send handlers all repeated the same dance: maybe
check ``grid.is_connected()``, call a grid function, and on any exception stringify
it into an ``error`` for the template. That connection policy + error handling now
lives here once, so the handlers shrink to "get data-or-error, render".

Each method returns a ``(data, error)`` tuple: ``error`` is ``None`` on success,
else a message string (with ``data`` left at its safe default). ``grid`` is
injected (defaulting to the real module) so the mapping is testable with a fake -
no live pwngrid needed.
"""
import base64
import logging


class GridView:
    def __init__(self, grid=None):
        if grid is None:
            from pwnagotchi import grid as _grid
            grid = _grid
        self._grid = grid

    def _fetch(self, fn, default, log_msg, require_connected):
        """Run a grid call, returning (data, error). Honours the per-call
        connection policy and turns any exception into an error string."""
        if require_connected and not self._grid.is_connected():
            return default, "not connected"
        try:
            return fn(), None
        except Exception as e:
            logging.exception(log_msg)
            return default, str(e)

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
