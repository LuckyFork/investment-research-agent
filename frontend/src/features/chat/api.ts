import { streamJsonEvents } from "../../lib/sse";
import type { ChatStreamEvent } from "./types";

export async function streamChat(
  input: { sessionId: string; message: string; requestId: string },
  onEvent: (event: ChatStreamEvent) => void,
  onError: (error: Error) => void
) {
  await streamJsonEvents<ChatStreamEvent>(
    "/api/v1/chat/completions",
    {
      session_id: input.sessionId,
      message: input.message,
      stream: true
    },
    {
      requestId: input.requestId,
      onEvent,
      onError
    }
  );
}
