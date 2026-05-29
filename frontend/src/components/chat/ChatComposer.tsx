import { FormEvent } from "react";
import { useI18n } from "../../i18n/provider";

export function ChatComposer({
  sessionId,
  input,
  streaming,
  onSessionChange,
  onInputChange,
  onSubmit
}: {
  sessionId: string;
  input: string;
  streaming: boolean;
  onSessionChange: (value: string) => void;
  onInputChange: (value: string) => void;
  onSubmit: () => void;
}) {
  const { t } = useI18n();

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    onSubmit();
  }

  return (
    <form className="space-y-3" onSubmit={handleSubmit}>
      <input
        className="w-full rounded-2xl border border-line bg-white px-4 py-3 text-sm"
        value={sessionId}
        onChange={(event) => onSessionChange(event.target.value)}
        placeholder={t("chat.sessionId")}
      />
      <textarea
        className="min-h-[132px] w-full rounded-3xl border border-line bg-white px-4 py-4 text-sm leading-6"
        value={input}
        onChange={(event) => onInputChange(event.target.value)}
        placeholder={t("chat.placeholder")}
      />
      <button
        type="submit"
        disabled={streaming || !input.trim()}
        className="rounded-full bg-accent px-5 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
      >
        {streaming ? t("chat.streaming") : t("chat.runQuery")}
      </button>
    </form>
  );
}
