"""Publish Excalidraw scenes to excalidraw.com share backend using client-side AES-GCM encryption.

Implements the official Excalidraw v2 chunked binary protocol:
- Version 1 chunked binary encapsulation (concatBuffers)
- Pako/zlib compression
- AES-GCM 128-bit client-side encryption with random 12-byte IV
- Read-after-write verification to prevent broken links
- Bounded retries with exponential backoff for transient failures
- Local .excalidraw backup preservation
- Structured logging with zero secret leakage
"""

import base64
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import struct
import time
from typing import Any
import uuid
import zlib

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import httpx

from excalidraw_mcp.config import scene_directory
from excalidraw_mcp.errors import SceneError

logger = logging.getLogger("excalidraw_mcp.sharing")

EXCALIDRAW_POST_ENDPOINT = "https://json.excalidraw.com/api/v2/post/"
EXCALIDRAW_GET_ENDPOINT = "https://json.excalidraw.com/api/v2/"
EXCALIDRAW_SHARE_BASE = "https://excalidraw.com/#json="

CONCAT_BUFFERS_VERSION = 1
VERSION_BYTES = 4
CHUNK_SIZE_BYTES = 4
MAX_PAYLOAD_BYTES = 5 * 1024 * 1024  # 5 MB max payload for json.excalidraw.com
DEFAULT_TIMEOUT = 12.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF = 0.1


def concat_buffers(*buffers: bytes) -> bytes:
    """Concatenate multiple byte buffers using Excalidraw v2 chunked binary format.

    Structure:
    [VERSION (4 bytes uint32 big-endian)]
    [CHUNK_1_LEN (4 bytes uint32 big-endian)][CHUNK_1_DATA]
    [CHUNK_2_LEN (4 bytes uint32 big-endian)][CHUNK_2_DATA]
    ...
    """
    out = bytearray(struct.pack(">I", CONCAT_BUFFERS_VERSION))
    for buf in buffers:
        out.extend(struct.pack(">I", len(buf)))
        out.extend(buf)
    return bytes(out)


def split_buffers(data: bytes) -> list[bytes]:
    """Split a concatenated buffer created via concat_buffers.

    Raises SceneError if data is truncated, corrupted, or has an unsupported version.
    """
    if len(data) < VERSION_BYTES:
        raise SceneError("Buffer too short to contain Excalidraw version header")
    version = struct.unpack(">I", data[:VERSION_BYTES])[0]
    if version > CONCAT_BUFFERS_VERSION:
        raise SceneError(f"Unsupported Excalidraw buffer format version: {version}")

    cursor = VERSION_BYTES
    total_len = len(data)
    buffers: list[bytes] = []
    while cursor < total_len:
        if cursor + CHUNK_SIZE_BYTES > total_len:
            raise SceneError("Corrupted payload: unexpected end of buffer reading chunk length")
        chunk_size = struct.unpack(">I", data[cursor : cursor + CHUNK_SIZE_BYTES])[0]
        cursor += CHUNK_SIZE_BYTES
        end = cursor + chunk_size
        if end > total_len:
            raise SceneError("Corrupted payload: chunk length exceeds available buffer data")
        buffers.append(data[cursor:end])
        cursor = end
    return buffers


