"""
DevUploads.com API client.

DevUploads runs on the XFileSharingPro (XFS) script family. Confirmed
directly against devuploads.com/api itself: account/info, account/stats,
upload/server, and file/list — their parameters match byte-for-byte
against the public XFileSharingPro reference (https://xfilesharing.com/pages/api).
Every other endpoint below follows that same, well-established convention.

Two endpoints (file_delete, folder_delete) aren't in the base XFS
reference doc — they're extremely common additions on PPD-configured XFS
sites like this one, but couldn't be individually confirmed against
DevUploads directly (their docs page blocks automated fetching). If
either ever comes back with an error, that's the one to double-check
against your own account's API panel — every method here is independent,
so fixing one doesn't touch anything else.

All methods return a DevUploadsResult so callers never have to guess
whether a field exists: ok (bool), data (the "result" value on success),
error (human-readable message on failure), raw (the full parsed response,
for anything not modeled here — e.g. upload/server's sess_id, which
DevUploads returns as a sibling of "result" rather than inside it).
"""
import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://devuploads.com/api"
TIMEOUT = 60.0


@dataclass
class DevUploadsResult:
    ok: bool
    data: Any = None
    error: Optional[str] = None
    raw: Optional[dict] = None

    @classmethod
    def fail(cls, error: str, raw=None) -> "DevUploadsResult":
        return cls(ok=False, error=error, raw=raw)

    @classmethod
    def success(cls, data, raw=None) -> "DevUploadsResult":
        return cls(ok=True, data=data, raw=raw)


async def _get(path: str, params: dict) -> DevUploadsResult:
    params = {k: v for k, v in params.items() if v is not None}
    url = f"{BASE_URL}/{path}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, params=params)
    except httpx.HTTPError as e:
        return DevUploadsResult.fail(f"Network error contacting DevUploads: {e}")
    return _parse_envelope(resp)


def _parse_envelope(resp: httpx.Response) -> DevUploadsResult:
    try:
        payload = resp.json()
    except ValueError:
        return DevUploadsResult.fail(f"DevUploads returned a non-JSON response (HTTP {resp.status_code}).")
    if not isinstance(payload, dict):
        return DevUploadsResult.fail(f"Unexpected response shape from DevUploads: {payload}")

    status = payload.get("status")
    if status not in (200, "200"):
        return DevUploadsResult.fail(f"DevUploads error: {payload.get('msg') or status}", raw=payload)
    return DevUploadsResult.success(payload.get("result"), raw=payload)


def has_key(key: str) -> bool:
    return bool(key and key.strip())


# ---------------- Account ----------------

async def account_info(key: str) -> DevUploadsResult:
    return await _get("account/info", {"key": key})


async def account_stats(key: str) -> DevUploadsResult:
    return await _get("account/stats", {"key": key})


# ---------------- Upload ----------------

async def get_upload_server(key: str) -> DevUploadsResult:
    """Step 1 of uploading: ask for a server ready to accept a file.
    On success, .data is the upload URL; the sess_id needed for step 2 is
    on .raw['sess_id'] (DevUploads returns it as a sibling of "result",
    not inside it)."""
    return await _get("upload/server", {"key": key})


