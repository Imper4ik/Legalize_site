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
