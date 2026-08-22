// Display helpers. Backend timestamps are naive local ISO strings, which
// `new Date` reads as local time — the same clock that wrote them.

export function relativeTime(value) {
  if (!value) return "";
  const then = value instanceof Date ? value : new Date(value);
  const seconds = Math.max(0, Math.round((Date.now() - then.getTime()) / 1000));
  if (seconds < 10) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function clockTime(value) {
  if (!value) return "—";
  return new Date(value).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function duration(from, to) {
  if (!from || !to) return null;
  const seconds = Math.max(0, Math.round((new Date(to) - new Date(from)) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

export function fileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function languageLabel(option) {
  // The backend's "auto" label is a prompt fragment ("the same language as the source
  // content"), which is not something anyone wants to read inside a select.
  const label = option.value === "auto" ? "Match the source language" : option.label;
  return option.experimental ? `${label} · experimental` : label;
}
