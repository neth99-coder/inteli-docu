"use client";

import { PointerEvent, useEffect, useMemo, useRef, useState } from "react";
import { Highlighter, LoaderCircle, MessageSquarePlus, Pencil, Trash2 } from "lucide-react";
import { Document, Page, pdfjs } from "react-pdf";

import type { PageAnnotation } from "@/lib/types";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();

type PdfPagePreviewProps = {
  annotations: PageAnnotation[];
  fileUrl: string;
  isSavingAnnotations: boolean;
  onSaveAnnotations: (annotations: PageAnnotation[]) => Promise<void>;
  pageNumber: number;
};

type AnnotationMode = "browse" | "highlight" | "note";

type DraftHighlight = {
  originX: number;
  originY: number;
  x: number;
  y: number;
  width: number;
  height: number;
};

type PendingNote = {
  x: number;
  y: number;
  text: string;
};

const MIN_HIGHLIGHT_WIDTH = 0.015;
const MIN_HIGHLIGHT_HEIGHT = 0.006;
const MIN_HIGHLIGHT_AREA = 0.00018;

export function PdfPagePreview({
  annotations,
  fileUrl,
  isSavingAnnotations,
  onSaveAnnotations,
  pageNumber,
}: PdfPagePreviewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const pageStageRef = useRef<HTMLDivElement | null>(null);
  const annotationElementsRef = useRef(new Map<string, HTMLElement>());
  const focusResetTimerRef = useRef<number | null>(null);
  const [width, setWidth] = useState(0);
  const [isRendering, setIsRendering] = useState(true);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [mode, setMode] = useState<AnnotationMode>("browse");
  const [draftHighlight, setDraftHighlight] = useState<DraftHighlight | null>(null);
  const [pendingNote, setPendingNote] = useState<PendingNote | null>(null);
  const [activeNoteId, setActiveNoteId] = useState<string | null>(null);
  const [focusedAnnotationId, setFocusedAnnotationId] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) {
      return;
    }

    const updateWidth = () => {
      setWidth(element.clientWidth);
    };

    updateWidth();

    const observer = new ResizeObserver(updateWidth);
    observer.observe(element);

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    setIsRendering(true);
    setRenderError(null);
    setDraftHighlight(null);
    setPendingNote(null);
    setActiveNoteId(null);
    setMode("browse");
  }, [fileUrl, pageNumber]);

  useEffect(() => {
    return () => {
      if (focusResetTimerRef.current !== null) {
        window.clearTimeout(focusResetTimerRef.current);
      }
    };
  }, []);

  const noteAnnotations = useMemo(
    () => annotations.filter((annotation) => annotation.type === "note"),
    [annotations]
  );

  async function persistAnnotations(nextAnnotations: PageAnnotation[]) {
    setSaveError(null);

    try {
      await onSaveAnnotations(nextAnnotations);
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "Failed to save annotations.");
    }
  }

  function getRelativePoint(event: PointerEvent<HTMLDivElement>) {
    const rect = pageStageRef.current?.getBoundingClientRect();
    if (!rect) {
      return null;
    }

    const x = clamp((event.clientX - rect.left) / rect.width);
    const y = clamp((event.clientY - rect.top) / rect.height);
    return { x, y };
  }

  function handlePointerDown(event: PointerEvent<HTMLDivElement>) {
    if (mode !== "highlight") {
      return;
    }

    if (event.target !== event.currentTarget) {
      return;
    }

    const point = getRelativePoint(event);
    if (!point) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    setPendingNote(null);
    setActiveNoteId(null);
    setDraftHighlight({
      originX: point.x,
      originY: point.y,
      x: point.x,
      y: point.y,
      width: 0,
      height: 0,
    });
  }

  function handlePointerMove(event: PointerEvent<HTMLDivElement>) {
    if (mode !== "highlight" || !draftHighlight) {
      return;
    }

    const point = getRelativePoint(event);
    if (!point) {
      return;
    }

    const x = Math.min(draftHighlight.originX, point.x);
    const y = Math.min(draftHighlight.originY, point.y);
    const width = Math.abs(point.x - draftHighlight.originX);
    const height = Math.abs(point.y - draftHighlight.originY);

    setDraftHighlight({
      ...draftHighlight,
      x,
      y,
      width,
      height,
    });
  }

  async function handlePointerUp(event: PointerEvent<HTMLDivElement>) {
    if (mode !== "highlight" || !draftHighlight) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }

    const isLargeEnough =
      (draftHighlight.width >= MIN_HIGHLIGHT_WIDTH &&
        draftHighlight.height >= MIN_HIGHLIGHT_HEIGHT) ||
      draftHighlight.width * draftHighlight.height >= MIN_HIGHLIGHT_AREA;

    if (!isLargeEnough) {
      setDraftHighlight(null);
      return;
    }

    const nextAnnotation: PageAnnotation = {
      id: createAnnotationId(),
      type: "highlight",
      x: draftHighlight.x,
      y: draftHighlight.y,
      width: draftHighlight.width,
      height: draftHighlight.height,
      text: null,
      created_at: new Date().toISOString(),
    };

    setDraftHighlight(null);
    await persistAnnotations([...annotations, nextAnnotation]);
  }

  function handleLayerClick(event: PointerEvent<HTMLDivElement>) {
    if (mode !== "note") {
      return;
    }

    if (event.target !== event.currentTarget) {
      return;
    }

    const point = getRelativePoint(event);
    if (!point) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    setDraftHighlight(null);
    setActiveNoteId(null);
    setPendingNote({ x: point.x, y: point.y, text: "" });
  }

  async function handleSaveNote() {
    if (!pendingNote) {
      return;
    }

    const text = pendingNote.text.trim();
    if (!text) {
      setSaveError("Add note text before saving.");
      return;
    }

    const nextAnnotation: PageAnnotation = {
      id: createAnnotationId(),
      type: "note",
      x: pendingNote.x,
      y: pendingNote.y,
      width: 0.04,
      height: 0.04,
      text,
      created_at: new Date().toISOString(),
    };

    setPendingNote(null);
    await persistAnnotations([...annotations, nextAnnotation]);
    setActiveNoteId(nextAnnotation.id);
  }

  async function handleDeleteAnnotation(annotationId: string) {
    const nextAnnotations = annotations.filter((annotation) => annotation.id !== annotationId);
    setPendingNote(null);
    if (activeNoteId === annotationId) {
      setActiveNoteId(null);
    }
    await persistAnnotations(nextAnnotations);
  }

  function registerAnnotationElement(annotationId: string, element: HTMLElement | null) {
    if (!element) {
      annotationElementsRef.current.delete(annotationId);
      return;
    }

    annotationElementsRef.current.set(annotationId, element);
  }

  function focusAnnotation(annotation: PageAnnotation) {
    if (annotation.type === "note") {
      setActiveNoteId(annotation.id);
    } else {
      setActiveNoteId(null);
    }

    setMode("browse");
    setFocusedAnnotationId(annotation.id);

    if (focusResetTimerRef.current !== null) {
      window.clearTimeout(focusResetTimerRef.current);
    }

    focusResetTimerRef.current = window.setTimeout(() => {
      setFocusedAnnotationId((current) => (current === annotation.id ? null : current));
    }, 1800);

    window.requestAnimationFrame(() => {
      const target = annotationElementsRef.current.get(annotation.id);
      if (!target) {
        return;
      }

      target.scrollIntoView({
        behavior: "smooth",
        block: "center",
        inline: "center",
      });

      if (target instanceof HTMLButtonElement) {
        target.focus({ preventScroll: true });
      }
    });
  }

  return (
    <div className="pdf-preview-stack">
      <div className="annotation-toolbar">
        <div className="annotation-tool-group" role="tablist" aria-label="Annotation tools">
          <button
            className={`toolbar-chip ${mode === "browse" ? "active" : ""}`}
            onClick={() => setMode("browse")}
            type="button"
          >
            <Pencil size={14} />
            Browse
          </button>
          <button
            className={`toolbar-chip ${mode === "highlight" ? "active" : ""}`}
            onClick={() => setMode("highlight")}
            type="button"
          >
            <Highlighter size={14} />
            Highlight
          </button>
          <button
            className={`toolbar-chip ${mode === "note" ? "active" : ""}`}
            onClick={() => setMode("note")}
            type="button"
          >
            <MessageSquarePlus size={14} />
            Note
          </button>
        </div>

        <div className="annotation-toolbar-meta">
          <span>{annotations.length} saved</span>
          <span>{isSavingAnnotations ? "Saving..." : "Saved to page"}</span>
        </div>
      </div>

      <div className="pdf-renderer" ref={containerRef}>
        {isRendering ? (
          <div className="pdf-loading">
            <LoaderCircle size={18} className="spin" />
            <span>Loading page preview...</span>
          </div>
        ) : null}

        {renderError ? (
          <div className="empty-state">{renderError}</div>
        ) : width > 0 ? (
          <Document
            file={fileUrl}
            loading={null}
            onLoadError={() => {
              setRenderError("PDF preview is not available for this page yet.");
              setIsRendering(false);
            }}
            onSourceError={() => {
              setRenderError("PDF preview is not available for this page yet.");
              setIsRendering(false);
            }}
          >
            <div className="pdf-page">
              <div className="pdf-page-stage" ref={pageStageRef}>
                <Page
                  loading={null}
                  onRenderError={() => {
                    setRenderError("Failed to render this PDF page.");
                    setIsRendering(false);
                  }}
                  onRenderSuccess={() => setIsRendering(false)}
                  pageNumber={pageNumber}
                  renderAnnotationLayer={false}
                  renderTextLayer={false}
                  width={Math.max(width - 34, 320)}
                />

                <div
                  className={`annotation-layer annotation-mode-${mode}`}
                  onClick={handleLayerClick}
                  onPointerDown={handlePointerDown}
                  onPointerMove={handlePointerMove}
                  onPointerUp={(event) => {
                    void handlePointerUp(event);
                  }}
                >
                  {annotations.map((annotation) =>
                    annotation.type === "highlight" ? (
                      <div
                        className={`page-highlight ${focusedAnnotationId === annotation.id ? "focused" : ""}`}
                        ref={(element) => registerAnnotationElement(annotation.id, element)}
                        key={annotation.id}
                        style={toBoxStyle(annotation)}
                        title="Saved highlight"
                      />
                    ) : (
                      <button
                        className={`note-pin ${activeNoteId === annotation.id ? "active" : ""} ${focusedAnnotationId === annotation.id ? "focused" : ""}`}
                        key={annotation.id}
                        onClick={(event) => {
                          event.preventDefault();
                          event.stopPropagation();
                          setActiveNoteId((current) =>
                            current === annotation.id ? null : annotation.id
                          );
                        }}
                        ref={(element) => registerAnnotationElement(annotation.id, element)}
                        style={{
                          left: `${annotation.x * 100}%`,
                          top: `${annotation.y * 100}%`,
                        }}
                        type="button"
                      >
                        {noteAnnotations.findIndex((item) => item.id === annotation.id) + 1}
                      </button>
                    )
                  )}

                  {draftHighlight ? (
                    <div className="page-highlight draft" style={toBoxStyle(draftHighlight)} />
                  ) : null}

                  {annotations
                    .filter(
                      (annotation) => annotation.type === "note" && annotation.id === activeNoteId
                    )
                    .map((annotation) => (
                      <div
                        className="note-popover"
                        key={`${annotation.id}-popover`}
                        onClick={(event) => {
                          event.stopPropagation();
                        }}
                        onPointerDown={(event) => {
                          event.stopPropagation();
                        }}
                        style={{
                          left: `${annotation.x * 100}%`,
                          top: `${Math.min(annotation.y + 0.05, 0.92) * 100}%`,
                        }}
                      >
                        <div className="note-popover-head">
                          <span className="section-label">Note</span>
                          <button
                            className="note-delete"
                            onClick={(event) => {
                              event.preventDefault();
                              event.stopPropagation();
                              void handleDeleteAnnotation(annotation.id);
                            }}
                            type="button"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                        <p>{annotation.text}</p>
                      </div>
                    ))}

                  {pendingNote ? (
                    <div
                      className="note-composer"
                      onClick={(event) => {
                        event.stopPropagation();
                      }}
                      onPointerDown={(event) => {
                        event.stopPropagation();
                      }}
                      style={{
                        left: `${pendingNote.x * 100}%`,
                        top: `${Math.min(pendingNote.y + 0.05, 0.9) * 100}%`,
                      }}
                    >
                      <label className="section-label" htmlFor="note-textarea">
                        New note
                      </label>
                      <textarea
                        id="note-textarea"
                        onChange={(event) =>
                          setPendingNote((current) =>
                            current ? { ...current, text: event.target.value } : current
                          )
                        }
                        placeholder="Add context for this page area..."
                        rows={4}
                        value={pendingNote.text}
                      />
                      <div className="note-composer-actions">
                        <button
                          className="toolbar-chip"
                          onClick={(event) => {
                            event.preventDefault();
                            event.stopPropagation();
                            setPendingNote(null);
                          }}
                          type="button"
                        >
                          Cancel
                        </button>
                        <button
                          className="toolbar-chip active"
                          onClick={(event) => {
                            event.preventDefault();
                            event.stopPropagation();
                            void handleSaveNote();
                          }}
                          type="button"
                        >
                          Save note
                        </button>
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          </Document>
        ) : null}
      </div>

      <div className="annotation-panel">
        <div className="subpanel-head">
          <span className="section-label">Page annotations</span>
          <span className="muted">
            {mode === "highlight"
              ? "Drag on the page to mark an area."
              : mode === "note"
                ? "Click anywhere on the page to drop a note."
                : "Open saved notes or remove annotations."}
          </span>
        </div>

        {saveError ? <div className="error">{saveError}</div> : null}

        {annotations.length === 0 ? (
          <div className="annotation-empty">No highlights or notes saved for this page yet.</div>
        ) : (
          <div className="annotation-list">
            {annotations.map((annotation, index) => (
              <details
                className="annotation-card"
                key={annotation.id}
                open={annotation.type === "note" && activeNoteId === annotation.id}
                onClick={(event) => {
                  const target = event.target as HTMLElement;
                  if (target.closest(".note-delete")) {
                    return;
                  }

                  focusAnnotation(annotation);
                }}
                onToggle={(event) => {
                  const target = event.currentTarget;
                  if (annotation.type === "note") {
                    setActiveNoteId(target.open ? annotation.id : null);
                  }
                }}
              >
                <summary>
                  <span className="annotation-jump">
                    {annotation.type === "highlight"
                      ? `Highlight ${index + 1}`
                      : `Note ${noteAnnotations.findIndex((item) => item.id === annotation.id) + 1}`}
                  </span>
                  <button
                    className="note-delete"
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      void handleDeleteAnnotation(annotation.id);
                    }}
                    type="button"
                  >
                    <Trash2 size={14} />
                  </button>
                </summary>

                <div className="annotation-card-body">
                  {annotation.type === "highlight" ? (
                    <p>Saved highlight for a marked region on page {pageNumber}.</p>
                  ) : (
                    <p>{annotation.text}</p>
                  )}
                </div>
              </details>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function clamp(value: number) {
  return Math.max(0, Math.min(1, value));
}

function toBoxStyle(box: Pick<PageAnnotation, "x" | "y" | "width" | "height">) {
  return {
    left: `${box.x * 100}%`,
    top: `${box.y * 100}%`,
    width: `${box.width * 100}%`,
    height: `${box.height * 100}%`,
  };
}

function createAnnotationId() {
  return `annotation-${crypto.randomUUID()}`;
}
