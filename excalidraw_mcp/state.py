"""One process-local scene with validated, serialized commits and detached reads."""

import random
import time
import json
from copy import deepcopy
from threading import RLock
from typing import Callable, TypeVar

from excalidraw_mcp.config import history_limit, max_history_bytes
from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.document import normalize_document
from excalidraw_mcp.models import SceneDocument, new_document, validate_document

T = TypeVar("T")


class SceneState:
    def __init__(self, max_history=None, max_history_size=None):
        self._lock = RLock()
        self._document = new_document()
        self._index = {}
        self._revision = 0
        self._editing = False
        self._max_history = history_limit() if max_history is None else max_history
        if not 1 <= self._max_history <= 100:
            raise ValueError("max_history must be between 1 and 100")
        self._max_history_bytes = (
            max_history_bytes() if max_history_size is None else max_history_size
        )
        if not 1_024 <= self._max_history_bytes <= 500 * 1024 * 1024:
            raise ValueError("max_history_size must be between 1024 and 524288000")
        self._history = []
        self._history_sizes = []
        self._history_bytes = 0
        self._listeners = []

    def subscribe(self, callback: Callable[[SceneDocument, int], None]) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(callback)

        def unsubscribe():
            with self._lock:
                if callback in self._listeners:
                    self._listeners.remove(callback)

        return unsubscribe

    def _notify(self):
        with self._lock:
            doc = deepcopy(self._document)
            rev = self._revision
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(doc, rev)
            except Exception:
                pass

    @property
    def revision(self):
        with self._lock:
            return self._revision

    @property
    def elements(self):
        return self.all()

    def document(self):
        with self._lock:
            return deepcopy(self._document)

    def snapshot(self):
        """Return a detached document and its matching revision atomically."""
        with self._lock:
            return deepcopy(self._document), self._revision

    def get(self, element_id):
        with self._lock:
            return deepcopy(self._index.get(element_id))

    def get_with_revision(self, element_id):
        """Return a detached element and its matching revision atomically."""
        with self._lock:
            return deepcopy(self._index.get(element_id)), self._revision

    def all(self):
        with self._lock:
            return deepcopy(self._document["elements"])

    @property
    def history_depth(self):
        with self._lock:
            return len(self._history)

    def _remember(self, document):
        size = len(
            json.dumps(
                document, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            ).encode("utf-8")
        )
        if size > self._max_history_bytes:
            # Skip recording snapshot that exceeds the maximum history budget,
            # but preserve existing valid history checkpoints.
            return
        self._history.append(deepcopy(document))
        self._history_sizes.append(size)
        self._history_bytes += size
        while (
            len(self._history) > self._max_history
            or self._history_bytes > self._max_history_bytes
        ):
            self._history.pop(0)
            self._history_bytes -= self._history_sizes.pop(0)

    def _commit(self, document, previous, remember=True, notify=True):
        replacement = normalize_document(
            document, validate_assets=document.get("files") != previous.get("files")
        )
        if replacement == previous:
            return False
        old = {el["id"]: el for el in previous["elements"]}
        for el in replacement["elements"]:
            before = old.get(el["id"])
            if before != el:
                version = before.get("version", 0) if before else 0
                updated = before.get("updated", 0) if before else 0
                el["version"] = (
                    version if type(version) is int and version >= 0 else 0
                ) + 1
                el["versionNonce"] = random.randrange(1, 2**31)
                el["updated"] = max(
                    time.time_ns() // 1_000_000,
                    (updated if type(updated) is int else 0) + 1,
                )
        if remember:
            self._remember(previous)
        self._document = replacement
        self._index = {el["id"]: el for el in replacement["elements"]}
        self._revision += 1
        if notify:
            self._notify()
        return True

    def replace(self, document, expected_revision=None):
        should_notify = False
        with self._lock:
            if self._editing:
                raise SceneError("Nested scene mutations are not supported")
            if expected_revision is not None and self._revision != expected_revision:
                raise SceneError(
                    "Scene changed while replacement was being prepared; retry the operation"
                )
            replacement = normalize_document(document)
            if replacement == self._document:
                return
            old = {el["id"]: el for el in self._document["elements"]}
            for el in replacement["elements"]:
                before = old.get(el["id"])
                if before is not None and before != el:
                    version = before.get("version", 0)
                    updated = before.get("updated", 0)
                    el["version"] = (
                        version if type(version) is int and version >= 0 else 0
                    ) + 1
                    el["versionNonce"] = random.randrange(1, 2**31)
                    el["updated"] = max(
                        time.time_ns() // 1_000_000,
                        (updated if type(updated) is int else 0) + 1,
                    )
            self._remember(self._document)
            self._document = replacement
            self._index = {el["id"]: el for el in replacement["elements"]}
            self._revision += 1
            should_notify = True
        if should_notify:
            self._notify()

    def apply(self, operation: Callable[[SceneDocument], T], remember: bool = True) -> T:
        """Apply a callback to a private draft. Exceptions roll back all edits."""
        should_notify = False
        with self._lock:
            if self._editing:
                raise SceneError("Nested scene mutations are not supported")
            self._editing = True
            try:
                draft = deepcopy(self._document)
                result = deepcopy(operation(draft))
                should_notify = self._commit(
                    draft, self._document, remember=remember, notify=False
                )
            finally:
                self._editing = False
        if should_notify:
            self._notify()
        return result

    def add_many(self, elements):
        incoming = validate_document(new_document(elements))["elements"]

        def append(document):
            document["elements"].extend(incoming)
            return [el["id"] for el in incoming]

        return self.apply(append)

    def add(self, element):
        return self.add_many([element])[0]

    def clear(self):
        should_notify = False
        with self._lock:
            if self._editing:
                raise SceneError("Nested scene mutations are not supported")
            should_notify = self._commit(new_document(), self._document, notify=False)
        if should_notify:
            self._notify()

    def undo(self):
        with self._lock:
            if self._editing:
                raise SceneError("Nested scene mutations are not supported")
            if not self._history:
                raise SceneError("Nothing to undo")
            previous = self._history[-1]
            replacement = normalize_document(previous)
            self._history.pop()
            self._history_bytes -= self._history_sizes.pop()
            self._document = replacement
            self._index = {el["id"]: el for el in self._document["elements"]}
            self._revision += 1
            result = {
                "status": "undone",
                "revision": self._revision,
                "history_depth": len(self._history),
            }
        self._notify()
        return result
