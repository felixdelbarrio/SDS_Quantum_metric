const API_BASE =
  import.meta.env.VITE_API_BASE ??
  (import.meta.env.DEV
    ? "http://127.0.0.1:8765/api"
    : `${window.location.origin}/api`);

type JsonValue =
  | Record<string, unknown>
  | unknown[]
  | string
  | number
  | boolean
  | null;

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  return handle<T>(response);
}

export async function apiPost<T>(path: string, body?: JsonValue): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return handle<T>(response);
}

export async function apiPut<T>(path: string, body: JsonValue): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handle<T>(response);
}

export async function apiDelete<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { method: "DELETE" });
  return handle<T>(response);
}

export async function apiDownload(
  path: string,
  body?: JsonValue,
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  const disposition = response.headers.get("content-disposition") ?? "";
  const filename =
    /filename="?([^";]+)"?/i.exec(disposition)?.[1] ?? "quantum-dataset.zip";
  return { blob: await response.blob(), filename };
}

export async function apiUpload<T>(
  path: string,
  formData: FormData,
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    body: formData,
  });
  return handle<T>(response);
}

async function handle<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return (await response.json()) as T;
}
