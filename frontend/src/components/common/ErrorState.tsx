export function ErrorState({ message }: { message: string }) {
  return <div className="rounded-xl border border-danger/20 bg-danger/10 p-4 text-sm text-danger">{message}</div>;
}