async def upload_file(key: str, filepath: str, filename: str = None) -> DevUploadsResult:
    """Full 2-step upload: get a server, then POST the file to it.
    Returns .data = {"file_code": ..., "file_status": "OK"} on success."""
    server_result = await get_upload_server(key)
    if not server_result.ok:
        return server_result

    upload_url = server_result.data
    sess_id = (server_result.raw or {}).get("sess_id")
    if not upload_url or not sess_id:
        return DevUploadsResult.fail("DevUploads didn't return an upload URL/session.", raw=server_result.raw)

    fname = filename or os.path.basename(filepath)
    try:
        async with httpx.AsyncClient(timeout=None) as client:  # uploads can take a while; no artificial timeout
            with open(filepath, "rb") as f:
                resp = await client.post(
                    upload_url,
                    data={"sess_id": sess_id, "utype": "prem"},
                    files={"file": (fname, f)},
                )
    except httpx.HTTPError as e:
        return DevUploadsResult.fail(f"Network error uploading to DevUploads: {e}")
    except OSError as e:
        return DevUploadsResult.fail(f"Couldn't read the local file to upload: {e}")

    try:
        payload = resp.json()
    except ValueError:
        return DevUploadsResult.fail(f"DevUploads upload returned a non-JSON response (HTTP {resp.status_code}).")

    # The upload POST's response is a bare list, not the usual envelope:
    # [{"file_code": "...", "file_status": "OK"}]
    if isinstance(payload, list) and payload:
        entry = payload[0]
        if entry.get("file_status") == "OK" and entry.get("file_code"):
            return DevUploadsResult.success(entry, raw={"result": payload})
        return DevUploadsResult.fail(f"DevUploads rejected the upload: {entry}", raw={"result": payload})
    return DevUploadsResult.fail(f"Unexpected upload response: {payload}", raw={"result": payload})


async def upload_remote_url(key: str, url: str, folder: str = None) -> DevUploadsResult:
    """Starts an async remote-URL upload (DevUploads fetches the URL itself).
    Returns immediately with a "WORKING" status — poll
    check_remote_upload_status with the resulting file_code to see when
    it's done."""
    return await _get("upload/url", {"key": key, "url": url, "folder": folder})


async def check_remote_upload_status(key: str, file_code: str) -> DevUploadsResult:
    return await _get("upload/url", {"key": key, "file_code": file_code})


# ---------------- Download ----------------

async def file_direct_link(key: str, file_code: str) -> DevUploadsResult:
    return await _get("file/direct_link", {"key": key, "file_code": file_code})


# ---------------- File management ----------------

async def file_info(key: str, file_code: str) -> DevUploadsResult:
    return await _get("file/info", {"key": key, "file_code": file_code})


async def file_list(key: str, page: int = 1, per_page: int = 20, fld_id: str = None,
                     name: str = None) -> DevUploadsResult:
    return await _get("file/list", {"key": key, "page": page, "per_page": per_page,
                                     "fld_id": fld_id, "name": name})


async def file_rename(key: str, file_code: str, name: str) -> DevUploadsResult:
    return await _get("file/rename", {"key": key, "file_code": file_code, "name": name})


async def file_clone(key: str, file_code: str) -> DevUploadsResult:
    return await _get("file/clone", {"key": key, "file_code": file_code})


async def file_set_folder(key: str, file_code: str, fld_id: str) -> DevUploadsResult:
    return await _get("file/set_folder", {"key": key, "file_code": file_code, "fld_id": fld_id})


async def file_delete(key: str, file_code: str) -> DevUploadsResult:
    """See module docstring — unverified specifically for DevUploads, but
    the standard convention across this script family."""
    return await _get("file/delete", {"key": key, "file_code": file_code})


async def files_deleted(key: str) -> DevUploadsResult:
    return await _get("files/deleted", {"key": key})


# ---------------- Folder management ----------------

async def folder_list(key: str, fld_id: str = "0") -> DevUploadsResult:
    return await _get("folder/list", {"key": key, "fld_id": fld_id})


async def folder_create(key: str, name: str, parent_id: str = "0") -> DevUploadsResult:
    return await _get("folder/create", {"key": key, "name": name, "parent_id": parent_id})


async def folder_rename(key: str, fld_id: str, name: str) -> DevUploadsResult:
    return await _get("folder/rename", {"key": key, "fld_id": fld_id, "name": name})


async def folder_delete(key: str, fld_id: str) -> DevUploadsResult:
    """See module docstring — same caveat as file_delete."""
    return await _get("folder/delete", {"key": key, "fld_id": fld_id})
