"""Comprehensive test suite for Excalidraw encrypted sharing, v2 binary protocol, retries, and verification."""

import base64
import json
import logging
import os
from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch
import zlib

import httpx

from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.sharing import (
    CONCAT_BUFFERS_VERSION,
    MAX_PAYLOAD_BYTES,
    _save_local_backup,
    _verify_retrieval,
    concat_buffers,
    decode_payload,
    encode_payload,
    export_to_excalidraw_url,
    split_buffers,
    validate_export_document,
)


class TestBufferProtocol(unittest.TestCase):
    def test_concat_and_split_buffers_roundtrip(self):
        chunks = [b"first_chunk_metadata", b"second_chunk_iv12345", b"third_chunk_ciphertext_data"]
        concatenated = concat_buffers(*chunks)
        self.assertEqual(concatenated[:4], struct.pack(">I", CONCAT_BUFFERS_VERSION))

        extracted = split_buffers(concatenated)
        self.assertEqual(len(extracted), 3)
        self.assertEqual(extracted, chunks)

    def test_split_buffers_version_validation(self):
        invalid_version = struct.pack(">I", 999) + struct.pack(">I", 4) + b"test"
        with self.assertRaisesRegex(SceneError, "Unsupported Excalidraw buffer format version"):
            split_buffers(invalid_version)

    def test_split_buffers_truncated_header(self):
        with self.assertRaisesRegex(SceneError, "Buffer too short"):
            split_buffers(b"\x00\x00")

    def test_split_buffers_truncated_chunk_length(self):
        # 4 bytes version + 2 bytes partial chunk length
        truncated = struct.pack(">I", CONCAT_BUFFERS_VERSION) + b"\x00\x01"
        with self.assertRaisesRegex(SceneError, "unexpected end of buffer reading chunk length"):
            split_buffers(truncated)

    def test_split_buffers_truncated_chunk_data(self):
        # Header + claims chunk is 100 bytes long, but only 5 bytes provided
        truncated = struct.pack(">I", CONCAT_BUFFERS_VERSION) + struct.pack(">I", 100) + b"hello"
        with self.assertRaisesRegex(SceneError, "chunk length exceeds available buffer data"):
            split_buffers(truncated)


