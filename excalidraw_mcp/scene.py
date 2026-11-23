"""Validated document persistence in an explicitly configured directory."""

import json
import os
import re
import stat
import uuid
from contextlib import contextmanager

from excalidraw_mcp.config import max_scene_bytes, scene_directory
from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.document import normalize_document, serialize_document
from excalidraw_mcp.models import new_document as new_document


def _filename(name):
    if not isinstance(name, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", name
    ):
        raise SceneError(
            "Scene name must be 1–128 letters, digits, underscores or hyphens, "
            "starting with a letter or digit; omit the extension"
        )
    return f"{name}.excalidraw"


HAS_POSIX_DIR_FD = hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NOFOLLOW")


@contextmanager
def _directory(create=False):
    root = scene_directory().resolve()
    if create:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if HAS_POSIX_DIR_FD:
        # The configured root is trusted. Anchor operations to its open descriptor
        # so replacement of a directory path cannot redirect an in-flight operation.
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            yield root, fd
        finally:
            os.close(fd)
    else:
        if not create and not root.is_dir():
            raise FileNotFoundError(f"Scene directory does not exist: {root}")
        yield root, None


def _check_target(fd, filename, root=None):
    if fd is not None:
        try:
            info = os.stat(filename, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            return False
        if not stat.S_ISREG(info.st_mode):
            raise SceneError(
                "Scene target must be a regular file, not a symlink or directory"
            )
        return True
    if root is None:
        root = scene_directory().resolve()
    target = root / filename
    try:
        info = os.stat(target, follow_symlinks=False)
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(info.st_mode):
        raise SceneError(
            "Scene target must be a regular file, not a symlink or directory"
        )
    return True


def save_scene(name, document, overwrite=False):
    filename = _filename(name)
    payload = serialize_document(document)
    payload_size = len(payload.encode("utf-8"))
    size_limit = max_scene_bytes()
    if payload_size > size_limit:
        raise SceneError(f"Scene exceeds the configured limit of {size_limit} bytes")
    try:
        with _directory(create=True) as (root, directory_fd):
            if _check_target(directory_fd, filename, root=root) and not overwrite:
                raise SceneError(
                    "Scene already exists; use overwrite=true to replace it"
                )
            temporary = f".scene-{uuid.uuid4().hex}.tmp"
            if directory_fd is not None:
                fd = os.open(
                    temporary,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=directory_fd,
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as stream:
                        stream.write(payload)
                        stream.flush()
                        os.fsync(stream.fileno())
                    if overwrite:
                        _check_target(directory_fd, filename, root=root)
                        os.replace(
                            temporary,
                            filename,
                            src_dir_fd=directory_fd,
                            dst_dir_fd=directory_fd,
                        )
                    else:
                        # Publishing with a hard link atomically refuses an existing
                        # destination, even when another save wins the race.
                        os.link(
                            temporary,
                            filename,
                            src_dir_fd=directory_fd,
                            dst_dir_fd=directory_fd,
                            follow_symlinks=False,
                        )
                    # Persist the directory entry as well as the file contents.
                    os.fsync(directory_fd)
                finally:
                    try:
                        os.unlink(temporary, dir_fd=directory_fd)
                    except FileNotFoundError:
                        pass
            else:
                temp_path = root / temporary
                dest_path = root / filename
                try:
                    with open(temp_path, "w", encoding="utf-8") as stream:
                        stream.write(payload)
                        stream.flush()
                        os.fsync(stream.fileno())
                    if overwrite:
                        _check_target(directory_fd, filename, root=root)
                        os.replace(temp_path, dest_path)
                    else:
                        try:
                            os.link(temp_path, dest_path)
                        except (AttributeError, OSError):
                            if dest_path.exists():
                                raise FileExistsError(f"{dest_path} already exists")
                            os.replace(temp_path, dest_path)
                finally:
                    try:
                        temp_path.unlink(missing_ok=True)
                    except Exception:
                        pass
            return str(root / filename)
    except FileExistsError as exc:
        raise SceneError(
            "Scene already exists; use overwrite=true to replace it"
        ) from exc
    except UnicodeError as exc:
        raise SceneError("Scene contains text that cannot be encoded as UTF-8") from exc
    except OSError as exc:
        raise SceneError(f"Could not save scene: {exc.strerror}") from exc


def load_scene(name):
    filename = _filename(name)
    try:
        with _directory() as (root, directory_fd):
            if not _check_target(directory_fd, filename, root=root):
                raise SceneError(f"Scene '{name}' not found")
            if directory_fd is not None:
                fd = os.open(
                    filename,
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=directory_fd,
                )
                stream_ctx = os.fdopen(fd, "rb")
            else:
                stream_ctx = open(root / filename, "rb")
            with stream_ctx as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise SceneError("Scene target must be a regular file")
                size_limit = max_scene_bytes()
                if info.st_size > size_limit:
                    raise SceneError(
                        f"Scene exceeds the configured limit of {size_limit} bytes"
                    )
                payload = stream.read(size_limit + 1)
                if len(payload) > size_limit:
                    raise SceneError(
                        f"Scene exceeds the configured limit of {size_limit} bytes"
                    )
                document = json.loads(payload)
        return normalize_document(document)
    except FileNotFoundError as exc:
        raise SceneError(f"Scene '{name}' not found") from exc
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise SceneError("Scene is not a valid UTF-8 JSON document") from exc
    except OSError as exc:
        raise SceneError(f"Could not load scene: {exc.strerror}") from exc


def list_scenes():
    try:
        with _directory() as (root, directory_fd):
            names = []
            entries = os.listdir(directory_fd) if directory_fd is not None else os.listdir(root)
            for filename in entries:
                if not filename.endswith(".excalidraw"):
                    continue
                name = filename.removesuffix(".excalidraw")
                try:
                    if _filename(name) != filename:
                        continue
                    if directory_fd is not None:
                        info = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
                    else:
                        info = os.stat(root / filename, follow_symlinks=False)
                except (FileNotFoundError, SceneError):
                    continue
                if stat.S_ISREG(info.st_mode):
                    names.append(name)
            return sorted(names)
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise SceneError(f"Could not list scenes: {exc.strerror}") from exc
