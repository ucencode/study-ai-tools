/**
 * API client. Generation is job-based: POST a job, then watch it over Server-Sent
 * Events. The event stream is read with fetch + a ReadableStream reader rather
 * than `EventSource`, so the same parser serves it and the request can be
 * aborted (detached) without ceremony.
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
  return res.status === 204 ? null : res.json();
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

// ── jobs ─────────────────────────────────────────────────────────────────────

export const submitJob = (path, body) => postJSON(path, body);
export const listJobs = (tool) =>
  request(`/api/jobs${tool ? `?tool=${encodeURIComponent(tool)}` : ""}`);
export const getJob = (id) => request(`/api/jobs/${encodeURIComponent(id)}`);
export const cancelJob = (id) =>
  request(`/api/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" });
export const deleteJob = (id) =>
  request(`/api/jobs/${encodeURIComponent(id)}`, { method: "DELETE" });

/** Watch a job: replays from `from`, then follows it live until it ends. */
export function streamJob(id, { from = 0, signal, onEvent }) {
  return streamSSE(`/api/jobs/${encodeURIComponent(id)}/events?from=${from}`, {
    method: "GET",
    signal,
    onEvent,
  });
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
 * Open the SSE stream at `path` and invoke `onEvent` for every frame as it lands.
 * Resolves once the server closes the stream.
 */
export async function streamSSE(path, { method = "POST", body, signal, onEvent }) {
  const headers = { Accept: "text/event-stream" };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
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