class TestPayloadEncodingAndDecoding(unittest.TestCase):
    def test_encode_and_decode_roundtrip_equality(self):
        doc = {
            "type": "excalidraw",
            "version": 2,
            "source": "https://excalidraw.com",
            "elements": [
                {
                    "id": "box-1",
                    "type": "rectangle",
                    "x": 50,
                    "y": 60,
                    "width": 120,
                    "height": 80,
                    "strokeColor": "#1e1e1e",
                    "backgroundColor": "#93c5fd",
                }
            ],
            "appState": {"viewBackgroundColor": "#ffffff"},
            "files": {},
        }

        payload, aes_key, iv = encode_payload(doc)
        self.assertEqual(len(iv), 12)
        self.assertEqual(len(aes_key), 16)  # 128 bits
        self.assertGreater(len(payload), 0)

        # Decode using the aes_key
        decoded = decode_payload(payload, aes_key)
        self.assertEqual(decoded["type"], "excalidraw")
        self.assertEqual(decoded["version"], 2)
        self.assertEqual(len(decoded["elements"]), 1)
        self.assertEqual(decoded["elements"][0]["id"], "box-1")
        self.assertEqual(decoded["elements"][0]["x"], 50)
        self.assertEqual(decoded["appState"]["viewBackgroundColor"], "#ffffff")

    def test_decode_payload_invalid_outer_chunk_count(self):
        # Only 2 chunks instead of 3
        invalid_payload = concat_buffers(b"meta", b"iv_is_12_byte")
        with self.assertRaisesRegex(SceneError, "Expected 3 outer chunks"):
            decode_payload(invalid_payload, os.urandom(16))

    def test_decode_payload_invalid_iv_length(self):
        invalid_payload = concat_buffers(b"meta", b"short_iv", b"ciphertext")
        with self.assertRaisesRegex(SceneError, "Invalid IV length"):
            decode_payload(invalid_payload, os.urandom(16))

    def test_decode_payload_corrupted_ciphertext(self):
        doc = {"type": "excalidraw", "version": 2, "elements": []}
        payload, aes_key, _iv = encode_payload(doc)
        outer = split_buffers(payload)
        # Corrupt the ciphertext bytes
        tampered_ciphertext = bytearray(outer[2])
        tampered_ciphertext[0] ^= 0xFF
        corrupted_payload = concat_buffers(outer[0], outer[1], bytes(tampered_ciphertext))

        with self.assertRaisesRegex(SceneError, "corrupted ciphertext or authentication tag mismatch"):
            decode_payload(corrupted_payload, aes_key)

    def test_decode_payload_corrupted_zlib(self):
        # Encrypt raw non-zlib bytes
        aes_key = os.urandom(16)
        iv = os.urandom(12)
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        ct = AESGCM(aes_key).encrypt(iv, b"this_is_not_zlib_compressed_data", None)
        meta = b'{"version":2,"compression":"pako@1","encryption":"AES-GCM"}'
        payload = concat_buffers(meta, iv, ct)

        with self.assertRaisesRegex(SceneError, "corrupted zlib stream"):
            decode_payload(payload, aes_key)

    def test_decode_payload_invalid_inner_chunk_count(self):
        aes_key = os.urandom(16)
        iv = os.urandom(12)
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        # Inner buffer with only 1 chunk instead of 2
        inner = concat_buffers(b"single_chunk_only")
        ct = AESGCM(aes_key).encrypt(iv, zlib.compress(inner), None)
        meta = b'{"version":2,"compression":"pako@1","encryption":"AES-GCM"}'
        payload = concat_buffers(meta, iv, ct)

        with self.assertRaisesRegex(SceneError, "Expected 2 inner chunks"):
            decode_payload(payload, aes_key)

    def test_decode_payload_malformed_inner_json(self):
        aes_key = os.urandom(16)
        iv = os.urandom(12)
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        inner = concat_buffers(b"null", b"{bad json: definitely not valid}")
        ct = AESGCM(aes_key).encrypt(iv, zlib.compress(inner), None)
        meta = b'{"version":2,"compression":"pako@1","encryption":"AES-GCM"}'
        payload = concat_buffers(meta, iv, ct)

        with self.assertRaisesRegex(SceneError, "Failed to parse decrypted document JSON"):
            decode_payload(payload, aes_key)

    def test_encode_payload_oversized(self):
        doc = {"type": "excalidraw", "elements": [], "huge_padding": "A" * (MAX_PAYLOAD_BYTES + 1000)}
        with patch("excalidraw_mcp.sharing.MAX_PAYLOAD_BYTES", 500):
            with self.assertRaisesRegex(SceneError, "exceeds Excalidraw limit"):
                encode_payload(doc)


class TestExportValidation(unittest.TestCase):
    def test_validate_export_document_rejects_non_dict(self):
        for invalid in (None, 123, "invalid", [1, 2, 3], False):
            with self.assertRaisesRegex(SceneError, "valid scene dictionary"):
                validate_export_document(invalid)

    def test_validate_export_document_rejects_non_list_elements(self):
        with self.assertRaisesRegex(SceneError, "elements must be a list"):
            validate_export_document({"type": "excalidraw", "elements": "not_a_list"})

    def test_validate_export_document_injects_defaults(self):
        minimal = {"elements": [{"id": "1", "type": "rectangle", "x": 0, "y": 0}]}
        normalized = validate_export_document(minimal)
        self.assertEqual(normalized["type"], "excalidraw")
        self.assertEqual(normalized["version"], 2)
        self.assertEqual(normalized["appState"], {})
        self.assertEqual(normalized["files"], {})
        self.assertEqual(len(normalized["elements"]), 1)


