from typing import Any


class ChunkingService:
    def chunk_elements(self, elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []

        for index, element in enumerate(elements):
            metadata = dict(element.get("metadata") or {})
            element_types = metadata.get("element_types") or []
            chunks.append(
                {
                    "chunk_index": index,
                    "content": element.get("text", "").strip(),
                    "page_number": element.get("page_number"),
                    "section_title": element.get("section_title"),
                    "has_image": "Image" in element_types,
                    "has_table": "Table" in element_types,
                    "image_summary": None,
                    "table_summary": None,
                    "metadata": metadata,
                }
            )

        return [chunk for chunk in chunks if chunk["content"]]

