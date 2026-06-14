from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from clients.models import Client, Document, TestRun, TestScenarioResult


@dataclass
class RelatedObjects:
    client: Client | None = None
    document: Document | None = None
    case_identifier: str = ""
    onboarding_token: str = ""


class ScenarioRecorder:
    def __init__(self, test_run: TestRun) -> None:
        self.test_run = test_run

    def check(
        self,
        scenario_name: str,
        passed: bool,
        *,
        expected: Any = "",
        actual: Any = "",
        error_message: str = "",
        related: RelatedObjects | None = None,
    ) -> TestScenarioResult:
        related = related or RelatedObjects()
        related_case_identifier = related.case_identifier
        if related.onboarding_token and related.client and related.client.is_test_data:
            related_case_identifier = f"onboarding:{related.onboarding_token}"

        return TestScenarioResult.objects.create(
            test_run=self.test_run,
            scenario_name=scenario_name,
            status=(
                TestScenarioResult.STATUS_PASSED
                if passed
                else TestScenarioResult.STATUS_FAILED
            ),
            expected_result=str(expected),
            actual_result=str(actual),
            error_message="" if passed else str(error_message or actual),
            related_client=related.client,
            related_case_identifier=related_case_identifier,
            related_document=related.document,
            is_test_data=True,
        )

    def skip(
        self,
        scenario_name: str,
        *,
        expected: Any = "",
        actual: Any = "",
        reason: str = "",
        related: RelatedObjects | None = None,
    ) -> TestScenarioResult:
        related = related or RelatedObjects()
        related_case_identifier = related.case_identifier
        if related.onboarding_token and related.client and related.client.is_test_data:
            related_case_identifier = f"onboarding:{related.onboarding_token}"

        return TestScenarioResult.objects.create(
            test_run=self.test_run,
            scenario_name=scenario_name,
            status=TestScenarioResult.STATUS_SKIPPED,
            expected_result=str(expected),
            actual_result=str(actual),
            error_message=str(reason),
            related_client=related.client,
            related_case_identifier=related_case_identifier,
            related_document=related.document,
            is_test_data=True,
        )
