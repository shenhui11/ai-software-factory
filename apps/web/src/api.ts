const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

type Envelope<T> = {
  data: T;
  request_id: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.message ?? payload.detail?.message ?? "Request failed");
  }
  return (payload as Envelope<T>).data;
}

export type ProjectPayload = {
  title: string;
  genre: string;
  length_type: string;
  template_id: string;
  summary: string;
  character_cards: string[];
  world_rules: string[];
  event_summary: string[];
  mode_default: "manual" | "auto";
};

export function createProject(payload: ProjectPayload) {
  return request<any>("/api/projects", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getProject(projectId: string) {
  return request<any>(`/api/projects/${projectId}`);
}

export function createTask(projectId: string, payload: { mode: "manual" | "auto"; chapter_count: number; start_chapter_index: number }) {
  return request<any>(`/api/projects/${projectId}/chapters/generate`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function runTask(projectId: string, taskId: string) {
  return request<any>(`/api/projects/${projectId}/tasks/${taskId}/run`, {
    method: "POST",
  });
}

export function getTask(projectId: string, taskId: string) {
  return request<any>(`/api/projects/${projectId}/tasks/${taskId}`);
}

export function confirmChapter(projectId: string, chapterId: string) {
  return request<any>(`/api/projects/${projectId}/chapters/${chapterId}/confirm`, {
    method: "POST",
  });
}

export function rewriteParagraph(projectId: string, chapterId: string, paragraph: string, instruction: string) {
  return request<any>(`/api/projects/${projectId}/chapters/${chapterId}/paragraph-rewrite`, {
    method: "POST",
    body: JSON.stringify({ paragraph, instruction }),
  });
}

export function expandParagraph(projectId: string, chapterId: string, paragraph: string, instruction: string) {
  return request<any>(`/api/projects/${projectId}/chapters/${chapterId}/paragraph-expand`, {
    method: "POST",
    body: JSON.stringify({ paragraph, instruction }),
  });
}

export function listTemplates() {
  return request<any[]>("/api/templates");
}
