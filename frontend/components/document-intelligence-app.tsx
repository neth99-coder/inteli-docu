"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  FileText,
  LoaderCircle,
  MessageSquare,
  RotateCcw,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";

import { apiFetch } from "@/lib/api";
import type {
  DocumentListItem,
  PageAnnotation,
  PageDetail,
  PageListItem,
  UploadResponse,
} from "@/lib/types";

const PdfPagePreview = dynamic(
  () => import("@/components/pdf-page-preview").then((module) => module.PdfPagePreview),
  { ssr: false }
);

const SUMMARY_POLL_INTERVAL_MS = 2000;
const SUMMARY_POLL_ATTEMPTS = 8;

export function DocumentIntelligenceApp() {
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [pages, setPages] = useState<PageListItem[]>([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [documentFileUrl, setDocumentFileUrl] = useState<string | null>(null);
  const [pageDetail, setPageDetail] = useState<PageDetail | null>(null);
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [isLoadingPage, setIsLoadingPage] = useState(false);
  const [isDeletingDocument, setIsDeletingDocument] = useState(false);
  const [isSavingAnnotations, setIsSavingAnnotations] = useState(false);
  const [isRegeneratingSummary, setIsRegeneratingSummary] = useState(false);
  const [pageQuestion, setPageQuestion] = useState("");
  const [pageAnswer, setPageAnswer] = useState<string | null>(null);
  const [isAskingQuestion, setIsAskingQuestion] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selectedPageIdRef = useRef<string | null>(null);
  const selectedDocument = documents.find((document) => document.id === selectedDocumentId) ?? null;
  const selectedPageIndex = pages.findIndex((page) => page.id === selectedPageId);
  const selectedPageNumber = pages[selectedPageIndex]?.page_number ?? pageDetail?.page_number ?? null;
  const summaryItems = parseSummary(pageDetail?.summary);

  useEffect(() => {
    void loadDocuments();
  }, []);

  useEffect(() => {
    if (!selectedDocumentId) {
      setPages([]);
      setSelectedPageId(null);
      setDocumentFileUrl(null);
      setPageDetail(null);
      return;
    }

    void loadDocumentFileUrl(selectedDocumentId);
    void loadPages(selectedDocumentId);
  }, [selectedDocumentId]);

  useEffect(() => {
    selectedPageIdRef.current = selectedPageId;
  }, [selectedPageId]);

  useEffect(() => {
    if (!selectedPageId) {
      setPageDetail(null);
      setPageQuestion("");
      setPageAnswer(null);
      return;
    }

    void loadPage(selectedPageId);
  }, [selectedPageId]);

  async function loadDocuments() {
    setIsBootstrapping(true);
    setError(null);

    try {
      const documentList = await apiFetch<DocumentListItem[]>("/documents");
      setDocuments(documentList);

      if (documentList.length > 0) {
        setSelectedDocumentId((current) => current ?? documentList[0].id);
      }
    } catch (loadError) {
      setError(getMessage(loadError));
    } finally {
      setIsBootstrapping(false);
    }
  }

  async function loadPages(documentId: string) {
    setError(null);
    setSelectedPageId(null);
    setPageDetail(null);

    try {
      const pageList = await apiFetch<PageListItem[]>(`/document/${documentId}/pages`);
      setPages(pageList);

      if (pageList.length === 0) {
        setSelectedPageId(null);
        return;
      }

      setSelectedPageId((current) => {
        const stillExists = pageList.some((page) => page.id === current);
        return stillExists ? current : pageList[0].id;
      });
    } catch (loadError) {
      setError(getMessage(loadError));
    }
  }

  async function loadDocumentFileUrl(documentId: string) {
    try {
      const response = await apiFetch<{ url: string }>(`/document/${documentId}/file-url`);
      setDocumentFileUrl(response.url);
    } catch {
      setDocumentFileUrl(null);
    }
  }

  async function loadPage(pageId: string) {
    setIsLoadingPage(true);
    setError(null);

    try {
      const page = await apiFetch<PageDetail>(`/page/${pageId}`);
      setPageState(page);

      if (!page.summary) {
        void pollForSummary(pageId);
      } else {
        setIsLoadingPage(false);
      }
    } catch (loadError) {
      setError(getMessage(loadError));
      setIsLoadingPage(false);
    }
  }

  async function pollForSummary(pageId: string) {
    for (let attempt = 0; attempt < SUMMARY_POLL_ATTEMPTS; attempt += 1) {
      await delay(SUMMARY_POLL_INTERVAL_MS);

      if (selectedPageIdRef.current !== pageId) {
        return;
      }

      try {
        const page = await apiFetch<PageDetail>(`/page/${pageId}`);
        setPageState(page);

        if (page.summary) {
          setIsLoadingPage(false);
          return;
        }
      } catch (loadError) {
        setError(getMessage(loadError));
        setIsLoadingPage(false);
        return;
      }
    }

    if (selectedPageIdRef.current === pageId) {
      setIsLoadingPage(false);
    }
  }

  function setPageState(page: PageDetail) {
    setPageDetail(page);
    setPages((currentPages) =>
      currentPages.map((item) =>
        item.id === page.id ? { ...item, summary: page.summary } : item
      )
    );
  }

  async function handleAskQuestion() {
    if (!pageDetail) {
      return;
    }

    const question = pageQuestion.trim();
    if (!question) {
      setError("Enter a question for this page.");
      return;
    }

    setIsAskingQuestion(true);
    setError(null);

    try {
      const response = await apiFetch<{ answer: string }>(`/page/${pageDetail.id}/ask`, {
        method: "POST",
        json: { question },
      });
      setPageAnswer(response.answer);
    } catch (askError) {
      setError(getMessage(askError));
    } finally {
      setIsAskingQuestion(false);
    }
  }

  function delay(ms: number) {
    return new Promise((resolve) => {
      window.setTimeout(resolve, ms);
    });
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;

    const formData = new FormData(form);
    const file = formData.get("file");

    if (!(file instanceof File)) {
      setError("Choose a PDF to upload.");
      return;
    }

    setIsUploading(true);
    setError(null);

    try {
      const payload = new FormData();
      payload.append("file", file);

      const result = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/upload`, {
        method: "POST",
        body: payload,
      });

      if (!result.ok) {
        const errorBody = (await result.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(errorBody?.detail ?? "Upload failed.");
      }

      const data = (await result.json()) as UploadResponse;
      await loadDocuments();
      setSelectedDocumentId(data.document_id);
    } catch (uploadError) {
      setError(getMessage(uploadError));
    } finally {
      setIsUploading(false);
      form.reset();
    }
  }

  async function handleDeleteDocument() {
    if (!selectedDocument) {
      return;
    }

    const confirmed = window.confirm(
      `Delete "${selectedDocument.name}" and all extracted pages and summaries?`
    );
    if (!confirmed) {
      return;
    }

    setIsDeletingDocument(true);
    setError(null);

    try {
      await apiFetch<{ status: string }>(`/document/${selectedDocument.id}`, {
        method: "DELETE",
      });

      setDocuments((currentDocuments) => {
        const nextDocuments = currentDocuments.filter((document) => document.id !== selectedDocument.id);
        setSelectedDocumentId(nextDocuments[0]?.id ?? null);
        return nextDocuments;
      });
      setPages([]);
      setDocumentFileUrl(null);
      setSelectedPageId(null);
      setPageDetail(null);
    } catch (deleteError) {
      setError(getMessage(deleteError));
    } finally {
      setIsDeletingDocument(false);
    }
  }

  async function handleSaveAnnotations(annotations: PageAnnotation[]) {
    if (!pageDetail) {
      return;
    }

    setIsSavingAnnotations(true);
    setError(null);

    try {
      const updatedPage = await apiFetch<PageDetail>(`/page/${pageDetail.id}/annotations`, {
        method: "PUT",
        json: { annotations },
      });

      setPageDetail(updatedPage);
    } catch (saveError) {
      setError(getMessage(saveError));
      throw saveError;
    } finally {
      setIsSavingAnnotations(false);
    }
  }

  async function handleRegenerateSummary() {
    if (!pageDetail) {
      return;
    }

    setIsRegeneratingSummary(true);
    setIsLoadingPage(true);
    setError(null);

    try {
      const updatedPage = await apiFetch<PageDetail>(`/page/${pageDetail.id}/regenerate-summary`, {
        method: "POST",
      });
      setPageState(updatedPage);
    } catch (regenerateError) {
      setError(getMessage(regenerateError));
    } finally {
      setIsRegeneratingSummary(false);
      setIsLoadingPage(false);
    }
  }

  return (
    <main className="shell">
      <div className="frame">
        <section className="workspace">
          <aside className="sidebar">
            <form className="upload-form" onSubmit={handleUpload}>
              <input accept="application/pdf" name="file" type="file" />
              <button className="button" disabled={isUploading} type="submit">
                {isUploading ? <LoaderCircle size={16} className="spin" /> : <Upload size={16} />}
                {isUploading ? "Uploading PDF..." : "Upload PDF"}
              </button>
            </form>

            {error ? <div className="error">{error}</div> : null}

            <div className="panel-title">
              <h2>Documents</h2>
              <span className="muted">{documents.length}</span>
            </div>

            <div className="sidebar-actions">
              <button
                className="button button-secondary button-danger"
                disabled={!selectedDocument || isDeletingDocument}
                onClick={handleDeleteDocument}
                type="button"
              >
                {isDeletingDocument ? <LoaderCircle size={16} className="spin" /> : <Trash2 size={16} />}
                {isDeletingDocument ? "Deleting..." : "Delete file"}
              </button>
            </div>

            <div className="document-list">
              {documents.map((document) => (
                <button
                  key={document.id}
                  className={`list-button ${document.id === selectedDocumentId ? "active" : ""}`}
                  onClick={() => setSelectedDocumentId(document.id)}
                  type="button"
                >
                  <span className="document-name">{document.name}</span>
                  <span className="muted">
                    {new Date(document.created_at).toLocaleDateString()}
                  </span>
                </button>
              ))}
            </div>
          </aside>

          <div className="content">
            <section className="pane">
              <div className="panel-title">
                <h3>{selectedDocument ? selectedDocument.name : "Page content"}</h3>
                <span className="muted">
                  {selectedDocument ? `${pages.length} pages` : "No document selected"}
                </span>
              </div>

              {isBootstrapping ? (
                <EmptyState message="Loading workspace..." />
              ) : !selectedDocument ? (
                <EmptyState message="Upload a PDF to begin." />
              ) : pages.length === 0 ? (
                <EmptyState message="This document has no extracted pages." />
              ) : (
                <>
                  <div className="page-toolbar">
                    <div className="page-switcher">
                      <button
                        className="icon-button"
                        disabled={selectedPageIndex <= 0}
                        onClick={() => setSelectedPageId(pages[selectedPageIndex - 1]?.id ?? null)}
                        type="button"
                      >
                        <ChevronLeft size={16} />
                      </button>

                      <label className="page-select-wrap">
                        <span className="section-label">Page</span>
                        <select
                          className="page-select"
                          onChange={(event) => setSelectedPageId(event.target.value)}
                          value={selectedPageId ?? ""}
                        >
                          {pages.map((page) => (
                            <option key={page.id} value={page.id}>
                              Page {page.page_number} {page.summary ? "• summarized" : ""}
                            </option>
                          ))}
                        </select>
                      </label>

                      <button
                        className="icon-button"
                        disabled={selectedPageIndex === -1 || selectedPageIndex >= pages.length - 1}
                        onClick={() => setSelectedPageId(pages[selectedPageIndex + 1]?.id ?? null)}
                        type="button"
                      >
                        <ChevronRight size={16} />
                      </button>
                    </div>

                    <div className="page-toolbar-meta">
                      <span>{selectedPageNumber ? `Viewing page ${selectedPageNumber}` : "Select a page"}</span>
                      <span>
                        {isLoadingPage
                          ? "Loading summary..."
                          : pageDetail?.summary
                            ? "Summary ready"
                            : "Summary on demand"}
                      </span>
                    </div>
                  </div>

                  {selectedPageNumber ? (
                    <div className="viewer-stack">
                      <div className="summary-box pdf-box">
                        <div className="subpanel-head">
                          <span className="section-label">Actual page</span>
                          <span className="muted">Page {selectedPageNumber}</span>
                        </div>

                        {documentFileUrl ? (
                          <PdfPagePreview
                            fileUrl={documentFileUrl}
                            annotations={pageDetail?.annotations ?? []}
                            isSavingAnnotations={isSavingAnnotations}
                            onSaveAnnotations={handleSaveAnnotations}
                            pageNumber={selectedPageNumber}
                          />
                        ) : (
                          <div className="empty-state">PDF preview is not available for this page yet.</div>
                        )}
                      </div>

                      <details className="text-disclosure">
                        <summary>Extracted text</summary>
                          <div className="summary-box text-box">
                            <div className="page-copy">
                              {pageDetail?.content || "No text extracted from this page."}
                            </div>
                          </div>
                      </details>
                    </div>
                  ) : (
                    <div className="summary-box">
                      <div className="empty-state">Select a page to view its extracted text.</div>
                    </div>
                  )}
                </>
              )}
            </section>

            <aside className="pane summary-pane">
              <div className="panel-title">
                <h3>Accountant Summary</h3>
                <div className="summary-actions">
                  <button
                    className="button button-secondary summary-refresh-button"
                    disabled={!pageDetail || isLoadingPage || isRegeneratingSummary}
                    onClick={() => void handleRegenerateSummary()}
                    type="button"
                  >
                    {isRegeneratingSummary ? (
                      <LoaderCircle size={14} className="spin" />
                    ) : (
                      <RotateCcw size={14} />
                    )}
                    {isRegeneratingSummary ? "Regenerating..." : "Regenerate"}
                  </button>
                  <Sparkles size={16} />
                </div>
              </div>

              <div className="summary-box">
                {isLoadingPage ? (
                  <div className="summary-loading">
                    <div className="loading">
                      <span className="dot" />
                      Generating summary for page {selectedPageNumber ?? "..."}...
                    </div>
                    <div className="summary-skeleton" />
                    <div className="summary-skeleton" />
                    <div className="summary-skeleton summary-skeleton-short" />
                  </div>
                ) : pageDetail ? (
                  <div className="summary-layout">
                    <div className="summary-note">
                      Accountant takeaways for page {pageDetail.page_number}
                    </div>

                    {summaryItems.kind === "empty" ? (
                      <div className="summary-empty">
                        <AlertTriangle size={16} />
                        <span>No significant accounting-relevant information.</span>
                      </div>
                    ) : (
                      <div className="summary-list">
                        {summaryItems.items.map((item, index) => (
                          <article className="summary-card" key={`${item}-${index}`}>
                            <span className="summary-index">{index + 1}</span>
                            <p className="summary-copy">{item}</p>
                          </article>
                        ))}
                      </div>
                    )}

                    <div className="page-qa">
                      <div className="subpanel-head">
                        <span className="section-label">Ask this page</span>
                        <MessageSquare size={16} />
                      </div>

                      <div className="page-qa-form">
                        <textarea
                          className="page-qa-input"
                          onChange={(event) => setPageQuestion(event.target.value)}
                          placeholder="Ask about a deadline, exception, filing rule, or any detail on this page..."
                          rows={3}
                          value={pageQuestion}
                        />
                        <button
                          className="button"
                          disabled={!pageDetail || isAskingQuestion}
                          onClick={() => void handleAskQuestion()}
                          type="button"
                        >
                          {isAskingQuestion ? (
                            <LoaderCircle size={16} className="spin" />
                          ) : (
                            <MessageSquare size={16} />
                          )}
                          {isAskingQuestion ? "Asking..." : "Ask"}
                        </button>
                      </div>

                      {pageAnswer ? (
                        <div className="page-qa-answer">
                          <p>{pageAnswer}</p>
                        </div>
                      ) : null}
                    </div>
                  </div>
                ) : (
                  <EmptyState message="Pick a page to trigger lazy summarization." />
                )}
              </div>
            </aside>
          </div>
        </section>
      </div>
    </main>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="empty-state">
      <div>
        <FileText size={28} style={{ marginBottom: 12 }} />
        <div>{message}</div>
      </div>
    </div>
  );
}

function getMessage(error: unknown) {
  return error instanceof Error ? error.message : "Unexpected error.";
}

function parseSummary(summary: string | null | undefined): { kind: "empty" | "items"; items: string[] } {
  if (!summary) {
    return { kind: "empty", items: [] };
  }

  const normalized = summary.trim();
  if (
    !normalized ||
    normalized.toLowerCase() === "no significant accounting-relevant information."
  ) {
    return { kind: "empty", items: [] };
  }

  const items = normalized
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => line.replace(/^[-*•]\s*/, "").replace(/^\d+\.\s*/, "").trim())
    .filter(Boolean);

  const conciseItems = (items.length > 0 ? items : [normalized])
    .map((item) => compactSentence(item))
    .filter(Boolean)
    .slice(0, 5);

  return conciseItems.length > 0
    ? { kind: "items", items: conciseItems }
    : { kind: "empty", items: [] };
}

function compactSentence(value: string) {
  const singleLine = value.replace(/\s+/g, " ").trim();
  if (!singleLine) {
    return "";
  }

  if (singleLine.length <= 180) {
    return singleLine;
  }

  const trimmed = singleLine.slice(0, 177).trimEnd();
  return `${trimmed}...`;
}
