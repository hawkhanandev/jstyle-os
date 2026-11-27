// Small fetch wrapper: sends cookies, adds the CSRF header on writes, surfaces API errors.
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

function csrfToken(): string {
  if (typeof document === "undefined") return "";
  const m = document.cookie.match(/(?:^|; )jstyle_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (method !== "GET" && method !== "HEAD") headers.set("x-csrf-token", csrfToken());
  if (init.body && !(init.body instanceof FormData) && !headers.has("content-type")) headers.set("content-type", "application/json");
  const res = await fetch(`/api${path}`, { ...init, headers, credentials: "same-origin" });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data?.detail ?? {};
    throw new ApiError(res.status, d.code ?? "error", d.message ?? res.statusText);
  }
  return data as T;
}

export type Me = { email: string; display_name: string | null; session_id: string; device_label: string | null };
