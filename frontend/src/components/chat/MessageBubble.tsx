import { ChatMessageView } from "../../features/chat/types";

export function MessageBubble({ message }: { message: ChatMessageView }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[90%] rounded-3xl px-4 py-3 text-sm leading-6 ${
          isUser ? "bg-accent text-white" : "border border-line bg-white text-text"
        }`}
      >
        {message.content}
      </div>
    </div>
  );
}
