from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from django.utils.crypto import get_random_string
from django.utils.text import slugify

from clients.models import DocumentRequirement


@dataclass(frozen=True)
class DocumentRequirementScenarioResult:
    purpose: str
    requirement: DocumentRequirement | None = None
    selected_codes: tuple[str, ...] = field(default_factory=tuple)
    updated_count: int = 0
    deleted_requirement_id: int | None = None
    requirement_name: str = ""


def build_document_requirement_code(*, purpose: str | None, name: str) -> str:
    slug = slugify(name, allow_unicode=True).replace("-", "_")
    if not slug:
        slug = f"custom_doc_{get_random_string(5)}"

    candidate = slug
    while DocumentRequirement.objects.filter(application_purpose=purpose, document_type=candidate).exists():
        candidate = f"{slug}_{get_random_string(4)}"
    return candidate


def create_document_requirement_for_purpose(
    *,
    purpose: str | None,
    name: str,
    slug: str | None = None,
) -> DocumentRequirementScenarioResult:
    requirement = DocumentRequirement.objects.create(
        application_purpose=purpose,
        document_type=slug or build_document_requirement_code(purpose=purpose, name=name),
        custom_name=name,
        is_required=True,
        position=DocumentRequirement.objects.filter(application_purpose=purpose).count(),
    )
    return DocumentRequirementScenarioResult(
        purpose=purpose or "",
        requirement=requirement,
        requirement_name=requirement.custom_name or requirement.document_type,
    )


def update_document_requirement_record(
    *,
    requirement: DocumentRequirement,
    cleaned_data: Mapping[str, object],
) -> DocumentRequirementScenarioResult:
    for field in ("custom_name", "custom_name_pl", "custom_name_en", "custom_name_ru", "is_required"):
        if field in cleaned_data:
            setattr(requirement, field, cleaned_data[field])

    if requirement.custom_name:
        for lang_field in ("custom_name_pl", "custom_name_en", "custom_name_ru"):
            if not getattr(requirement, lang_field):
                setattr(requirement, lang_field, requirement.custom_name)

    requirement.save()
    return DocumentRequirementScenarioResult(
        purpose=requirement.application_purpose,
        requirement=requirement,
        requirement_name=requirement.custom_name or requirement.document_type,
    )


def delete_document_requirement_record(
    *,
    requirement: DocumentRequirement,
) -> DocumentRequirementScenarioResult:
    purpose = requirement.application_purpose
    requirement_id = requirement.pk
    requirement_name = requirement.custom_name or requirement.document_type.replace("_", " ").capitalize()
    requirement.delete()
    return DocumentRequirementScenarioResult(
        purpose=purpose,
        deleted_requirement_id=requirement_id,
        requirement_name=requirement_name,
    )


def sync_document_checklist_for_purpose(
    *,
    purpose: str | None,
    selected_codes: Sequence[str],
) -> DocumentRequirementScenarioResult:
    if purpose is None:
        return DocumentRequirementScenarioResult(purpose="", updated_count=0)

    selected_codes = list(selected_codes)
    selected_positions = {code: pos for pos, code in enumerate(selected_codes)}
    existing = {
        requirement.document_type: requirement
        for requirement in DocumentRequirement.objects.filter(application_purpose=purpose)
    }

    for code in selected_codes:
        if code in existing:
            requirement = existing[code]
            requirement.is_required = True
            requirement.position = selected_positions.get(code, requirement.position)
            requirement.save(update_fields=["is_required", "position"])
        else:
            DocumentRequirement.objects.create(
                application_purpose=purpose,
                document_type=code,
                is_required=True,
                position=selected_positions.get(code, 0),
            )

    for requirement in existing.values():
        if requirement.document_type not in selected_positions and requirement.is_required:
            requirement.is_required = False
            requirement.save(update_fields=["is_required"])

    return DocumentRequirementScenarioResult(
        purpose=purpose,
        selected_codes=tuple(selected_codes),
        updated_count=len(selected_codes),
    )
