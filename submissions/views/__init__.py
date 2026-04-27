from .submissions import (
    SubmissionListView,
    SubmissionCreateView,
    SubmissionDetailView,
    submission_quick_create,
    submission_quick_update,
    submission_quick_delete,
)
from .documents import (
    DocumentCreateView,
    DocumentUpdateView,
    DocumentDeleteView,
    DocumentDownloadView,
)
from .api import (
    submission_api,
    submission_detail_api,
    document_api,
    document_detail_api,
    SubmissionApiView,
    SubmissionDetailApiView,
    DocumentApiView,
    DocumentDetailApiView,
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
