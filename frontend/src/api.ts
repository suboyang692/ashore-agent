export type User = { id: string; username: string; email: string | null; role: string; status: string };
export type Session = { token: string; user: User };
export type AnswerSource = {
  fragment: number; cite: string; source: string; page: number | null;
  via: string; excerpt: string; cited: boolean;
};
export type AnswerData = {
  knowledge_point?: string;
  sources?: AnswerSource[];
  next_action?: { type: string; knowledge_point: string } | null;
};
export type ChatResponse = {
  intent: string; reply: string; data: AnswerData & Record<string, unknown>;
};
export type Conversation = { id: number; title: string; updated_at: string };
export type ConversationMessage = { id: number; role: "user" | "assistant"; content: string; response_data: { intent: string; data: AnswerData } | null };
export const listConversations = (token: string) => request<{ items: Conversation[] }>("/conversations", {}, token);
export const createConversation = (token: string) => request<Conversation>("/conversations", { method: "POST" }, token);
export const getConversationMessages = (id: number, token: string) => request<{ items: ConversationMessage[] }>(`/conversations/${id}/messages`, {}, token);
export const deleteConversation = (id: number, token: string) => request<{ deleted: number }>(`/conversations/${id}`, { method: "DELETE" }, token);
export const clearConversations = (token: string) => request<{ deleted: number }>("/conversations", { method: "DELETE" }, token);
export type ChatStreamEvent =
  | { type: "meta"; intent: string; knowledge_point?: string }
  | { type: "token"; text: string }
  | { type: "done"; result: ChatResponse }
  | { type: "error"; message: string };
export type Question = { id: number; knowledge_point: string; question_type: string; stem: string; difficulty: number | null };
export type Mastery = { total_count: number; wrong_count: number; mastery: number };
export type ObjectiveResult = {
  type: "objective"; attempt_id?: number; correct: boolean; mastery: Mastery | null;
  standard_answer: string; analysis: string;
};
export type SubjectiveResult = {
  type: "subjective"; attempt_id?: number; score: number; mistake_type: string;
  comment: string; suggestion: string; standard_answer: string; analysis: string;
};
export type SubmitResult = ObjectiveResult | SubjectiveResult;
export type Mistake = {
  id: number; attempt_id: number; knowledge_point: string | null; mistake_type: string;
  original_text: string | null; reason: string | null; correct_method: string | null;
  question_id: number; score: number | null; submitted_at: string; stem: string; question_type: string;
};
export type PlanDay = {
  day: number; focus: string; knowledge_points: string[]; tasks: string; reason: string;
};
export type PlanItem = {
  id: number; plan_id: number; day_no: number; knowledge_point: string; task_type: string;
  question_id: number | null; target_count: number; completed_count: number;
  status: "pending" | "in_progress" | "completed" | "overdue";
  due_at: string | null; completed_at: string | null;
};
export type ReviewPlan = {
  plan_id: number; days: number; summary: string; schedule: PlanDay[];
  created_at: string; items?: PlanItem[];
};
export type MasteryItem = {
  knowledge_point: string; subject: string; total_count: number; wrong_count: number; mastery: number;
};
export type Profile = { user_id: string; items: MasteryItem[]; weak_points: string[] };
export type AdminOverview = {
  users: number; questions: number; conversations: number; attempts: number;
  cache: {
    backend: string; hit_rate: number; keys: number;
    kb_version: number; sessions: number;
  };
};
export type AdminUser = {
  id: string; username: string; email: string | null;
  role: "student" | "admin"; status: "active" | "disabled";
  created_at: string; last_login_at: string | null;
};
export type AuditLog = {
  id: number; actor_id: string | null; actor_name: string | null; action: string;
  target_type: string | null; target_id: string | null;
  request_id: string | null; ip: string | null;
  detail: Record<string, unknown> | null; created_at: string;
};

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

export async function request<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    });
  } catch {
    throw new Error("无法连接后端。请先启动 python -m app.api。");
  }
  if (!response.ok) {
    let detail = "请求失败，请稍后重试";
    try {
      const payload = await response.json();
      if (typeof payload.detail === "string") detail = payload.detail;
    } catch { /* HTTP error without JSON */ }
    throw new ApiError(detail, response.status);
  }
  return response.json() as Promise<T>;
}

