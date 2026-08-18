from unittest.mock import MagicMock, call, patch

import pytest
import requests

from scripts import rag_ingest


# --- Requirement 1: 依 commit 內容判斷是否觸發匯入 -------------------------


def test_filter_target_files_includes_archived_change_files():
    paths = ["openspec/changes/archive/2026-01-01-foo/proposal.md"]

    assert rag_ingest.filter_target_files(paths) == paths


def test_filter_target_files_includes_current_spec_files():
    paths = ["openspec/specs/cafe-search/spec.md"]

    assert rag_ingest.filter_target_files(paths) == paths


def test_filter_target_files_excludes_unrelated_files():
    paths = [
        "cafe/models.py",
        "openspec/changes/add-spec-to-rag/proposal.md",
        "openspec/specs/cafe-search/design.md",
        "README.md",
    ]

    assert rag_ingest.filter_target_files(paths) == []


def test_filter_target_files_empty_input_returns_empty():
    assert rag_ingest.filter_target_files([]) == []


def test_filter_target_files_mixed_returns_only_relevant():
    paths = [
        "cafe/models.py",
        "openspec/changes/archive/2026-01-01-foo/design.md",
        "openspec/specs/cafe-search/spec.md",
    ]

    assert rag_ingest.filter_target_files(paths) == [
        "openspec/changes/archive/2026-01-01-foo/design.md",
        "openspec/specs/cafe-search/spec.md",
    ]


# --- Requirement 2: 匯入內容依來源路徑分流至對應 RAG workspace --------------


def test_workspace_slug_for_archived_change_file():
    path = "openspec/changes/archive/2026-01-01-foo/proposal.md"

    assert rag_ingest.workspace_slug_for(path) == "sdd-archived-decisions"


def test_workspace_slug_for_current_spec_file():
    path = "openspec/specs/cafe-search/spec.md"

    assert rag_ingest.workspace_slug_for(path) == "sdd-current-specs"


def test_workspace_slug_for_unrelated_path_raises():
    with pytest.raises(ValueError):
        rag_ingest.workspace_slug_for("cafe/models.py")


# --- Requirement 3: 匯入前需避免重複或過期版本殘留 --------------------------


def test_find_existing_document_returns_name_when_title_matches():
    # AnythingLLM 的 GET /v1/documents 以 localFiles 巢狀資料夾樹回傳（實測 docker exec
    # openapi.json 確認 base path 為 /api，且回應非扁平 documents 陣列而是巢狀 folder tree）。
    response = MagicMock()
    response.json.return_value = {
        "localFiles": {
            "name": "documents",
            "type": "folder",
            "items": [
                {
                    "name": "custom-documents",
                    "type": "folder",
                    "items": [
                        {
                            "name": "other-doc-uuid.json",
                            "type": "file",
                            "title": "openspec/specs/other/spec.md",
                        },
                        {
                            "name": "target-doc-uuid.json",
                            "type": "file",
                            "title": "openspec/specs/cafe-search/spec.md",
                        },
                    ],
                }
            ],
        }
    }
    response.raise_for_status.return_value = None

    with patch.object(rag_ingest.requests, "get", return_value=response) as mock_get:
        result = rag_ingest.find_existing_document("openspec/specs/cafe-search/spec.md")

    assert result == "target-doc-uuid.json"
    mock_get.assert_called_once()
    args, kwargs = mock_get.call_args
    assert args[0] == "http://localhost:3001/api/v1/documents"
    assert kwargs["timeout"] == rag_ingest.REQUEST_TIMEOUT


def test_find_existing_document_returns_none_when_no_match():
    response = MagicMock()
    response.json.return_value = {
        "localFiles": {
            "name": "documents",
            "type": "folder",
            "items": [
                {
                    "name": "other-doc-uuid.json",
                    "type": "file",
                    "title": "openspec/specs/other/spec.md",
                },
            ],
        }
    }
    response.raise_for_status.return_value = None

    with patch.object(rag_ingest.requests, "get", return_value=response):
        result = rag_ingest.find_existing_document("openspec/specs/cafe-search/spec.md")

    assert result is None


def test_find_existing_document_empty_document_list_returns_none():
    response = MagicMock()
    response.json.return_value = {
        "localFiles": {"name": "documents", "type": "folder", "items": []}
    }
    response.raise_for_status.return_value = None

    with patch.object(rag_ingest.requests, "get", return_value=response):
        result = rag_ingest.find_existing_document("openspec/specs/cafe-search/spec.md")

    assert result is None