class TestNetworkUploadAndRetries(unittest.TestCase):
    def test_upload_transient_502_recovers_on_retry(self):
        doc = {"type": "excalidraw", "elements": [{"id": "el1", "type": "rectangle", "x": 0, "y": 0}]}
        mock_502 = MagicMock()
        mock_502.status_code = 502
        mock_502.text = "Bad Gateway"

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {"id": "recovering-doc-123"}
        mock_200.raise_for_status = MagicMock()

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, {"EXCALIDRAW_SCENE_DIR": tmp_dir}):
                with patch("httpx.Client.post", side_effect=[mock_502, mock_200]) as mock_post:
                    result = export_to_excalidraw_url(doc, max_retries=3, retry_backoff=0.01, verify=False)
                    self.assertEqual(result["id"], "recovering-doc-123")
                    self.assertEqual(result["status"], "published")
                    self.assertEqual(mock_post.call_count, 2)

    def test_upload_exhausts_retries_on_persistent_500(self):
        doc = {"type": "excalidraw", "elements": []}
        mock_500 = MagicMock()
        mock_500.status_code = 500
        mock_500.text = "Internal Server Error"

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, {"EXCALIDRAW_SCENE_DIR": tmp_dir}):
                with patch("httpx.Client.post", return_value=mock_500) as mock_post:
                    with self.assertRaisesRegex(SceneError, "returned HTTP 500"):
                        export_to_excalidraw_url(doc, max_retries=3, retry_backoff=0.01, verify=False)
                    self.assertEqual(mock_post.call_count, 3)

    def test_upload_429_rate_limit_with_retry_after(self):
        doc = {"type": "excalidraw", "elements": []}
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.headers = {"Retry-After": "0.01"}
        mock_429.text = "Too Many Requests"

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {"id": "rate-limited-doc-456"}
        mock_200.raise_for_status = MagicMock()

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, {"EXCALIDRAW_SCENE_DIR": tmp_dir}):
                with patch("httpx.Client.post", side_effect=[mock_429, mock_200]):
                    result = export_to_excalidraw_url(doc, max_retries=2, retry_backoff=0.01, verify=False)
                    self.assertEqual(result["id"], "rate-limited-doc-456")

    def test_upload_non_retryable_400_bad_request(self):
        doc = {"type": "excalidraw", "elements": []}
        mock_400 = MagicMock()
        mock_400.status_code = 400
        mock_400.raise_for_status.side_effect = httpx.HTTPStatusError(
            "400 Bad Request",
            request=MagicMock(),
            response=MagicMock(status_code=400, text="Bad Request"),
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, {"EXCALIDRAW_SCENE_DIR": tmp_dir}):
                with patch("httpx.Client.post", return_value=mock_400) as mock_post:
                    with self.assertRaisesRegex(SceneError, "returned HTTP 400"):
                        export_to_excalidraw_url(doc, max_retries=3, retry_backoff=0.01, verify=False)
                    self.assertEqual(mock_post.call_count, 1)

    def test_upload_malformed_server_json_response(self):
        doc = {"type": "excalidraw", "elements": []}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"error": "unexpected format missing id"}

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, {"EXCALIDRAW_SCENE_DIR": tmp_dir}):
                with patch("httpx.Client.post", return_value=mock_resp):
                    with self.assertRaisesRegex(SceneError, "Server did not return a valid document ID"):
                        export_to_excalidraw_url(doc, max_retries=1, verify=False)


