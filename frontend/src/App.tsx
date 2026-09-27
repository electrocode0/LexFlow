import {
  ArrowLeft,
  ArrowUpRight,
  Check,
  ChevronRight,
  CircleAlert,
  FileText,
  LoaderCircle,
  Plus,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  askContract,
  createContract,
  getContract,
  listContracts,
  listDocuments,
  uploadDocument,
} from "./api";
import type { AskResponse, Citation, Contract, DocumentRecord } from "./api";

interface AnswerTurn {
  question: string;
  result: AskResponse;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong.";
}

function App() {
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeContract, setActiveContract] = useState<Contract | null>(null);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [loadingContracts, setLoadingContracts] = useState(true);
  const [loadingWorkspace, setLoadingWorkspace] = useState(false);
  const [pageError, setPageError] = useState("");
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState("");
  const [turn, setTurn] = useState<AnswerTurn | null>(null);
  const [expandedCitation, setExpandedCitation] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let current = true;
    listContracts()
      .then((items) => {
        if (current) setContracts(items);
      })
      .catch((error: unknown) => {
        if (current) setPageError(errorMessage(error));
      })
      .finally(() => {
        if (current) setLoadingContracts(false);
      });
    return () => {
      current = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setActiveContract(null);
      setDocuments([]);
      return;
    }
    let current = true;
    setLoadingWorkspace(true);
    setPageError("");
    Promise.all([getContract(selectedId), listDocuments(selectedId)])
      .then(([contract, records]) => {
        if (!current) return;
        setActiveContract(contract);
        setDocuments(records);
      })
      .catch((error: unknown) => {
        if (current) setPageError(errorMessage(error));
      })
      .finally(() => {
        if (current) setLoadingWorkspace(false);
      });
    return () => {
      current = false;
    };
  }, [selectedId]);

  function openContract(contractId: string) {
    setPageError("");
    setTurn(null);
    setAskError("");
    setSelectedId(contractId);
  }

  function returnToDashboard() {
    setPageError("");
    setSelectedId(null);
    setTurn(null);
    setExpandedCitation(null);
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const title = String(data.get("title") ?? "").trim();
    if (!title) {
      setCreateError("Enter a contract name.");
      return;
    }
    setIsCreating(true);
    setCreateError("");
    try {
      const contract = await createContract({
        title,
        contract_type: String(data.get("contract_type") ?? "") || null,
        counterparty: String(data.get("counterparty") ?? "").trim() || null,
      });
      setContracts((current) => [contract, ...current]);
      setIsCreateOpen(false);
      setSelectedId(contract.id);
    } catch (error) {
      setCreateError(errorMessage(error));
    } finally {
      setIsCreating(false);
    }
  }

  async function handleUpload(file?: File) {
    if (!file || !selectedId) return;
    setUploadError("");
    if (!file.name.toLowerCase().endsWith(".txt")) {
      setUploadError("Choose a .txt document.");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setUploadError("The file must be 10 MB or smaller.");
      return;
    }
    setUploading(true);
    try {
      await uploadDocument(selectedId, file);
      setDocuments(await listDocuments(selectedId));
      setTurn(null);
    } catch (error) {
      setUploadError(errorMessage(error));
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function handleAsk(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedQuestion = question.trim();
    if (!selectedId || !normalizedQuestion) {
      setAskError("Enter a question to continue.");
      return;
    }
    setAsking(true);
    setAskError("");
    setTurn(null);
    setExpandedCitation(null);
    try {
      const result = await askContract(selectedId, normalizedQuestion);
      setTurn({ question: normalizedQuestion, result });
      setQuestion("");
    } catch (error) {
      setAskError(errorMessage(error));
    } finally {
      setAsking(false);
    }
  }

  const documentNames = new Map(documents.map((document) => [document.id, document.file_name]));

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button className="brand-lockup" onClick={returnToDashboard} aria-label="LexFlow home">
          <span className="brand-symbol">L</span>
          <span className="brand-name">lexflow<span>.</span></span>
        </button>
        <div className="sidebar-rule" />
        <div className="sidebar-caption">LEGAL OPERATIONS</div>
        <button
          className={`nav-item ${selectedId ? "" : "nav-item-active"}`}
          onClick={returnToDashboard}
        >
          <FileText size={17} strokeWidth={1.8} />
          <span>Contracts</span>
          <span className="nav-count">{contracts.length}</span>
        </button>
        <div className="sidebar-bottom">
          <div className="secure-mark"><ShieldCheck size={15} /> Private workspace</div>
          <span className="sidebar-version">LEXFLOW · 0.2</span>
        </div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <div className="breadcrumbs">
            <span>Workspace</span>
            <ChevronRight size={14} />
            <span className={selectedId ? "" : "breadcrumb-current"}>
              {activeContract?.title ?? (selectedId ? "Contract" : "Contracts")}
            </span>
          </div>
          <div className="topbar-status"><span className="status-dot" /> LOCAL WORKSPACE</div>
        </header>

        {pageError && (
          <div className="global-error" role="alert">
            <CircleAlert size={17} /> <span>{pageError}</span>
            <button onClick={() => setPageError("")} aria-label="Dismiss error"><X size={16} /></button>
          </div>
        )}

        {selectedId ? (
          loadingWorkspace || !activeContract ? (
            <main className="page-content loading-view" aria-live="polite">
              <LoaderCircle className="spin" size={24} />
              <span>Opening contract…</span>
            </main>
          ) : (
            <ContractWorkspace
              contract={activeContract}
              documents={documents}
              fileInput={fileInput}
              uploading={uploading}
              uploadError={uploadError}
              onUpload={handleUpload}
              question={question}
              setQuestion={setQuestion}
              asking={asking}
              askError={askError}
              turn={turn}
              expandedCitation={expandedCitation}
              setExpandedCitation={setExpandedCitation}
              documentNames={documentNames}
              onAsk={handleAsk}
              onBack={returnToDashboard}
            />
          )
        ) : (
          <Dashboard
            contracts={contracts}
            loading={loadingContracts}
            onOpen={openContract}
            onCreate={() => {
              setCreateError("");
              setIsCreateOpen(true);
            }}
          />
        )}
      </div>

      {isCreateOpen && (
        <div className="modal-scrim" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setIsCreateOpen(false);
        }}>
          <section className="create-dialog" role="dialog" aria-modal="true" aria-labelledby="create-title">
            <div className="dialog-heading">
              <div>
                <span className="eyebrow">NEW MATTER</span>
                <h2 id="create-title">Create contract</h2>
              </div>
              <button className="icon-button" onClick={() => setIsCreateOpen(false)} aria-label="Close dialog">
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleCreate} className="create-form">
              <label className="field-label" htmlFor="contract-title">Contract name <span>*</span></label>
              <input id="contract-title" name="title" maxLength={500} placeholder="e.g. Mutual NDA · Northstar" autoFocus />
              <label className="field-label" htmlFor="contract-type">Agreement type</label>
              <select id="contract-type" name="contract_type" defaultValue="NDA">
                <option value="NDA">Non-disclosure agreement</option>
                <option value="MSA">Master services agreement</option>
                <option value="SOW">Statement of work</option>
                <option value="Other">Other</option>
              </select>
              <label className="field-label" htmlFor="counterparty">Counterparty</label>
              <input id="counterparty" name="counterparty" maxLength={500} placeholder="Company or individual" />
              {createError && <p className="form-error" role="alert"><CircleAlert size={15} />{createError}</p>}
              <div className="dialog-actions">
                <button type="button" className="button-secondary" onClick={() => setIsCreateOpen(false)}>Cancel</button>
                <button type="submit" className="button-primary" disabled={isCreating}>
                  {isCreating ? <LoaderCircle className="spin" size={16} /> : <Plus size={16} />}
                  Create contract
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}

