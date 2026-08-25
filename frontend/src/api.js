// One function per endpoint, hand-written. Base is relative so the Vite proxy
// (dev) and any same-origin deployment use identical URLs.

const BASE = "/api";

// Records carry the underscored service name; URLs use the hyphenated one.
const SERVICE_PATH = {
  slide_summarizer: "slide-summarizer",
  curriculum_generator: "curriculum-generator",
};

export const SERVICE_LABEL = {
  slide_summarizer: "Slide summarizer",
  curriculum_generator: "Curriculum generator",
};

export const SLIDES = "slide_summarizer";
export const CURRICULUM = "curriculum_generator";

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function detailOf(body, fallback) {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  // 422 comes back as a list of validation errors.
  if (Array.isArray(detail)) {
    return detail.map((e) => `${(e.loc || []).slice(1).join(".")}: ${e.msg}`).join("; ");
  }
  return fallback;
}

async function request(path, options) {
  let response;
  try {
    response = await fetch(BASE + path, options);
  } catch (e) {
    // fetch only rejects when the request never reached the server.
    throw new ApiError(0, "connection unavailable");
  }
  if (response.status === 204) return null;

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(response.status, detailOf(body, `HTTP ${response.status}`));
  }
  return body;
}

function json(path, body) {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function servicePath(service) {
  const path = SERVICE_PATH[service];
  if (!path) throw new ApiError(0, `unknown service: ${service}`);
  return path;
}

export const getHealth = () => request("/health");
export const getConfig = () => request("/config");
export const getModels = () => request("/models");

// /models gives role lists as plain names but `models` as records. An unclassified
// model is an unknown capability, so falling back to the full list is something the
// form has to say out loud rather than substitute silently.
export function modelsForRole(models, role) {
  const listed = models?.[role] || [];
  if (listed.length > 0) return { options: listed, fallback: false };
  return { options: (models?.models || []).map((model) => model.name), fallback: true };
}

export const listJobs = (service) =>
  request(service ? `/jobs?service_name=${encodeURIComponent(service)}` : "/jobs");

export const getJob = (service, id) => request(`/${servicePath(service)}/jobs/${id}`);
export const getOutput = (service, id) => request(`/${servicePath(service)}/jobs/${id}/output`);

export const retryJob = (service, id) =>
  request(`/${servicePath(service)}/jobs/${id}/retry`, { method: "POST" });

export const deleteJob = (service, id) =>
  request(`/${servicePath(service)}/jobs/${id}`, { method: "DELETE" });

export const createSlideJob = (formData) =>
  request("/slide-summarizer/jobs", { method: "POST", body: formData });

export const createQuiz = (curriculum, model) =>
  json("/curriculum-generator/quiz", { curriculum, model });

export const createCurriculumJob = (payload) => json("/curriculum-generator/jobs", payload);

// Presets are settings only — never the deck, the curriculum, or the quiz.
export const listPresets = (service) => request(`/${servicePath(service)}/presets`);

export const savePreset = (service, name, settings) =>
  json(`/${servicePath(service)}/presets`, { name, settings });

export const deletePreset = (service, id) =>
  request(`/${servicePath(service)}/presets/${id}`, { method: "DELETE" });
