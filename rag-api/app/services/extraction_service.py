from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from llama_parse import LlamaParse
from unstructured.chunking.title import chunk_by_title
from unstructured.documents.elements import Element
from unstructured.partition.pdf import partition_pdf

from app.config import get_settings


class ExtractionService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def extract(self, file_path: Path, file_type: str) -> list[dict[str, Any]]:
        normalized_type = file_type.lower()

        if normalized_type == "application/pdf":
            return self._extract_pdf(file_path)
        if normalized_type in {
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }:
            return self._extract_office(file_path)

        raise ValueError(f"Unsupported file type: {file_type}")

    def _extract_pdf(self, file_path: Path) -> list[dict[str, Any]]:
        if self.settings.unstructured_api_key:
            elements = self._extract_pdf_via_unstructured_api(file_path)
        else:
            elements = self._extract_pdf_locally(file_path)

        return [self._normalize_unstructured_element(element) for element in elements]

    def _extract_office(self, file_path: Path) -> list[dict[str, Any]]:
        if not self.settings.llama_parse_api_key:
            raise RuntimeError("LLAMA_PARSE_API_KEY is required for XLSX and PPTX parsing.")

        parser = LlamaParse(
            api_key=self.settings.llama_parse_api_key,
            result_type="markdown",
            verbose=False,
        )
        documents = parser.load_data(str(file_path))

        elements: list[dict[str, Any]] = []
        for index, document in enumerate(documents):
            text = getattr(document, "text", "") or ""
            if not text.strip():
                continue

            metadata = dict(getattr(document, "metadata", {}) or {})
            elements.extend(self._markdown_to_elements(text=text, base_metadata=metadata, default_page=index + 1))

        if not elements:
            raise RuntimeError("LlamaParse returned no readable content.")

        return elements

    def _extract_pdf_locally(self, file_path: Path) -> list[Element]:
        elements = partition_pdf(
            filename=str(file_path),
            strategy="hi_res",
            infer_table_structure=True,
            include_page_breaks=False,
        )
        return chunk_by_title(
            elements,
            combine_text_under_n_chars=0,
            max_characters=1600,
            new_after_n_chars=1200,
        )

    def _extract_pdf_via_unstructured_api(self, file_path: Path) -> list[dict[str, Any]]:
        with file_path.open("rb") as uploaded_file:
            response = httpx.post(
                self.settings.unstructured_api_url,
                headers={"unstructured-api-key": self.settings.unstructured_api_key or ""},
                data={
                    "strategy": "hi_res",
                    "chunking_strategy": "by_title",
                    "include_page_breaks": "false",
                    "infer_table_structure": "true",
                },
                files={"files": (file_path.name, uploaded_file, "application/pdf")},
                timeout=120,
            )

        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("Unexpected Unstructured response payload.")
        return payload

    def _normalize_unstructured_element(self, element: Element | dict[str, Any]) -> dict[str, Any]:
        if isinstance(element, dict):
            metadata = dict(element.get("metadata") or {})
            element_types = self._extract_element_types(metadata, fallback=element.get("type"))
            page_number = metadata.get("page_number")
            return {
                "page_number": page_number if isinstance(page_number, int) else None,
                "section_title": metadata.get("section_title") or metadata.get("category_depth"),
                "text": (element.get("text") or "").strip(),
                "metadata": {
                    **metadata,
                    "source": "unstructured_api",
                    "strategy": "by_title",
                    "element_types": element_types,
                },
            }

        metadata_obj = getattr(element, "metadata", None)
        metadata = metadata_obj.to_dict() if metadata_obj and hasattr(metadata_obj, "to_dict") else {}
        element_type = getattr(element, "category", None) or element.__class__.__name__
        page_number = metadata.get("page_number")

        return {
            "page_number": page_number if isinstance(page_number, int) else None,
            "section_title": metadata.get("section_title") or metadata.get("filename"),
            "text": getattr(element, "text", "").strip(),
            "metadata": {
                **metadata,
                "source": "unstructured_local",
                "strategy": "by_title",
                "element_types": self._extract_element_types(metadata, fallback=element_type),
            },
        }

    def _markdown_to_elements(
        self,
        *,
        text: str,
        base_metadata: dict[str, Any],
        default_page: int,
    ) -> list[dict[str, Any]]:
        elements: list[dict[str, Any]] = []
        current_title = "Imported content"
        current_lines: list[str] = []
        chunk_index = 0

        def flush() -> None:
            nonlocal chunk_index
            content = "\n".join(current_lines).strip()
            if not content:
                return

            page_number = base_metadata.get("page_number", default_page)
            elements.append(
                {
                    "page_number": page_number if isinstance(page_number, int) else default_page,
                    "section_title": current_title,
                    "text": content,
                    "metadata": {
                        **base_metadata,
                        "source": "llama_parse",
                        "strategy": "markdown_sections",
                        "element_types": ["CompositeElement"],
                        "chunk_index": chunk_index,
                    },
                }
            )
            chunk_index += 1

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line.startswith("#"):
                flush()
                current_lines = []
                current_title = line.lstrip("#").strip() or current_title
                continue
            current_lines.append(raw_line)

        flush()
        return elements

    def _extract_element_types(self, metadata: dict[str, Any], fallback: str | None) -> list[str]:
        element_types = metadata.get("element_types")
        if isinstance(element_types, list) and element_types:
            return [str(item) for item in element_types]
        if isinstance(fallback, str) and fallback:
            return [fallback]
        return ["CompositeElement"]
