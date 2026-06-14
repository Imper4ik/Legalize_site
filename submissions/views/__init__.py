from .api import (
    DocumentApiView,
    DocumentDetailApiView,
    SubmissionApiView,
    SubmissionDetailApiView,
    document_api,
    document_detail_api,
    submission_api,
    submission_detail_api,
)
from .documents import (
    DocumentCreateView,
    DocumentDeleteView,
    DocumentDownloadView,
    DocumentUpdateView,
)
from .submissions import (
    SubmissionCreateView,
    SubmissionDetailView,
    SubmissionListView,
    submission_quick_create,
    submission_quick_delete,
    submission_quick_update,
)

__all__ = [
    "SubmissionListView",
    "SubmissionCreateView",
    "SubmissionDetailView",
    "submission_quick_create",
    "submission_quick_update",
    "submission_quick_delete",
    "DocumentCreateView",
    "DocumentUpdateView",
    "DocumentDeleteView",
    "DocumentDownloadView",
    "submission_api",
    "submission_detail_api",
    "document_api",
    "document_detail_api",
    "SubmissionApiView",
    "SubmissionDetailApiView",
    "DocumentApiView",
    "DocumentDetailApiView",
]
