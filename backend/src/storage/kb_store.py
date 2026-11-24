from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from src.config.settings import category_to_department
from src.schemas.chunk import DLQRecord
from src.schemas.document import DocumentFormat, MetadataAttributes, MetadataSidecar

SUPPORTED_EXTENSIONS: dict[str, DocumentFormat] = {
    ".pdf": "PDF",
    ".docx": "DOCX",
    ".md": "MD",
    ".markdown": "MD",
    ".txt": "TXT",
}


class SidecarValidationError(ValueError):
    """Raised when a staged KB file lacks a valid `.metadata.json` sidecar."""


def sanitize_filename(filename: str) -> str:
    base = Path(filename).name.strip()
    if not base:
        return "document.txt"
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base)
    return cleaned or "document.txt"


def detect_format(filename: str) -> DocumentFormat:
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS.keys()))
        raise ValueError(f"Unsupported file format '{ext}'. Supported: {supported}")
    return SUPPORTED_EXTENSIONS[ext]


def compute_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def format_size_label(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{round(size_bytes / 1024)} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def derive_title(filename: str) -> str:
    stem = Path(filename).stem
    pretty = re.sub(r"[-_]+", " ", stem).strip()
    if not pretty:
        return filename
    return pretty[0].upper() + pretty[1:]


class KnowledgeBaseStore:
    """Manages hierarchical source document staging, `.metadata.json` sidecars, and DLQ logs."""

    def __init__(self, storage_dir: Path, max_file_size_mb: int = 50) -> None:
        self.storage_dir = Path(storage_dir)
        self.kb_dir = self.storage_dir / "knowledge_base"
        self.dlq_dir = self.storage_dir / "dlq"
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        self.dlq_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def sidecar_path_for(file_path: Path) -> Path:
        return Path(f"{file_path}.metadata.json")

    def stage_document(
        self,
        *,
        filename: str,
        content: bytes,
        category: str,
        tenant_id: str,
        department: str | None = None,
        access_groups: list[str] | None = None,
        document_id: str | None = None,
        title: str | None = None,
        version: int = 1,
    ) -> tuple[Path, Path, MetadataSidecar]:
        """Phase 1: Save source file under `{tenant}/{department}/{doc_id}/` and write sidecar."""
        if not content:
            raise ValueError("Uploaded file is empty.")
        if len(content) > self.max_file_size_bytes:
            raise ValueError(
                f"File size ({len(content)} bytes) exceeds limit of {self.max_file_size_bytes} bytes."
            )

        safe_name = sanitize_filename(filename)
        fmt = detect_format(safe_name)
        dept = (department or category_to_department(category)).strip()
        tenant = tenant_id.strip()
        if not tenant or not dept:
            raise ValueError("Both tenant_id and department are required.")

        content_hash = compute_sha256(content)
        doc_id = document_id or f"doc-{uuid.uuid4().hex[:12]}"
        groups = sorted({g.strip() for g in (access_groups or [dept, "admin"]) if g.strip()})
        doc_title = (title or derive_title(safe_name)).strip()

        doc_dir = self.kb_dir / tenant / dept / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        file_path = doc_dir / safe_name
        sidecar_path = self.sidecar_path_for(file_path)

        # Write source document first
        file_path.write_bytes(content)

        sidecar = MetadataSidecar(
            metadataAttributes=MetadataAttributes(
                tenant_id=tenant,
                department=dept,
                category=category.strip(),
                access_groups=groups,
                document_id=doc_id,
                title=doc_title,
                format=fmt,
                content_hash=content_hash,
                version=version,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
        )

        # Write sidecar atomically via temp file
        tmp_sidecar = sidecar_path.with_suffix(".json.tmp")
        tmp_sidecar.write_text(
            json.dumps(sidecar.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_sidecar.replace(sidecar_path)

        return file_path, sidecar_path, sidecar

    def validate_sidecar(self, file_path: Path) -> MetadataSidecar:
        """Phase 2 Fail-Closed Safeguard: validate `.metadata.json` exists and matches KB prefix."""
        file_path = Path(file_path)
        if not file_path.exists() or not file_path.is_file():
            raise SidecarValidationError(f"Source file does not exist: {file_path}")

        sidecar_path = self.sidecar_path_for(file_path)
        if not sidecar_path.exists():
            raise SidecarValidationError(
                f"Missing required metadata sidecar '{sidecar_path.name}' for '{file_path.name}'."
            )

        try:
            raw_json = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SidecarValidationError(
                f"Invalid JSON in metadata sidecar '{sidecar_path.name}': {exc}"
            ) from exc

        try:
            sidecar = MetadataSidecar.model_validate(raw_json)
        except ValidationError as exc:
            raise SidecarValidationError(
                f"Sidecar schema validation failed for '{sidecar_path.name}': {exc}"
            ) from exc

        # Enforce folder prefix alignment: kb_dir/{tenant}/{department}/{doc_id}/{filename}
        try:
            rel_parts = file_path.resolve().relative_to(self.kb_dir.resolve()).parts
        except ValueError:
            rel_parts = ()

        if len(rel_parts) >= 4:
            folder_tenant, folder_dept = rel_parts[0], rel_parts[1]
            attrs = sidecar.metadataAttributes
            if folder_tenant != attrs.tenant_id:
                raise SidecarValidationError(
                    f"Tenant mismatch: folder '{folder_tenant}' != sidecar '{attrs.tenant_id}'."
                )
            if folder_dept != attrs.department:
                raise SidecarValidationError(
                    f"Department mismatch: folder '{folder_dept}' != sidecar '{attrs.department}'."
                )

        return sidecar

    def scan_knowledge_base(self) -> list[Path]:
        """List all non-sidecar source files in the knowledge base directory."""
        files: list[Path] = []
        if not self.kb_dir.exists():
            return files
        for path in sorted(self.kb_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.name.endswith(".metadata.json") or path.name.endswith(".tmp"):
                continue
            files.append(path)
        return files

    def write_dlq_file(self, record: DLQRecord) -> Path:
        """Persist failed ingestion / safeguard diagnostics to `storage/dlq/`."""
        self.dlq_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.dlq_dir / f"{record.dlq_id}.json"
        out_path.write_text(
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return out_path

    def delete_document_files(self, storage_path: str | Path, sidecar_path: str | Path | None = None) -> None:
        """Remove staged source file, sidecar, and empty parent directories."""
        src = Path(storage_path) if storage_path else None
        sidecar = Path(sidecar_path) if sidecar_path else (self.sidecar_path_for(src) if src else None)

        if sidecar and sidecar.exists():
            sidecar.unlink(missing_ok=True)
        if src and src.exists():
            parent = src.parent
            src.unlink(missing_ok=True)
            if parent.exists() and parent != self.kb_dir and not any(parent.iterdir()):
                shutil.rmtree(parent, ignore_errors=True)
