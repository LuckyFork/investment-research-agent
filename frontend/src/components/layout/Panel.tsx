import { PropsWithChildren } from "react";

export function Panel({ title, children }: PropsWithChildren<{ title: string }>) {
  return (
    <section className="rounded-3xl border border-line bg-panel p-5 shadow-panel">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-display text-sm font-semibold uppercase tracking-[0.18em] text-muted">{title}</h2>
      </div>
      {children}
    </section>
  );
}
