import { useI18n } from "../../i18n/provider";

export function StreamStatus({ streaming, error }: { streaming: boolean; error?: string }) {
  const { t } = useI18n();

  if (error) {
    return <p className="text-sm text-danger">{error}</p>;
  }
  return <p className="text-sm text-muted">{streaming ? t("chat.statusStreaming") : t("chat.statusReady")}</p>;
}