class TestReadAfterWriteVerification(unittest.TestCase):
    def test_verification_success(self):
        doc = {
            "type": "excalidraw",
            "version": 2,
            "elements": [{"id": "el1", "type": "rectangle", "x": 10, "y": 20}],
        }
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {"id": "verified-scene-789"}
        mock_post_resp.raise_for_status = MagicMock()

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.raise_for_status = MagicMock()

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, {"EXCALIDRAW_SCENE_DIR": tmp_dir}):
                with patch("httpx.Client.post", return_value=mock_post_resp) as mock_post:
                    def get_side_effect(*args, **kwargs):
                        mock_get_resp.content = mock_post.call_args[1]["content"]
                        return mock_get_resp

                    with patch("httpx.Client.get", side_effect=get_side_effect) as mock_get:
                        result = export_to_excalidraw_url(doc, verify=True, max_retries=1)
                        self.assertEqual(result["id"], "verified-scene-789")
                        self.assertEqual(result["status"], "published")
                        self.assertEqual(mock_get.call_count, 1)

    def test_verification_404_failure_raises_scene_error(self):
        doc = {"type": "excalidraw", "version": 2, "elements": []}
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {"id": "missing-scene-404"}
        mock_post_resp.raise_for_status = MagicMock()

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 404
        mock_get_resp.text = "Not Found"

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, {"EXCALIDRAW_SCENE_DIR": tmp_dir}):
                with patch("httpx.Client.post", return_value=mock_post_resp):
                    with patch("httpx.Client.get", return_value=mock_get_resp):
                        with self.assertRaisesRegex(SceneError, "Verification failed: document missing-scene-404 was not found"):
                            export_to_excalidraw_url(doc, verify=True, max_retries=1)

    def test_verification_corrupted_retrieved_payload(self):
        doc = {"type": "excalidraw", "version": 2, "elements": []}
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {"id": "corrupted-scene"}
        mock_post_resp.raise_for_status = MagicMock()

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.content = b"completely_garbage_unreadable_bytes"
        mock_get_resp.raise_for_status = MagicMock()

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, {"EXCALIDRAW_SCENE_DIR": tmp_dir}):
                with patch("httpx.Client.post", return_value=mock_post_resp):
                    with patch("httpx.Client.get", return_value=mock_get_resp):
                        with self.assertRaisesRegex(SceneError, "could not be decrypted"):
                            export_to_excalidraw_url(doc, verify=True, max_retries=1)

    def test_verification_element_count_mismatch(self):
        doc = {
            "type": "excalidraw",
            "version": 2,
            "elements": [{"id": "el1", "type": "rectangle", "x": 0, "y": 0}],
        }
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {"id": "mismatched-scene"}
        mock_post_resp.raise_for_status = MagicMock()

        other_doc = {"type": "excalidraw", "version": 2, "elements": []}
        other_payload, _, _ = encode_payload(other_doc)

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.content = other_payload
        mock_get_resp.raise_for_status = MagicMock()

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, {"EXCALIDRAW_SCENE_DIR": tmp_dir}):
                with patch("httpx.Client.post", return_value=mock_post_resp):
                    with patch("httpx.Client.get", return_value=mock_get_resp):
                        with self.assertRaisesRegex(SceneError, "Verification failed"):
                            export_to_excalidraw_url(doc, verify=True, max_retries=1)