def test_ingest_file_removes_existing_before_upload():
    with (
        patch.object(rag_ingest, "find_existing_document", return_value="old-doc-uuid.json") as mock_find,
        patch.object(rag_ingest, "remove_document") as mock_remove,
        patch.object(rag_ingest, "upload_document") as mock_upload,
    ):
        rag_ingest.ingest_file("openspec/specs/cafe-search/spec.md")

    mock_find.assert_called_once_with("openspec/specs/cafe-search/spec.md")
    mock_remove.assert_called_once_with("old-doc-uuid.json")
    mock_upload.assert_called_once_with(
        "openspec/specs/cafe-search/spec.md", "sdd-current-specs"
    )


def test_ingest_file_uploads_directly_when_no_existing_document():
    with (
        patch.object(rag_ingest, "find_existing_document", return_value=None),
        patch.object(rag_ingest, "remove_document") as mock_remove,
        patch.object(rag_ingest, "upload_document") as mock_upload,
    ):
        rag_ingest.ingest_file("openspec/specs/cafe-search/spec.md")

    mock_remove.assert_not_called()
    mock_upload.assert_called_once_with(
        "openspec/specs/cafe-search/spec.md", "sdd-current-specs"
    )


def test_upload_document_sends_correct_payload(tmp_path, monkeypatch):
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("# Some Spec Content", encoding="utf-8")

    response = MagicMock()
    response.raise_for_status.return_value = None

    with patch.object(rag_ingest.requests, "post", return_value=response) as mock_post:
        rag_ingest.upload_document(str(spec_file), "sdd-current-specs", content="# Some Spec Content")

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "http://localhost:3001/api/v1/document/raw-text"
    assert kwargs["json"]["textContent"] == "# Some Spec Content"
    assert kwargs["json"]["metadata"]["title"] == str(spec_file)
    assert kwargs["json"]["addToWorkspaces"] == "sdd-current-specs"
    assert kwargs["timeout"] == rag_ingest.REQUEST_TIMEOUT


def test_remove_document_calls_correct_url_with_timeout():
    response = MagicMock()
    response.raise_for_status.return_value = None

    with patch.object(rag_ingest.requests, "delete", return_value=response) as mock_delete:
        rag_ingest.remove_document("target-doc-uuid.json")

    mock_delete.assert_called_once()
    args, kwargs = mock_delete.call_args
    assert args[0] == "http://localhost:3001/api/v1/system/remove-documents"
    assert kwargs["json"] == {"names": ["target-doc-uuid.json"]}
    assert kwargs["timeout"] == rag_ingest.REQUEST_TIMEOUT


# --- Requirement 4: RAG 服務無法連線或匯入失敗不得阻斷 commit --------------


def test_main_does_not_call_requests_when_no_relevant_files_changed():
    with (
        patch.object(rag_ingest, "get_changed_files", return_value=["cafe/models.py"]),
        patch.object(rag_ingest.requests, "get") as mock_get,
        patch.object(rag_ingest.requests, "post") as mock_post,
        patch.object(rag_ingest.requests, "delete") as mock_delete,
    ):
        rag_ingest.main()

    mock_get.assert_not_called()
    mock_post.assert_not_called()
    mock_delete.assert_not_called()


def test_main_catches_connection_error_and_returns_normally():
    with (
        patch.object(
            rag_ingest,
            "get_changed_files",
            return_value=["openspec/specs/cafe-search/spec.md"],
        ),
        patch.object(
            rag_ingest,
            "ingest_file",
            side_effect=requests.exceptions.ConnectionError("RAG offline"),
        ),
    ):
        result = rag_ingest.main()

    assert result is None


def test_main_catches_api_error_and_returns_normally():
    with (
        patch.object(
            rag_ingest,
            "get_changed_files",
            return_value=["openspec/specs/cafe-search/spec.md"],
        ),
        patch.object(
            rag_ingest,
            "ingest_file",
            side_effect=requests.exceptions.HTTPError("500 Server Error"),
        ),
    ):
        result = rag_ingest.main()

    assert result is None


def test_main_one_file_failure_does_not_block_other_files():
    with (
        patch.object(
            rag_ingest,
            "get_changed_files",
            return_value=[
                "openspec/specs/cafe-search/spec.md",
                "openspec/specs/favorite/spec.md",
            ],
        ),
        patch.object(
            rag_ingest,
            "ingest_file",
            side_effect=[requests.exceptions.HTTPError("500 Server Error"), None],
        ) as mock_ingest,
    ):
        rag_ingest.main()

    assert mock_ingest.call_args_list == [
        call("openspec/specs/cafe-search/spec.md"),
        call("openspec/specs/favorite/spec.md"),
    ]
