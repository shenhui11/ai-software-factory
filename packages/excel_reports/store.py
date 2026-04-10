from __future__ import annotations

from itertools import count

from packages.excel_reports.models import AuditLog, ProcessingJob, ProcessingLog, ReportRecord, UploadRecord


class InMemoryStore:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.uploads: dict[str, UploadRecord] = {}
        self.jobs: dict[str, ProcessingJob] = {}
        self.reports: dict[str, ReportRecord] = {}
        self.audit_logs: list[AuditLog] = []
        self.processing_logs: list[ProcessingLog] = []
        self.objects: dict[str, bytes] = {}
        self._upload_ids = count(1)
        self._job_ids = count(1)
        self._report_ids = count(1)

    def next_upload_id(self) -> str:
        return f"upl_{next(self._upload_ids):03d}"

    def next_job_id(self) -> str:
        return f"job_{next(self._job_ids):03d}"

    def next_report_id(self) -> str:
        return f"rpt_{next(self._report_ids):03d}"


STORE = InMemoryStore()


def get_store() -> InMemoryStore:
    return STORE


def reset_store() -> None:
    STORE.reset()
