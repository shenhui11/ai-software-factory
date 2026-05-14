const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() ?? "";

function isLoopbackHost(hostname: string) {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
}

function resolveApiBaseUrl() {
  if (!configuredApiBaseUrl) {
    return "";
  }
  if (typeof window === "undefined") {
    return configuredApiBaseUrl;
  }
  try {
    const configuredUrl = new URL(configuredApiBaseUrl, window.location.origin);
    if (!/^https?:$/.test(configuredUrl.protocol)) {
      return configuredApiBaseUrl;
    }
    if (!isLoopbackHost(configuredUrl.hostname) || isLoopbackHost(window.location.hostname)) {
      return `${configuredUrl.origin}${configuredUrl.pathname}`.replace(/\/$/, "");
    }
    return `${configuredUrl.protocol}//${window.location.hostname}${configuredUrl.port ? `:${configuredUrl.port}` : ""}${configuredUrl.pathname}`.replace(/\/$/, "");
  } catch {
    return configuredApiBaseUrl;
  }
}

const API_BASE_URL = resolveApiBaseUrl();
const ADMIN_ROLE_HEADER = "X-User-Role";
const ADMIN_ROLE_VALUE = "admin";
const AUTH_STORAGE_KEY = "novel-workshop-session";

type Envelope<T> = {
  data: T;
  request_id: string;
};

export type AuthSessionPayload = {
  token: string;
  user: {
    id: string;
    username: string;
    role: "creator" | "admin";
  };
};

function getStoredToken() {
  if (typeof window === "undefined") {
    return "";
  }
  try {
    const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
    if (!raw) {
      return "";
    }
    const parsed = JSON.parse(raw) as { token?: string };
    return parsed.token ?? "";
  } catch {
    return "";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getStoredToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (path.startsWith("/admin")) {
    headers[ADMIN_ROLE_HEADER] = ADMIN_ROLE_VALUE;
  }
  const method = init?.method ?? "GET";
  console.info("[api.request]", method, path);
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { ...headers, ...(init?.headers as Record<string, string> | undefined) },
  });
  console.info("[api.response]", method, path, response.status);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.message ?? payload.detail?.message ?? "Request failed");
  }
  return (payload as Envelope<T>).data;
}

export type ProjectPayload = {
  title: string;
  genre: string;
  genres: string[];
  length_type: string;
  template_id: string;
  summary: string;
  character_cards: string[];
  world_rules: string[];
  event_summary: string[];
  story_beats: Array<Record<string, any>>;
  mode_default: "manual" | "auto";
};

export function createProject(payload: ProjectPayload) {
  return request<any>("/api/projects", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function generateProjectFoundation(payload: {
  title: string;
  genre: string;
  genres: string[];
  length_type: string;
  template_id: string;
  summary: string;
  character_cards: string[];
  world_rules: string[];
  event_summary: string[];
}) {
  return request<{ task_id: string; status: "queued" | "running" | "completed" | "failed" }>("/api/projects/generate-foundation", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getProjectFoundationTask(taskId: string) {
  return request<{
    id: string;
    status: "queued" | "running" | "completed" | "failed";
    progress_stage?: string;
    progress_message?: string;
    result: {
      summary?: string;
      character_cards?: string[];
      world_rules?: string[];
      event_summary?: string[];
      story_beats?: Array<Record<string, any>>;
      active_phase?: Record<string, any>;
    } | null;
    error_message?: string;
  }>(`/api/projects/foundation-tasks/${taskId}`);
}

export function register(payload: { username: string; password: string }) {
  return request<any>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ ...payload, role: "creator" }),
  });
}

