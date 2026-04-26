export type DocumentListItem = {
  id: string;
  name: string;
  created_at: string;
};

export type PageListItem = {
  id: string;
  page_number: number;
  summary: string | null;
  created_at: string;
};

export type PageAnnotation = {
  id: string;
  type: "highlight" | "note";
  x: number;
  y: number;
  width: number;
  height: number;
  text: string | null;
  created_at: string;
};

export type PageDetail = {
  id: string;
  document_id: string;
  page_number: number;
  content: string;
  summary: string | null;
  annotations: PageAnnotation[];
  document_file_url: string | null;
  created_at: string;
};

export type AskPageQuestionResponse = {
  answer: string;
};

export type UploadResponse = {
  document_id: string;
  name: string;
  page_count: number;
};
