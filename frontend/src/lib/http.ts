import { DEFAULT_HEADERS } from "./constants";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

function buildHeaders(headers?: HeadersInit, requestId?: string) {
  return {
    ...DEFAULT_HEADERS,
    ...(requestId ? { "X-Request-Id": requestId } : {}),
    ...(headers ?? {})
  };
}

export async function httpGet<T>(path: string, init?: RequestInit, requestId?: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: buildHeaders(init?.headers, requestId)
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function httpPost<T>(path: string, body: unknown, init?: RequestInit, requestId?: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    ...init,
    headers: buildHeaders(
      {
        "Content-Type": "application/json",
        ...(init?.headers ?? {})
      },
      requestId
    ),
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}
