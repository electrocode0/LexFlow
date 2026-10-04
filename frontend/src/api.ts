export interface Contract {
  id: string;
  title: string;
  contract_type: string | null;
  status: string;
  counterparty: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentRecord {
  id: string;
  contract_id: string;
  file_name: string;
  mime_type: string | null;
  storage_path: string | null;
  raw_text: string | null;
  created_at: string;
}

export interface Citation {
  document_id: string;
  chunk_id: string;
  chunk_index: number;
  text: string;
}

export interface AskResponse {
  answer: string;
  answerable: boolean;
  citations: Citation[];
}

export interface ContractInput {
  title: string;
  contract_type: string | null;
  counterparty: string | null;
}

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new Error("Could not reach LexFlow. Check that the API is running.");
  }

  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) message = payload.detail;
    } catch {
      // Keep the status-based message when the server did not return JSON.
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
}

export function listContracts(): Promise<Contract[]> {
  return request<Contract[]>("/contracts");
}

export function createContract(input: ContractInput): Promise<Contract> {
  return request<Contract>("/contracts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function getContract(contractId: string): Promise<Contract> {
  return request<Contract>(`/contracts/${contractId}`);
}

export function listDocuments(contractId: string): Promise<DocumentRecord[]> {
  return request<DocumentRecord[]>(`/contracts/${contractId}/documents`);
}

export function uploadDocument(
  contractId: string,
  file: File,
): Promise<DocumentRecord> {
  const form = new FormData();
  form.append("file", file);
  return request<DocumentRecord>(`/contracts/${contractId}/documents`, {
    method: "POST",
    body: form,
  });
}

export function askContract(
  contractId: string,
  question: string,
): Promise<AskResponse> {
  return request<AskResponse>(`/contracts/${contractId}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
}