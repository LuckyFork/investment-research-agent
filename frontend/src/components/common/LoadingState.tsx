export function LoadingState({ label = "Loading..." }: { label?: string }) {
  return <div className="text-sm text-muted">{label}</div>;
}