export function authenticate(mode: "login" | "register", username: string, password: string) {
  return request<Session>(`/auth/${mode}`, {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function getMe(token: string) {
  return request<User>("/auth/me", {}, token);
}

export function ask(userId: string, message: string, token: string) {
  return request<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, message }),
  }, token);
}

export async function streamAsk(
  userId: string, message: string, token: string,
  onEvent: (event: ChatStreamEvent) => void, signal?: AbortSignal, conversationId?: number,
) {
  let response: Response;
  try {
    response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ user_id: userId, message, conversation_id: conversationId }),
      signal,
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new Error("无法连接后端。请先启动 python -m app.api。");
  }

  if (!response.ok) {
    let detail = "请求失败，请稍后重试";
    try {
      const payload = await response.json();
      if (typeof payload.detail === "string") detail = payload.detail;
    } catch { /* HTTP error without JSON */ }
    throw new ApiError(detail, response.status);
  }
  if (!response.body) throw new Error("浏览器不支持流式响应。");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");

    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const payload = block
        .split("\n")
        .filter(line => line.startsWith("data:"))
        .map(line => line.slice(5).trimStart())
        .join("\n");
      if (payload && payload !== "[DONE]") {
        onEvent(JSON.parse(payload) as ChatStreamEvent);
      }
      boundary = buffer.indexOf("\n\n");
    }
    if (done) break;
  }
}

export function getNextQuestion(userId: string, questionType: string,
                                 knowledgePoint: string, token: string) {
  const type = questionType ? `&question_type=${encodeURIComponent(questionType)}` : "";
  const point = knowledgePoint ? `&knowledge_point=${encodeURIComponent(knowledgePoint)}` : "";
  return request<Question>(
    `/questions/next?user_id=${encodeURIComponent(userId)}${type}${point}`, {}, token,
  );
}

export function submitAnswer(userId: string, questionId: number, answer: string, token: string) {
  return request<SubmitResult>("/submit", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, question_id: questionId, answer }),
  }, token);
}

export function getMistakes(userId: string, knowledgePoint: string, mistakeType: string, token: string) {
  const params = new URLSearchParams({ user_id: userId, limit: "50" });
  if (knowledgePoint.trim()) params.set("knowledge_point", knowledgePoint.trim());
  if (mistakeType.trim()) params.set("mistake_type", mistakeType.trim());
  return request<{ user_id: string; items: Mistake[] }>(`/mistakes?${params}`, {}, token);
}

export function getLatestPlan(userId: string, token: string) {
  return request<ReviewPlan>(
    `/plan/${encodeURIComponent(userId)}?include_items=true`, {}, token,
  );
}

export function createPlan(userId: string, days: number, token: string) {
  return request<{ plan_id: number; days: number; summary: string; schedule: PlanDay[] }>("/plan", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, days }),
  }, token);
}

export function completePlanItem(itemId: number, userId: string, token: string) {
  return request<PlanItem>(
    `/plan-items/${itemId}/complete?user_id=${encodeURIComponent(userId)}`, { method: "POST" }, token,
  );
}

export function getProfile(userId: string, token: string) {
  return request<Profile>(`/profile/${encodeURIComponent(userId)}`, {}, token);
}

export function getAdminOverview(token: string) {
  return request<AdminOverview>("/admin/overview", {}, token);
}

export function getAdminUsers(query: string, offset: number, limit: number, token: string) {
  const params = new URLSearchParams({
    q: query.trim(), limit: String(limit), offset: String(offset),
  });
  return request<{ items: AdminUser[]; limit: number; offset: number }>(
    `/admin/users?${params}`, {}, token,
  );
}

export function getAdminAuditLogs(offset: number, limit: number, token: string) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return request<{ items: AuditLog[]; total: number; limit: number; offset: number }>(
    `/admin/audit-logs?${params}`, {}, token,
  );
}

export function setAdminUserStatus(userId: string, status: AdminUser["status"], token: string) {
  return request<{ id: string; status: string }>(
    `/admin/users/${encodeURIComponent(userId)}/status`,
    { method: "PATCH", body: JSON.stringify({ status }) },
    token,
  );
}

export function setAdminUserRole(userId: string, role: AdminUser["role"], token: string) {
  return request<{ id: string; role: string }>(
    `/admin/users/${encodeURIComponent(userId)}/role`,
    { method: "PATCH", body: JSON.stringify({ role }) },
    token,
  );
}
