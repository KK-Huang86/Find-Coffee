"""同步 SDD 文件（已封存 change 與現行 spec）至本機 AnythingLLM RAG 服務。

由 `.pre-commit-config.yaml` 的 `post-commit` stage hook 觸發。
"""

import logging
import re
import subprocess
from pathlib import Path

import requests
from decouple import config

logger = logging.getLogger(__name__)

API_KEY = config("ANYTHINGLLM_API_KEY", default="")
BASE_URL = config("ANYTHINGLLM_BASE_URL", default="http://localhost:3001")

REQUEST_TIMEOUT = 10

ARCHIVE_PREFIX = "openspec/changes/archive/"
CURRENT_SPEC_PATTERN = re.compile(r"^openspec/specs/.+/spec\.md$")

ARCHIVED_DECISIONS_SLUG = "sdd-archived-decisions"
CURRENT_SPECS_SLUG = "sdd-current-specs"


def _is_archived_change_file(path: str) -> bool:
    return path.startswith(ARCHIVE_PREFIX)


def _is_current_spec_file(path: str) -> bool:
    return bool(CURRENT_SPEC_PATTERN.match(path))


def filter_target_files(paths: list[str]) -> list[str]:
    return [p for p in paths if _is_archived_change_file(p) or _is_current_spec_file(p)]


def workspace_slug_for(path: str) -> str:
    if _is_archived_change_file(path):
        return ARCHIVED_DECISIONS_SLUG
    if _is_current_spec_file(path):
        return CURRENT_SPECS_SLUG
    raise ValueError(f"path is not a RAG ingestion target: {path}")


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {API_KEY}"}


def _api_url(path: str) -> str:
    return f"{BASE_URL.rstrip('/')}/api{path}"


def _iter_document_entries(node: dict) -> list[dict]:
    """AnythingLLM 的 `GET /v1/documents` 以 `localFiles` 巢狀資料夾樹回傳文件，
    而非扁平陣列，需遞迴走訪每個 folder 的 `items` 找出實際文件節點。"""
    entries = []
    for item in node.get("items", []) or []:
        if item.get("type") == "folder":
            entries.extend(_iter_document_entries(item))
        else:
            entries.append(item)
    return entries


def find_existing_document(title: str) -> str | None:
    response = requests.get(
        _api_url("/v1/documents"), headers=_auth_headers(), timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
    root = response.json().get("localFiles", {})
    for document in _iter_document_entries(root):
        if document.get("title") == title:
            return document.get("name")
    return None


def remove_document(name: str) -> None:
    response = requests.delete(
        _api_url("/v1/system/remove-documents"),
        headers=_auth_headers(),
        json={"names": [name]},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()


def upload_document(path: str, slug: str, content: str | None = None) -> None:
    if content is None:
        content = Path(path).read_text(encoding="utf-8")
    response = requests.post(
        _api_url("/v1/document/raw-text"),
        headers=_auth_headers(),
        json={
            "textContent": content,
            "metadata": {"title": path},
            "addToWorkspaces": slug,
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()


def ingest_file(path: str) -> None:
    slug = workspace_slug_for(path)
    existing_name = find_existing_document(path)
    if existing_name is not None:
        remove_document(existing_name)
    upload_document(path, slug)


def get_changed_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def main() -> None:
    try:
        changed_files = get_changed_files()
    except Exception:
        logger.exception("rag_ingest: failed to read changed files for HEAD")
        return

    target_files = filter_target_files(changed_files)
    for path in target_files:
        try:
            ingest_file(path)
        except Exception:
            logger.exception("rag_ingest: failed to ingest %s", path)


if __name__ == "__main__":
    main()
