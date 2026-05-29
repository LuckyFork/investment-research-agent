import { Link, useLocation } from "react-router-dom";
import { useI18n } from "../../i18n/provider";

export function TopBar() {
  const location = useLocation();
  const { locale, setLocale, t } = useI18n();
  const items = [
    { to: "/console", label: t("topbar.console") },
    { to: "/traces", label: t("topbar.traces") },
    { to: "/evals", label: t("topbar.evals") }
  ];

  return (
    <header className="sticky top-0 z-10 border-b border-line/80 bg-canvas/90 backdrop-blur">
      <div className="mx-auto flex max-w-[1600px] items-center justify-between px-6 py-4">
        <div>
          <p className="font-display text-lg font-semibold text-accent">{t("topbar.title")}</p>
          <p className="text-sm text-muted">{t("topbar.subtitle")}</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-sm text-muted">
            <span>{t("topbar.language")}</span>
            <button
              type="button"
              onClick={() => setLocale("zh")}
              className={`rounded-full px-3 py-1 text-sm font-medium ${locale === "zh" ? "bg-accent text-white" : "bg-panel text-text"}`}
            >
              {t("topbar.zh")}
            </button>
            <button
              type="button"
              onClick={() => setLocale("en")}
              className={`rounded-full px-3 py-1 text-sm font-medium ${locale === "en" ? "bg-accent text-white" : "bg-panel text-text"}`}
            >
              {t("topbar.en")}
            </button>
          </div>
          <nav className="flex gap-2">
            {items.map((item) => {
              const active = location.pathname === item.to;
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`rounded-full px-4 py-2 text-sm font-medium ${
                    active ? "bg-accent text-white" : "bg-panel text-text"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>
      </div>
    </header>
  );
}