class TestLocalBackupPreservation(unittest.TestCase):
    def test_local_backup_created_and_persisted(self):
        doc = {
            "type": "excalidraw",
            "version": 2,
            "elements": [{"id": "box1", "type": "rectangle", "x": 100, "y": 100}],
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, {"EXCALIDRAW_SCENE_DIR": tmp_dir}):
                backup_file = _save_local_backup(doc)
                self.assertIsNotNone(backup_file)
                self.assertTrue(Path(backup_file).is_file())

                with open(backup_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self.assertEqual(saved["elements"][0]["id"], "box1")

    def test_local_backup_preserved_on_upload_failure(self):
        doc = {"type": "excalidraw", "version": 2, "elements": [{"id": "fail-box", "type": "diamond", "x": 0, "y": 0}]}
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Downstream crash"

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, {"EXCALIDRAW_SCENE_DIR": tmp_dir}):
                with patch("httpx.Client.post", return_value=mock_resp):
                    with self.assertRaises(SceneError):
                        export_to_excalidraw_url(doc, max_retries=1, verify=False)

                backups = list((Path(tmp_dir) / "backups").glob("export_backup_*.excalidraw"))
                self.assertEqual(len(backups), 1)
                with open(backups[0], "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self.assertEqual(saved["elements"][0]["id"], "fail-box")


class TestEdgeCases(unittest.TestCase):
    def test_empty_scene_roundtrip(self):
        doc = {"type": "excalidraw", "version": 2, "elements": [], "appState": {}, "files": {}}
        payload, aes_key, iv = encode_payload(doc)
        decoded = decode_payload(payload, aes_key)
        self.assertEqual(decoded["elements"], [])

    def test_large_diagram_500_elements(self):
        elements = [
            {
                "id": f"node-{i}",
                "type": "rectangle",
                "x": i * 10,
                "y": i * 15,
                "width": 100,
                "height": 50,
                "text": f"Service Node {i}",
            }
            for i in range(500)
        ]
        doc = {"type": "excalidraw", "version": 2, "elements": elements, "appState": {}, "files": {}}
        payload, aes_key, iv = encode_payload(doc)
        decoded = decode_payload(payload, aes_key)
        self.assertEqual(len(decoded["elements"]), 500)
        self.assertEqual(decoded["elements"][499]["id"], "node-499")

    def test_unicode_and_emojis(self):
        doc = {
            "type": "excalidraw",
            "version": 2,
            "elements": [
                {
                    "id": "text-japanese",
                    "type": "text",
                    "x": 0,
                    "y": 0,
                    "text": "日本語のテスト (Excalidraw 描画)",
                },
                {
                    "id": "text-arabic",
                    "type": "text",
                    "x": 10,
                    "y": 10,
                    "text": "مرحبا بالعالم - رسم تخطيطي",
                },
                {
                    "id": "text-emojis",
                    "type": "text",
                    "x": 20,
                    "y": 20,
                    "text": "🎨 Diagrams with AI 🚀 📐 💡",
                },
            ],
            "appState": {},
            "files": {},
        }
        payload, aes_key, iv = encode_payload(doc)
        decoded = decode_payload(payload, aes_key)
        self.assertEqual(len(decoded["elements"]), 3)
        self.assertEqual(decoded["elements"][0]["text"], "日本語のテスト (Excalidraw 描画)")
        self.assertEqual(decoded["elements"][1]["text"], "مرحبا بالعالم - رسم تخطيطي")
        self.assertEqual(decoded["elements"][2]["text"], "🎨 Diagrams with AI 🚀 📐 💡")

    def test_embedded_images_and_files(self):
        doc = {
            "type": "excalidraw",
            "version": 2,
            "elements": [
                {
                    "id": "img-1",
                    "type": "image",
                    "x": 100,
                    "y": 100,
                    "fileId": "file-xyz-123",
                }
            ],
            "appState": {},
            "files": {
                "file-xyz-123": {
                    "mimeType": "image/png",
                    "id": "file-xyz-123",
                    "dataURL": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                    "created": 123456789,
                }
            },
        }
        payload, aes_key, iv = encode_payload(doc)
        decoded = decode_payload(payload, aes_key)
        self.assertIn("file-xyz-123", decoded["files"])
        self.assertEqual(decoded["elements"][0]["fileId"], "file-xyz-123")


class TestSecurityAndStructuredLogging(unittest.TestCase):
    def test_logging_does_not_leak_encryption_key(self):
        doc = {"type": "excalidraw", "version": 2, "elements": [{"id": "n1", "type": "rectangle", "x": 0, "y": 0}]}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "secure-doc-abc"}
        mock_resp.raise_for_status = MagicMock()

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, {"EXCALIDRAW_SCENE_DIR": tmp_dir}):
                with patch("httpx.Client.post", return_value=mock_resp):
                    with self.assertLogs("excalidraw_mcp.sharing", level="INFO") as cm:
                        result = export_to_excalidraw_url(doc, verify=False)

        url = result["url"]
        self.assertTrue(url.startswith("https://excalidraw.com/#json=secure-doc-abc,"))
        key_in_url = url.split(",")[-1]
        self.assertEqual(len(key_in_url), 22)  # 128-bit key in unpadded base64url

        # Check log records: key MUST NOT appear anywhere in the logs
        logged_text = "\n".join(cm.output)
        self.assertNotIn(key_in_url, logged_text)
        self.assertIn("[REDACTED]", logged_text)
        self.assertIn("secure-doc-abc", logged_text)

    def test_sharing_module_does_not_import_unittest_mock(self):
        """Ensure sharing module does not import unittest or unittest.mock in production code."""
        import excalidraw_mcp.sharing as sharing_mod

        self.assertFalse(
            hasattr(sharing_mod, "unittest"),
            "excalidraw_mcp.sharing should not import unittest or unittest.mock",
        )


if __name__ == "__main__":
    unittest.main()
