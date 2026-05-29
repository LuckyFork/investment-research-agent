import { DEFAULT_HEADERS } from "./constants";

export async function streamJsonEvents<T>(
  path: string,
  body: unknown,
  {
    onEvent,
    onError,
    requestId
  }: {
    onEvent: (event: T) => void;
    onError?: (error: Error) => void;
    requestId?: string;
  }
) {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      ...DEFAULT_HEADERS,
      ...(requestId ? { "X-Request-Id": requestId } : {}),
      "Content-Type": "application/json"
    },
    body: JSON.stringify(body)
  });

  if (!response.ok || !response.body) {
    const error = new Error(`Stream request failed: ${response.status}`);
    onError?.(error);
    throw error;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";

    for (const chunk of chunks) {
      const line = chunk
        .split("\n")
        .find((item) => item.startsWith("data: "));
      if (!line) continue;
      try {
        onEvent(JSON.parse(line.slice(6)) as T);
      } catch (error) {
        onError?.(error as Error);
      }
    }
  }
}