interface DashboardProps {
  contracts: Contract[];
  loading: boolean;
  onOpen: (contractId: string) => void;
  onCreate: () => void;
}

function Dashboard({ contracts, loading, onOpen, onCreate }: DashboardProps) {
  return (
    <main className="page-content">
      <div className="page-heading dashboard-heading">
        <div>
          <span className="eyebrow">DOCUMENT PORTFOLIO</span>
          <h1>Contracts</h1>
        </div>
        <button className="button-primary" onClick={onCreate}><Plus size={17} /> New contract</button>
      </div>

      <section className="contract-register" aria-labelledby="register-title">
        <div className="register-heading">
          <div>
            <h2 id="register-title">All contracts</h2>
            <span>{loading ? "Loading" : `${contracts.length} ${contracts.length === 1 ? "record" : "records"}`}</span>
          </div>
          <span className="register-caption">MOST RECENT FIRST</span>
        </div>
        {loading ? (
          <div className="table-loading"><LoaderCircle className="spin" size={20} /> Loading contracts</div>
        ) : contracts.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon"><FileText size={23} strokeWidth={1.6} /></div>
            <h3>No contracts yet</h3>
            <p>Your contract register is ready.</p>
            <button className="button-secondary" onClick={onCreate}><Plus size={16} /> Create a contract</button>
          </div>
        ) : (
          <>
            <div className="contract-table-head">
              <span>CONTRACT</span><span>COUNTERPARTY</span><span>TYPE</span><span>STATUS</span><span>UPDATED</span><span />
            </div>
            <div className="contract-rows">
              {contracts.map((contract) => (
                <button className="contract-row" key={contract.id} onClick={() => onOpen(contract.id)}>
                  <span className="contract-title-cell">
                    <span className="document-icon"><FileText size={18} /></span>
                    <span><strong>{contract.title}</strong><small>{contract.id.slice(0, 8)}</small></span>
                  </span>
                  <span className="table-value">{contract.counterparty || <span className="muted-value">Not specified</span>}</span>
                  <span><span className="type-pill">{contract.contract_type || "General"}</span></span>
                  <span><span className="status-pill"><span />{contract.status}</span></span>
                  <span className="table-date">{formatDate(contract.updated_at)}</span>
                  <span className="row-arrow"><ArrowUpRight size={17} /></span>
                </button>
              ))}
            </div>
          </>
        )}
      </section>
      <footer className="page-footer"><span>LEXFLOW</span><span>Contract intelligence workspace</span></footer>
    </main>
  );
}

