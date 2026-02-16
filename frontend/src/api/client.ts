import axios from "axios";

const API_BASE = "http://localhost:8000/api";

const api = axios.create({
  baseURL: API_BASE,
  timeout: 300_000, // 5 min – chunked LLM calls + vision can be slow
});

// ── Documents ──
export async function parseDocument(file: File) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post("/documents/parse", form);
  return data;
}

export function getFigureImageUrl(docId: string, index: number) {
  return `${API_BASE}/documents/${docId}/figure/${index}`;
}

// ── Workflows ──
export async function listWorkflows() {
  const { data } = await api.get("/workflows");
  return data;
}

export async function getWorkflow(id: string) {
  const { data } = await api.get(`/workflows/${id}`);
  return data;
}

export interface WorkflowCreate {
  name: string;
  description?: string;
  prompt_template: string;
  output_schema_json: string;
  created_by?: string;
}

export async function createWorkflow(body: WorkflowCreate) {
  const { data } = await api.post("/workflows", body);
  return data;
}

export async function deleteWorkflow(id: string) {
  const { data } = await api.delete(`/workflows/${id}`);
  return data;
}

// ── Runs ──
export interface RunCreate {
  workflow_id: string;
  doc_id: string;
  input_text?: string;
}

export async function executeRun(body: RunCreate) {
  const { data } = await api.post("/runs", body);
  return data;
}

export function getRunDownloadUrl(runId: string) {
  return `${API_BASE}/runs/${runId}/download`;
}

export function getRunEnrichedMdUrl(runId: string) {
  return `${API_BASE}/runs/${runId}/download-md`;
}

export default api;
