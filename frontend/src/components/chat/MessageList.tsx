import { ChatMessageView } from "../../features/chat/types";
import { useI18n } from "../../i18n/provider";
import { EmptyState } from "../common/EmptyState";
import { MessageBubble } from "./MessageBubble";

export function MessageList({ messages }: { messages: ChatMessageView[] }) {
  const { t } = useI18n();

  if (!messages.length) {
    return <EmptyState title={t("chat.noConversation")} body={t("chat.noConversationBody")} />;
  }

  return (
    <div className="space-y-3">
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}
    </div>
  );
}