interface WorkspaceProps {
  contract: Contract;
  documents: DocumentRecord[];
  fileInput: React.RefObject<HTMLInputElement | null>;
  uploading: boolean;
  uploadError: string;
  onUpload: (file?: File) => void;
  question: string;
  setQuestion: (question: string) => void;
  asking: boolean;
  askError: string;
  turn: AnswerTurn | null;
  expandedCitation: string | null;
  setExpandedCitation: (citationId: string | null) => void;
  documentNames: Map<string, string>;
  onAsk: (event: FormEvent<HTMLFormElement>) => void;
  onBack: () => void;
}

function ContractWorkspace(props: WorkspaceProps) {
  const {
    contract, documents, fileInput, uploading, uploadError, onUpload,
    question, setQuestion, asking, askError, turn, expandedCitation,
    setExpandedCitation, documentNames, onAsk, onBack,
  } = props;

  return (
    <main className="page-content workspace-page">
      <button className="back-link" onClick={onBack}><ArrowLeft size={16} /> All contracts</button>
      <div className="workspace-title-row">
        <div>
          <span className="eyebrow">{contract.contract_type || "CONTRACT"} · WORKSPACE</span>
          <h1>{contract.title}</h1>
          <div className="contract-meta">
            <span>{contract.counterparty || "Counterparty not specified"}</span>
            <span className="meta-divider" />
            <span>Created {formatDate(contract.created_at)}</span>
            <span className="status-pill"><span />{contract.status}</span>
          </div>
        </div>
        <div className="contract-reference">REF <strong>{contract.id.slice(0, 8).toUpperCase()}</strong></div>
      </div>

      <div className="workspace-grid">
        <section className="documents-panel" aria-labelledby="documents-title">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">SOURCE FILES</span>
              <h2 id="documents-title">Documents <span className="count-badge">{documents.length}</span></h2>
            </div>
            <button
              className="icon-action"
              onClick={() => fileInput.current?.click()}
              disabled={uploading}
              title="Upload a .txt document"
              aria-label="Upload a .txt document"
            >
              {uploading ? <LoaderCircle className="spin" size={17} /> : <Upload size={17} />}
            </button>
            <input
              ref={fileInput}
              className="visually-hidden"
              type="file"
              accept=".txt,text/plain"
              onChange={(event) => onUpload(event.target.files?.[0])}
              aria-label="Choose a text document"
            />
          </div>
          {uploadError && <p className="inline-error" role="alert"><CircleAlert size={15} />{uploadError}</p>}
          {documents.length === 0 ? (
            <div className="documents-empty">
              <div className="empty-icon small"><Upload size={19} /></div>
              <strong>No source files</strong>
              <span>Upload a text document to get started.</span>
              <button className="button-secondary compact" onClick={() => fileInput.current?.click()} disabled={uploading}>
                <Upload size={15} /> Upload .txt
              </button>
            </div>
          ) : (
            <ul className="document-list">
              {documents.map((document) => (
                <li className="document-row" key={document.id}>
                  <span className="document-icon"><FileText size={18} /></span>
                  <span className="document-details"><strong>{document.file_name}</strong><small>{formatDate(document.created_at)}</small></span>
                  <Check className="document-check" size={16} />
                </li>
              ))}
            </ul>
          )}
          <div className="source-note"><ShieldCheck size={15} /><span>Source text remains attached to this contract.</span></div>
        </section>

        <section className="ask-panel" aria-labelledby="ask-title">
          <div className="ask-heading">
            <div className="ask-icon"><Sparkles size={17} /></div>
            <div><span className="eyebrow">CONTRACT REVIEW</span><h2 id="ask-title">Ask LexFlow</h2></div>
            <span className="context-badge"><span /> THIS CONTRACT</span>
          </div>
          <form className="question-form" onSubmit={onAsk}>
            <label className="field-label" htmlFor="question-input">Your question</label>
            <textarea
              id="question-input"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="What are the confidentiality obligations?"
              maxLength={2000}
              rows={3}
            />
            <div className="question-form-footer">
              <span>{question.length}/2000</span>
              <button className="button-primary ask-button" type="submit" disabled={asking || !question.trim()}>
                {asking ? <LoaderCircle className="spin" size={16} /> : <Sparkles size={16} />}
                {asking ? "Reviewing…" : "Ask LexFlow"}
              </button>
            </div>
          </form>
          {askError && <p className="inline-error ask-error" role="alert"><CircleAlert size={15} />{askError}</p>}

          {asking ? (
            <div className="answer-loading" aria-live="polite"><LoaderCircle className="spin" size={21} /><span>Reviewing the retrieved contract sources…</span></div>
          ) : turn ? (
            <div className="answer-stack" aria-live="polite">
              <div className="question-echo">
                <span className="answer-label">YOUR QUESTION</span>
                <p>{turn.question}</p>
              </div>
              <div className="answer-block">
                <div className="answer-label"><Sparkles size={14} /> LEXFLOW ANSWER</div>
                <p className="answer-copy">{turn.result.answer}</p>
              </div>
              <div className="citation-section">
                <div className="citation-heading">
                  <span className="answer-label"><ShieldCheck size={14} /> VERIFIED SOURCES</span>
                  <span>{turn.result.citations.length} cited</span>
                </div>
                {turn.result.citations.length === 0 ? (
                  <p className="no-citations">No source passages support this answer.</p>
                ) : (
                  <div className="citation-list">
                    {turn.result.citations.map((citation, index) => (
                      <CitationItem
                        key={citation.chunk_id}
                        citation={citation}
                        index={index}
                        fileName={documentNames.get(citation.document_id) ?? "Contract source"}
                        expanded={expandedCitation === citation.chunk_id}
                        onToggle={() => setExpandedCitation(
                          expandedCitation === citation.chunk_id ? null : citation.chunk_id,
                        )}
                      />
                    ))}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="answer-placeholder">
              <div className="placeholder-rule" />
              <span className="eyebrow">GROUNDED REVIEW</span>
              <p>Answers are paired with source passages from this contract.</p>
            </div>
          )}
        </section>
      </div>
      <footer className="page-footer"><span>LEXFLOW</span><span>Only this contract is in scope</span></footer>
    </main>
  );
}

interface CitationItemProps {
  citation: Citation;
  index: number;
  fileName: string;
  expanded: boolean;
  onToggle: () => void;
}

function CitationItem({ citation, index, fileName, expanded, onToggle }: CitationItemProps) {
  return (
    <div className={`citation-item ${expanded ? "citation-expanded" : ""}`}>
      <button className="citation-trigger" onClick={onToggle} aria-expanded={expanded}>
        <span className="citation-number">{String(index + 1).padStart(2, "0")}</span>
        <span className="citation-label"><strong>{fileName}</strong><small>Chunk {citation.chunk_index + 1}</small></span>
        <span className="citation-action">{expanded ? "Hide passage" : "View passage"}<ChevronRight size={15} /></span>
      </button>
      {expanded && (
        <div className="verified-passage">
          <div className="verified-passage-label"><ShieldCheck size={14} /> VERIFIED SOURCE TEXT</div>
          <p><mark>{citation.text}</mark></p>
          <span className="source-id">SOURCE ID · {citation.chunk_id}</span>
        </div>
      )}
    </div>
  );
}

export default App;