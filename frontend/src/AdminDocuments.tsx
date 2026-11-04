import { FormEvent, useCallback, useEffect, useState } from "react";
import { FileText, RefreshCw, Upload } from "lucide-react";
import {
  getAdminDocuments, reindexAdminDocument, uploadAdminDocument,
  type DocumentItem, type Session,
} from "./api";
import { formatTime } from "./format";

const PAGE_SIZE = 20;
const statusLabels: Record<string, string> = {
  pending: "待处理",
  processing: "处理中",
  ready: "已入库",
  failed: "失败",
  archived: "已归档",
};

export default function AdminDocuments({ session }: { session: Session }) {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [uploading, setUploading] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const page = await getAdminDocuments(offset, PAGE_SIZE, session.token);
      setDocuments(page.items);
      setTotal(page.total);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "文档列表加载失败");
    } finally {
      setLoading(false);
    }
  }, [offset, session.token]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!documents.some(item => item.status === "pending" || item.status === "processing")) return;
    const timer = window.setInterval(() => { void load(); }, 4000);
    return () => window.clearInterval(timer);
  }, [documents, load]);

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || uploading) return;
    setUploading(true);
    setError("");
    try {
      await uploadAdminDocument(file, title, session.token);
      setFile(null);
      setTitle("");
      setOffset(0);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "文档上传失败");
    } finally {
      setUploading(false);
    }
  }

  async function reindex(document: DocumentItem) {
    if (busyId !== null) return;
    if (!window.confirm(`确定重新入库“${document.title}”吗？`)) return;
    setBusyId(document.id);
    setError("");
    try {
      await reindexAdminDocument(document.id, session.token);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "重新入库失败");
    } finally {
      setBusyId(null);
    }
  }

  return <>
    <form className="admin-upload" onSubmit={upload}>
      <div>
        <label htmlFor="admin-title">文档标题</label>
        <input id="admin-title" value={title} onChange={event => setTitle(event.target.value)} placeholder="留空则使用文件名" />
      </div>
      <div>
        <label htmlFor="admin-file">知识库文件</label>
        <input id="admin-file" type="file" accept=".pdf,.md,.txt" onChange={event => setFile(event.target.files?.[0] ?? null)} />
        <small>{file ? file.name : "支持 PDF / Markdown / TXT，最大 20 MB"}</small>
      </div>
      <button className="primary" type="submit" disabled={!file || uploading}>
        <Upload size={16} />{uploading ? "正在上传…" : "上传并入库"}
      </button>
    </form>

    <div className="admin-list-toolbar">
      <span>共 {total} 个文档</span>
      <button className="secondary-button" type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={15} />刷新</button>
    </div>
    {error ? <div className="notice error-notice" role="alert">{error}</div> : null}
    {loading && !documents.length ? <div className="state-message">正在加载文档…</div> : documents.length ? <div className="admin-document-list">
      {documents.map(item => <article className="admin-document-row" key={item.id}>
        <span className="admin-document-icon"><FileText size={18} /></span>
        <div className="admin-document-copy">
          <strong>{item.title}</strong>
          <span>{item.file_name}</span>
          {item.error_message ? <small>{item.error_message}</small> : null}
        </div>
        <span className={`admin-doc-status ${item.status}`}>{statusLabels[item.status] ?? item.status}</span>
        <span className="admin-document-meta">{item.version_count} 版本 · {item.chunk_count} 切片</span>
        <time>{formatTime(item.updated_at)}</time>
        <button className="admin-action-button" type="button" disabled={busyId !== null} onClick={() => void reindex(item)}>
          <RefreshCw size={14} />{busyId === item.id ? "提交中…" : "重新入库"}
        </button>
      </article>)}
    </div> : <p className="admin-empty">还没有上传文档</p>}

    <div className="admin-pagination">
      <button className="secondary-button" type="button" disabled={offset === 0 || loading} onClick={() => setOffset(value => Math.max(0, value - PAGE_SIZE))}>上一页</button>
      <span className="admin-page-number">第 {Math.floor(offset / PAGE_SIZE) + 1} 页</span>
      <button className="secondary-button" type="button" disabled={offset + PAGE_SIZE >= total || loading} onClick={() => setOffset(value => value + PAGE_SIZE)}>下一页</button>
    </div>
  </>;
}
