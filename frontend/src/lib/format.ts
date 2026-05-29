export function formatPercent(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "--";
  return `${(value * 100).toFixed(0)}%`;
}

export function formatTime(timestamp: number | null | undefined) {
  if (!timestamp) return "--";
  return new Date(timestamp * 1000).toLocaleString();
}

export function titleCase(value: string) {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}