export function login(payload: { username: string; password: string }) {
  return request<AuthSessionPayload>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getMe() {
  return request<any>("/api/auth/me");
}

export function logout() {
  return request<any>("/api/auth/logout", {
    method: "POST",
  });
}

export function changePassword(payload: { current_password: string; new_password: string }) {
  return request<AuthSessionPayload>("/api/auth/password", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listProjects() {
  return request<any[]>("/api/projects");
}

export function listGenres() {
  return request<Array<{ value: string; label: string }>>("/api/genres");
}

export function getProject(projectId: string) {
  return request<any>(`/api/projects/${projectId}`);
}

export function deleteProject(projectId: string) {
  return request<any>(`/api/projects/${projectId}`, {
    method: "DELETE",
  });
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

export function getChapterDetail(projectId: string, chapterId: string) {
  return request<any>(`/api/projects/${projectId}/chapters/${chapterId}`);
}

export function clearActiveTask(projectId: string) {
  return request<any>(`/api/projects/${projectId}/tasks/clear-active`, {
    method: "POST",
  });
}

export function confirmChapter(projectId: string, chapterId: string) {
  return request<any>(`/api/projects/${projectId}/chapters/${chapterId}/confirm`, {
    method: "POST",
  });
}

export function regenerateChapterOutlines(projectId: string, chapterId: string, userIdea = "") {
  return request<any>(`/api/projects/${projectId}/chapters/${chapterId}/outlines/regenerate`, {
    method: "POST",
    body: JSON.stringify({ user_idea: userIdea }),
  });
}

export function selectOutlineOption(projectId: string, chapterId: string, optionId: string) {
  return request<any>(`/api/projects/${projectId}/chapters/${chapterId}/outlines/${optionId}/select`, {
    method: "POST",
  });
}

export function updateOutlineOption(
  projectId: string,
  chapterId: string,
  optionId: string,
  payload: { content: string; core_conflict: string; key_event: string; ending_hook: string },
) {
  return request<any>(`/api/projects/${projectId}/chapters/${chapterId}/outlines/${optionId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function regenerateChapterDraft(projectId: string, chapterId: string) {
  return request<any>(`/api/projects/${projectId}/chapters/${chapterId}/drafts/regenerate`, {
    method: "POST",
  });
}

export function updateChapterDraft(projectId: string, chapterId: string, draftId: string, content: string) {
  return request<any>(`/api/projects/${projectId}/chapters/${chapterId}/drafts/${draftId}`, {
    method: "PATCH",
    body: JSON.stringify({ content }),
  });
}

export function updateChapter(projectId: string, chapterId: string, title: string) {
  return request<any>(`/api/projects/${projectId}/chapters/${chapterId}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

export function deleteChapter(projectId: string, chapterId: string) {
  return request<any>(`/api/projects/${projectId}/chapters/${chapterId}`, {
    method: "DELETE",
  });
}

export function rewriteChapter(
  projectId: string,
  chapterId: string,
  instruction: string,
  chapterContent: string,
  paragraph?: string,
) {
  return request<any>(`/api/projects/${projectId}/chapters/${chapterId}/rewrite`, {
    method: "POST",
    body: JSON.stringify({ instruction, chapter_content: chapterContent, paragraph }),
  });
}

export function expandChapter(
  projectId: string,
  chapterId: string,
  instruction: string,
  chapterContent: string,
  paragraph?: string,
) {
  return request<any>(`/api/projects/${projectId}/chapters/${chapterId}/expand`, {
    method: "POST",
    body: JSON.stringify({ instruction, chapter_content: chapterContent, paragraph }),
  });
}

export function removeChapterParagraph(
  projectId: string,
  chapterId: string,
  instruction: string,
  chapterContent: string,
  paragraph: string,
) {
  return request<any>(`/api/projects/${projectId}/chapters/${chapterId}/remove`, {
    method: "POST",
    body: JSON.stringify({ instruction, chapter_content: chapterContent, paragraph }),
  });
}

export function listTemplates() {
  return request<any[]>("/api/templates");
}

export function createTemplate(payload: {
  name: string;
  genre: string;
  genres: string[];
  tags: string[];
  style_rules: string;
  world_template: string;
  character_template: string;
  outline_template: string;
  status?: string;
}) {
  return request<any>("/api/templates", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateTemplate(templateId: string, payload: Record<string, string | string[]>) {
  return request<any>(`/api/templates/${templateId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function getQuotas() {
  return request<any>("/api/membership/quotas");
}

export function getAdminTemplates() {
  return request<any>("/admin/templates");
}

export function getAdminGenres() {
  return request<Array<{ value: string; label: string; required_any: string[]; forbidden_any: string[] }>>("/admin/genres");
}

export function updateAdminGenre(
  genreValue: string,
  payload: { label: string; required_any: string[]; forbidden_any: string[] },
) {
  return request<any>(`/admin/genres/${encodeURIComponent(genreValue)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function publishAdminTemplate(templateId: string) {
  return request<any>(`/admin/templates/${templateId}/publish`, {
    method: "POST",
  });
}

export function getAdminMemberships(targetUserId?: string) {
  const params = targetUserId?.trim() ? `?target_user_id=${encodeURIComponent(targetUserId.trim())}` : "";
  return request<any>(`/admin/memberships${params}`);
}

export function getAdminUsers() {
  return request<Array<{ id: string; username: string; role: "creator" | "admin" }>>("/admin/users");
}

export function createAdminUser(payload: { username: string; password: string; role: "creator" }) {
  return request<{ id: string; username: string; role: "creator" | "admin" }>("/admin/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function resetAdminUserPassword(userId: string) {
  return request<{ user: { id: string; username: string; role: "creator" | "admin" }; reset_password: string }>(
    `/admin/users/${userId}/reset-password`,
    {
      method: "POST",
    },
  );
}

export function createAdminMembershipPlan(payload: {
  name: string;
  daily_free_chapters: number;
  monthly_free_chapters: number;
  description: string;
}) {
  return request<any>("/admin/memberships/plans", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateAdminMembershipPlan(
  planId: string,
  payload: {
    name: string;
    daily_free_chapters: number;
    monthly_free_chapters: number;
    description: string;
  },
) {
  return request<any>(`/admin/memberships/plans/${planId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function activateAdminMembershipPlan(planId: string) {
  return request<any>(`/admin/memberships/plans/${planId}/activate`, {
    method: "POST",
  });
}

export function adjustAdminQuota(dailyDelta: number, monthlyDelta: number, bonusDelta: number, targetUserId?: string) {
  return request<any>("/admin/quotas/adjust", {
    method: "POST",
    body: JSON.stringify({
      target_user_id: targetUserId?.trim() || undefined,
      daily_delta: dailyDelta,
      monthly_delta: monthlyDelta,
      bonus_delta: bonusDelta,
    }),
  });
}

export function getAdminOrders() {
  return request<any>("/admin/orders");
}

export function createAdminOrder(payload: {
  plan_id: string;
  amount: number;
  status: string;
  note: string;
}) {
  return request<any>("/admin/orders", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateAdminOrder(
  orderId: string,
  payload: {
    plan_id: string;
    amount: number;
    status: string;
    note: string;
  },
) {
  return request<any>(`/admin/orders/${orderId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function getAdminSafetyPolicies() {
  return request<any>("/admin/safety/policies");
}

export function updateAdminSafetyPolicy(policyId: string, payload: { blocked_terms: string[]; copyright_notice: string }) {
  return request<any>(`/admin/safety/policies/${policyId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function getAdminTaskLogs() {
  return request<any[]>("/admin/logs/tasks");
}
