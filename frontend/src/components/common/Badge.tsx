import { clsx } from "clsx";
import { PropsWithChildren } from "react";

export function Badge({
  tone = "default",
  children
}: PropsWithChildren<{ tone?: "default" | "success" | "warning" | "danger" | "accent" }>) {
  return (
    <span
      className={clsx(
        "inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold tracking-wide",
        tone === "default" && "border-line bg-panel text-text",
        tone === "success" && "border-success/20 bg-success/10 text-success",
        tone === "warning" && "border-warning/20 bg-warning/10 text-warning",
        tone === "danger" && "border-danger/20 bg-danger/10 text-danger",
        tone === "accent" && "border-accent/20 bg-accent/10 text-accent"
      )}
    >
      {children}
    </span>
  );
}