def encode_payload(document: dict[str, Any]) -> tuple[bytes, bytes, bytes]:
    """Serialize, compress, and encrypt an Excalidraw document into the v2 share format.

    Returns:
        tuple of (payload_bytes, aes_key_bytes, iv_bytes)
    """
    try:
        json_bytes = json.dumps(document, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as err:
        raise SceneError(f"Cannot serialize document to JSON: {err}") from err

    try:
        # Step 1: Encapsulate inner buffer with contentsMetadata (null metadata for database export)
        inner_buffer = concat_buffers(b"null", json_bytes)

        # Step 2: Compress with zlib (pako.deflate compatible)
        compressed_data = zlib.compress(inner_buffer, level=6)

        # Step 3: Generate 128-bit AES-GCM key and 12-byte IV
        aes_key = AESGCM.generate_key(bit_length=128)
        iv = os.urandom(12)
        aesgcm = AESGCM(aes_key)
        ciphertext = aesgcm.encrypt(iv, compressed_data, None)

        # Step 4: Encapsulate outer buffer with FileEncodingInfo metadata
        file_info = json.dumps(
            {"version": 2, "compression": "pako@1", "encryption": "AES-GCM"},
            separators=(",", ":"),
        ).encode("utf-8")

        payload = concat_buffers(file_info, iv, ciphertext)
    except Exception as err:
        raise SceneError(f"Encryption failed: {err}") from err

    if len(payload) > MAX_PAYLOAD_BYTES:
        raise SceneError(
            f"Encrypted payload ({len(payload)} bytes) exceeds Excalidraw limit of {MAX_PAYLOAD_BYTES} bytes"
        )

    return payload, aes_key, iv


def decode_payload(payload: bytes, aes_key: bytes) -> dict[str, Any]:
    """Decrypt, decompress, and deserialize an Excalidraw v2 share payload into a document.

    Raises SceneError on corruption, tag mismatch, or deserialization failure.
    """
    outer_chunks = split_buffers(payload)
    if len(outer_chunks) < 3:
        raise SceneError(
            f"Expected 3 outer chunks (metadata, iv, ciphertext), got {len(outer_chunks)}"
        )

    _file_info_bytes, iv, ciphertext = outer_chunks[0], outer_chunks[1], outer_chunks[2]
    if len(iv) != 12:
        raise SceneError(f"Invalid IV length: expected 12 bytes, got {len(iv)}")

    try:
        aesgcm = AESGCM(aes_key)
        decrypted_compressed = aesgcm.decrypt(iv, ciphertext, None)
    except InvalidTag as err:
        raise SceneError("Decryption failed: corrupted ciphertext or authentication tag mismatch") from err
    except Exception as err:
        raise SceneError(f"Decryption failed: {err}") from err

    try:
        uncompressed = zlib.decompress(decrypted_compressed)
    except zlib.error as err:
        raise SceneError(f"Decompression failed: corrupted zlib stream ({err})") from err

    inner_chunks = split_buffers(uncompressed)
    if len(inner_chunks) < 2:
        raise SceneError(
            f"Expected 2 inner chunks (metadata, document), got {len(inner_chunks)}"
        )

    _contents_meta_bytes, json_bytes = inner_chunks[0], inner_chunks[1]
    try:
        doc = json.loads(json_bytes.decode("utf-8"))
    except Exception as err:
        raise SceneError(f"Failed to parse decrypted document JSON: {err}") from err

    if not isinstance(doc, dict):
        raise SceneError("Decrypted document is not a valid JSON dictionary")

    return doc


def validate_export_document(document: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize an Excalidraw document before export."""
    if not isinstance(document, dict):
        raise SceneError("Document must be a valid scene dictionary")

    if "elements" in document and not isinstance(document["elements"], list):
        raise SceneError("Document elements must be a list")

    doc = dict(document)
    doc.setdefault("type", "excalidraw")
    doc.setdefault("version", 2)
    doc.setdefault("source", "https://excalidraw.com")
    doc.setdefault("elements", [])
    doc.setdefault("appState", {})
    doc.setdefault("files", {})

    if not isinstance(doc["elements"], list):
        raise SceneError("Document elements must be a list")
    if not isinstance(doc["appState"], dict):
        raise SceneError("Document appState must be a dictionary")
    if not isinstance(doc["files"], dict):
        raise SceneError("Document files must be a dictionary")

    return doc


def _save_local_backup(document: dict[str, Any]) -> str | None:
    """Preserve an unencrypted local backup of the scene prior to network operations."""
    try:
        root = scene_directory()
        backup_dir = root / "backups"
        backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        rand_id = uuid.uuid4().hex[:8]
        backup_path = backup_dir / f"export_backup_{ts}_{rand_id}.excalidraw"

        payload = json.dumps(document, indent=2, ensure_ascii=False)
        temp_path = backup_dir / f".tmp_{backup_path.name}"
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, backup_path)
        logger.info("Saved local export backup to %s", backup_path)
        return str(backup_path)
    except Exception as err:
        logger.warning("Could not preserve local export backup: %s", err)
        return None


def _verify_retrieval(
    client: httpx.Client,
    get_endpoint: str,
    doc_id: str,
    aes_key: bytes,
    original_document: dict[str, Any],
    max_retries: int,
    retry_backoff: float,
) -> None:
    """Fetch and verify the uploaded document from the backend to guarantee read-after-write integrity."""
    retrieval_url = f"{get_endpoint.rstrip('/')}/{doc_id}"
    logger.info("Verifying document retrieval from %s...", retrieval_url)

    t0 = time.perf_counter()
    resp = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.get(retrieval_url)
            if resp.status_code == 404:
                if attempt < max_retries:
                    delay = retry_backoff * (2 ** (attempt - 1))
                    time.sleep(delay)
                    continue
                raise SceneError(
                    f"Verification failed: document {doc_id} was not found on the Excalidraw server (HTTP 404)"
                )
            resp.raise_for_status()
            break
        except httpx.HTTPStatusError as err:
            if err.response.status_code >= 500 and attempt < max_retries:
                delay = retry_backoff * (2 ** (attempt - 1))
                time.sleep(delay)
                continue
            raise SceneError(
                f"Excalidraw share server returned HTTP {err.response.status_code} during verification: {err.response.text}"
            ) from err
        except (httpx.ConnectError, httpx.TimeoutException) as err:
            if attempt < max_retries:
                delay = retry_backoff * (2 ** (attempt - 1))
                time.sleep(delay)
                continue
            raise SceneError(f"Verification network error: {err}") from err

    if resp is None:
        raise SceneError(f"Verification failed: could not retrieve document {doc_id}")

    try:
        retrieved_doc = decode_payload(resp.content, aes_key)
    except Exception as err:
        raise SceneError(
            f"Verification failed: uploaded document {doc_id} could not be decrypted/decompressed ({err})"
        ) from err

    orig_elements = original_document.get("elements", [])
    retr_elements = retrieved_doc.get("elements", [])
    if len(orig_elements) != len(retr_elements):
        raise SceneError(
            f"Verification failed: element count mismatch (expected {len(orig_elements)}, got {len(retr_elements)})"
        )

    verify_duration_ms = (time.perf_counter() - t0) * 1000.0
    logger.info(
        "Read-after-write verification succeeded for doc_id=%s in %.2fms",
        doc_id,
        verify_duration_ms,
    )


def export_to_excalidraw_url(
    document: dict[str, Any],
    timeout: float = DEFAULT_TIMEOUT,
    endpoint: str = EXCALIDRAW_POST_ENDPOINT,
    get_endpoint: str = EXCALIDRAW_GET_ENDPOINT,
    verify: bool = True,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_backoff: float = DEFAULT_RETRY_BACKOFF,
    save_backup: bool = True,
) -> dict[str, Any]:
    """Publish an Excalidraw document to excalidraw.com with client-side encryption.

    Flow:
    1. Validate document schema and JSON serializability.
    2. Save a local unencrypted .excalidraw backup.
    3. Serialize, compress (zlib), and encrypt (AES-GCM 128) into Excalidraw v2 chunked binary.
    4. Post chunked binary payload to excalidraw backend with bounded retries and exponential backoff.
    5. Perform read-after-write verification by retrieving and decrypting the scene.
    6. Return excalidraw.com shareable link with decryption key in hash fragment.
    """
    normalized_doc = validate_export_document(document)

    backup_path = None
    if save_backup:
        backup_path = _save_local_backup(normalized_doc)

    payload, aes_key, iv = encode_payload(normalized_doc)

    logger.info(
        "Exporting Excalidraw document (elements: %d, payload_bytes: %d)",
        len(normalized_doc.get("elements", [])),
        len(payload),
    )

    doc_id = None
    http_timeout = httpx.Timeout(
        timeout=timeout,
        connect=min(timeout, 5.0),
        read=timeout,
        write=timeout,
    )

    try:
        with httpx.Client(timeout=http_timeout) as client:
            for attempt in range(1, max_retries + 1):
                attempt_t0 = time.perf_counter()
                try:
                    resp = client.post(
                        endpoint,
                        content=payload,
                        headers={"Content-Type": "application/octet-stream"},
                    )
                    duration_ms = (time.perf_counter() - attempt_t0) * 1000.0
                    status_code = getattr(resp, "status_code", None)

                    if isinstance(status_code, int) and status_code == 429:
                        retry_after_str = resp.headers.get("Retry-After") if hasattr(resp, "headers") else None
                        delay = retry_backoff * (2 ** (attempt - 1))
                        if retry_after_str:
                            try:
                                delay = min(max(float(retry_after_str), delay), 5.0)
                            except ValueError:
                                pass
                        logger.warning(
                            "Excalidraw share server rate limit (HTTP 429) on attempt %d/%d (%.2fms). Retrying in %.2fs...",
                            attempt,
                            max_retries,
                            duration_ms,
                            delay,
                        )
                        if attempt < max_retries:
                            time.sleep(delay)
                            continue
                        raise SceneError(
                            f"Excalidraw share server rate limit exceeded (HTTP 429): {getattr(resp, 'text', '')}"
                        )

                    if isinstance(status_code, int) and status_code >= 500:
                        logger.warning(
                            "Excalidraw share server error (HTTP %d) on attempt %d/%d (%.2fms)",
                            status_code,
                            attempt,
                            max_retries,
                            duration_ms,
                        )
                        if attempt < max_retries:
                            delay = retry_backoff * (2 ** (attempt - 1))
                            time.sleep(delay)
                            continue
                        raise SceneError(
                            f"Excalidraw share server returned HTTP {status_code}: {getattr(resp, 'text', '')}"
                        )

                    resp.raise_for_status()

                    try:
                        data = resp.json()
                    except Exception as err:
                        raise SceneError(f"Malformed response from Excalidraw server: {err}") from err

                    doc_id = data.get("id")
                    if not doc_id or not isinstance(doc_id, str):
                        raise SceneError("Server did not return a valid document ID")

                    logger.info(
                        "Upload succeeded on attempt %d/%d in %.2fms (doc_id=%s)",
                        attempt,
                        max_retries,
                        duration_ms,
                        doc_id,
                    )
                    break

                except httpx.TimeoutException as err:
                    duration_ms = (time.perf_counter() - attempt_t0) * 1000.0
                    logger.warning(
                        "Upload timed out after %.2fms on attempt %d/%d",
                        duration_ms,
                        attempt,
                        max_retries,
                    )
                    if attempt < max_retries:
                        delay = retry_backoff * (2 ** (attempt - 1))
                        time.sleep(delay)
                        continue
                    raise SceneError(f"Excalidraw share server timed out after {timeout}s") from err

                except httpx.HTTPStatusError as err:
                    status = getattr(err.response, "status_code", None) if hasattr(err, "response") else None
                    if isinstance(status, int) and (status >= 500 or status == 429) and attempt < max_retries:
                        delay = retry_backoff * (2 ** (attempt - 1))
                        time.sleep(delay)
                        continue
                    resp_text = getattr(err.response, "text", "") if hasattr(err, "response") else ""
                    raise SceneError(
                        f"Excalidraw share server returned HTTP {status}: {resp_text}"
                    ) from err

                except httpx.RequestError as err:
                    logger.warning(
                        "Network request error on attempt %d/%d: %s",
                        attempt,
                        max_retries,
                        err,
                    )
                    if attempt < max_retries:
                        delay = retry_backoff * (2 ** (attempt - 1))
                        time.sleep(delay)
                        continue
                    raise SceneError(
                        f"Network error while connecting to Excalidraw server: {err}"
                    ) from err

            if not doc_id:
                raise SceneError("Failed to obtain document ID from Excalidraw server")

            if verify:
                _verify_retrieval(
                    client=client,
                    get_endpoint=get_endpoint,
                    doc_id=doc_id,
                    aes_key=aes_key,
                    original_document=normalized_doc,
                    max_retries=max_retries,
                    retry_backoff=retry_backoff,
                )

    except SceneError:
        raise
    except Exception as err:
        raise SceneError(f"Upload to Excalidraw failed: {err}") from err

    key_b64 = base64.urlsafe_b64encode(aes_key).rstrip(b"=").decode("utf-8")
    shareable_url = f"{EXCALIDRAW_SHARE_BASE}{doc_id},{key_b64}"
    logger.info("Excalidraw share link created: %s%s,[REDACTED]", EXCALIDRAW_SHARE_BASE, doc_id)

    result: dict[str, Any] = {
        "status": "published",
        "url": shareable_url,
        "id": doc_id,
    }
    if backup_path:
        result["backup_path"] = backup_path

    return result
