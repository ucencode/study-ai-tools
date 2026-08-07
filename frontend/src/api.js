/**
 * API client. Generation endpoints are POST + Server-Sent Events, so they're
 * read with fetch + a ReadableStream reader rather than `EventSource` (which
 * can only issue GETs and couldn't carry a whole curriculum in the body).
 */

async function request(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* non-JSON error body — keep the status text */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
}

export const getHealth = () => request("/api/health");
export const getConfig = () => request("/api/config");
export const getModels = () => request("/api/models");
export const getInputs = () => request("/api/slides/inputs");
export const getOutputs = () => request("/api/outputs");
export const getOutput = (tool, name) =>
  request(`/api/outputs/${encodeURIComponent(tool)}/${encodeURIComponent(name)}`);

export const downloadUrl = (tool, name) =>
  `/api/outputs/${encodeURIComponent(tool)}/${encodeURIComponent(name)}?download=true`;

export const postJSON = (path, body) =>
  request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export function uploadPdf(file) {
  const form = new FormData();
  form.append("file", file);
  return request("/api/slides/upload", { method: "POST", body: form });
}

/** Parse one SSE frame into `{ type, data }`, or null for comments/blanks. */
function parseFrame(frame) {
  let type = "message";
  const dataLines = [];
  for (const line of frame.split("\n")) {
    if (!line || line.startsWith(":")) continue; // heartbeat / comment
    if (line.startsWith("event:")) type = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return null;
  try {
    return { type, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return { type, data: { text: dataLines.join("\n") } };
  }
}

/**
 * POST `body` to `path` and invoke `onEvent` for every SSE frame as it lands.
 * Resolves once the server closes the stream.
 */
export async function streamSSE(path, { body, signal, onEvent }) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const parsed = await res.json();
      if (parsed.detail) detail = JSON.stringify(parsed.detail);
    } catch {
      /* keep the status line */
    }
    throw new Error(detail);
  }
  if (!res.body) throw new Error("this browser cannot read streaming responses");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    // \r\n is legal in SSE; normalize so one split rule covers both
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

    let split;
    while ((split = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      const event = parseFrame(frame);
      if (event) onEvent(event);
    }
  }

  const tail = parseFrame(buffer.trim());
  if (tail) onEvent(tail);
}
