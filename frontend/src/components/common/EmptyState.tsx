export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-line p-6 text-sm text-muted">
      <p className="font-semibold text-text">{title}</p>
      <p className="mt-2">{body}</p>
    </div>
  );
}
