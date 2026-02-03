from threading import Lock


class State(object):
    def __init__(self, state={}):
        # Holds all UI/state elements (key -> element)
        self._state = state

        # Lock to make state access thread-safe
        self._lock = Lock()

        # Callbacks to notify when a specific key changes
        self._listeners = {}

        # Tracks which keys have changed since last reset
        self._changes = {}

    def add_element(self, key, elem):
        # Add a new element to the state
        self._state[key] = elem

        # Mark this key as changed
        self._changes[key] = True

    def has_element(self, key):
        # Check if an element exists in the state
        return key in self._state

    def remove_element(self, key):
        # Remove an element from the state
        del self._state[key]

        # Mark this key as changed
        self._changes[key] = True

    def add_listener(self, key, cb):
        # Register a callback for when a specific key changes
        with self._lock:
            self._listeners[key] = cb

    def items(self):
        # Return all state items (thread-safe)
        with self._lock:
            return self._state.items()

    def get(self, key):
        # Get the value of a state element if it exists
        with self._lock:
            return self._state[key].value if key in self._state else None

    def reset(self):
        # Clear the change-tracking dictionary
        with self._lock:
            self._changes = {}

    def changes(self, ignore=()):
        # Return a list of changed keys, excluding ignored ones
        with self._lock:
            changes = []
            for change in self._changes.keys():
                if change not in ignore:
                    changes.append(change)
            return changes

    def has_changes(self):
        # Check if any state changes are pending
        with self._lock:
            return len(self._changes) > 0

    def set(self, key, value):
        # Update the value of an existing state element
        with self._lock:
            if key in self._state:
                prev = self._state[key].value
                self._state[key].value = value

                # Only trigger change logic if value actually changed
                if prev != value:
                    self._changes[key] = True

                    # Call listener callback if one is registered
                    if key in self._listeners and self._listeners[key] is not None:
                        self._listeners[key](prev, value)
