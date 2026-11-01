import { FormEvent, useEffect, useRef, useState } from "react";
import { ArrowRight, ArrowUp, BookOpen, MessageCircle, PanelLeftClose, PanelLeftOpen, Plus, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import { clearConversations, createConversation, deleteConversation, getConversationMessages, listConversations, streamAsk, type AnswerData, type Conversation, type Session } from "./api";
import AnswerSources from "./AnswerSources";
import MathText from "./MathText";

type Entry = {
  role: "user" | "assistant"; content: string; intent?: string;
  data?: AnswerData; streaming?: boolean;
};

export default function ChatPage({ session }: { session: Session }) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [historyError, setHistoryError] = useState("");
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(true);
  const end = useRef<HTMLDivElement>(null);
  const controller = useRef<AbortController | null>(null);
  const historyBusy = pending || loadingHistory || deletingId !== null || creating;

  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [entries, pending]);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    let alive = true;
    listConversations(session.token).then(async ({ items }) => {
      if (alive) {
        setConversations(items);
        try {
          if (items.length) {
            const { items: messages } = await getConversationMessages(items[0].id, session.token);
            if (alive) {
              setEntries(messages.map(item => ({ role: item.role, content: item.content,
                intent: item.response_data?.intent, data: item.response_data?.data })));
              setActiveId(items[0].id);
            }
          }
        } catch (cause) {
          if (alive) setHistoryError(cause instanceof Error ? cause.message : "读取会话失败");
        } finally {
          if (alive) setLoadingHistory(false);
        }
      }
    }).catch((cause: Error) => { if (alive) { setHistoryError(cause.message); setLoadingHistory(false); } });
    return () => { alive = false; };
  }, [session.token]);

  async function openConversation(id: number) {
    if (historyBusy || id === activeId) return;
    setHistoryError("");
    try {
      const { items } = await getConversationMessages(id, session.token);
      setEntries(items.map(item => ({ role: item.role, content: item.content,
        intent: item.response_data?.intent, data: item.response_data?.data })));
      setActiveId(id);
      setDraft("");
      setError("");
    } catch (cause) {
      setHistoryError(cause instanceof Error ? cause.message : "读取会话失败");
    }
  }

  async function newConversation() {
    if (historyBusy) return;
    setCreating(true);
    setHistoryError("");
    try {
      const created = await createConversation(session.token);
      try {
        const { items } = await listConversations(session.token);
        setConversations(items);
      } catch (cause) {
        setConversations(current => [created, ...current.filter(item => item.id !== created.id)]);
        setHistoryError(cause instanceof Error ? cause.message : "刷新历史会话失败");
      }
      setActiveId(created.id);
      setEntries([]);
      setDraft("");
      setError("");
    } catch (cause) {
      setHistoryError(cause instanceof Error ? cause.message : "新建会话失败");
    } finally {
      setCreating(false);
    }
  }

  async function removeHistory() {
    if (historyBusy || !window.confirm("确定清除所有历史会话吗？清除后无法恢复。")) return;
    try {
      await clearConversations(session.token);
      setConversations([]);
      setActiveId(null);
      setEntries([]);
      setDraft("");
      setHistoryError("");
    } catch (cause) {
      setHistoryError(cause instanceof Error ? cause.message : "清除历史失败");
    }
  }

  async function deleteConversationItem(id: number) {
    if (historyBusy || !window.confirm("是否删除此次对话？")) return;
    setDeletingId(id);
    setHistoryError("");
    try {
      await deleteConversation(id, session.token);
      const remaining = conversations.filter(item => item.id !== id);
      setConversations(remaining);
      if (activeId === id) {
        setDraft("");
        setError("");
        if (remaining.length) {
          const { items } = await getConversationMessages(remaining[0].id, session.token);
          setEntries(items.map(item => ({ role: item.role, content: item.content,
            intent: item.response_data?.intent, data: item.response_data?.data })));
          setActiveId(remaining[0].id);
        } else {
          setEntries([]);
          setActiveId(null);
        }
      }
    } catch (cause) {
      setHistoryError(cause instanceof Error ? cause.message : "删除会话失败");
    } finally {
      setDeletingId(null);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || historyBusy) return;
    let conversationId = activeId;
    if (conversationId === null) {
      try {
        const created = await createConversation(session.token);
        conversationId = created.id;
        setActiveId(created.id);
        setConversations(current => [created, ...current]);
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "新建会话失败");
        return;
      }
    }
    setDraft("");
    setError("");
    setEntries(current => [...current,
      { role: "user", content: message },
      { role: "assistant", content: "", intent: "qa", data: {}, streaming: true },
    ]);
    setPending(true);
    let done = false;
    const abort = new AbortController();
    controller.current = abort;

    function updateAnswer(patch: (entry: Entry) => Entry) {
      setEntries(current => {
        const next = [...current];
        const last = next.length - 1;
        if (next[last]?.role !== "assistant") return current;
        next[last] = patch(next[last]);
        return next;
      });
    }

    try {
      await streamAsk(session.user.id, message, session.token, event => {
        if (event.type === "meta") {
          updateAnswer(entry => ({
            ...entry,
            intent: event.intent,
            data: { ...entry.data, knowledge_point: event.knowledge_point },
          }));
        } else if (event.type === "token") {
          updateAnswer(entry => ({ ...entry, content: entry.content + event.text }));
        } else if (event.type === "done") {
          done = true;
          updateAnswer(() => ({
            role: "assistant", content: event.result.reply, intent: event.result.intent,
            data: event.result.data, streaming: false,
          }));
        } else {
          throw new Error(event.message);
        }
      }, abort.signal, conversationId);
      if (!done) throw new Error("流式连接意外结束，请重试。");
      try {
        const { items } = await listConversations(session.token);
        setConversations(items);
      } catch (cause) {
        setHistoryError(cause instanceof Error ? cause.message : "刷新历史会话失败");
      }
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setEntries(current => {
        const next = [...current];
        if (next[next.length - 1]?.role === "assistant" && next[next.length - 1]?.streaming) next.pop();
        if (next[next.length - 1]?.role === "user" && next[next.length - 1]?.content === message) next.pop();
        return next;
      });
      setDraft(message);
      setError(cause instanceof Error ? cause.message : "答疑暂时不可用");
    } finally {
      controller.current = null;
      setPending(false);
    }
  }

  return <div className={`chat-layout${historyOpen ? "" : " history-collapsed"}`}>
    {historyOpen ? <aside className="history-pane" aria-label="历史会话">
      <div className="history-header">
        <h2>历史会话</h2>
        <div className="history-header-actions">
          <button className="history-collapse" type="button" onClick={() => setHistoryOpen(false)} title="收起历史会话" aria-label="收起历史会话"><PanelLeftClose size={16} /></button>
          <button className="history-new" type="button" onClick={() => void newConversation()} disabled={historyBusy} title="新对话" aria-label="新对话"><Plus size={17} /></button>
        </div>
      </div>
      <div className="history-list">
        {loadingHistory ? <p className="history-empty">正在加载…</p> : conversations.length === 0 ? <p className="history-empty">暂无历史会话</p> : conversations.map(item =>
          <div key={item.id} className={`history-item-row${activeId === item.id ? " active" : ""}`}>
            <button type="button" className="history-item" onClick={() => void openConversation(item.id)} disabled={historyBusy} title={item.title} aria-current={activeId === item.id ? "true" : undefined}>{item.title}</button>
            <button type="button" className="history-delete" onClick={() => void deleteConversationItem(item.id)} disabled={historyBusy} title="删除此次对话" aria-label={`删除会话：${item.title}`}><Trash2 size={15} /></button>
          </div>)}
      </div>
      {historyError ? <p className="error" role="alert">{historyError}</p> : null}
      <div className="history-actions">
        <button type="button" className="history-clear" onClick={() => void removeHistory()} disabled={historyBusy || conversations.length === 0}><Trash2 size={16} />清除历史会话</button>
      </div>
    </aside> : null}
  <section className="chat-page" aria-label="答疑">
    <header className="section-header">
      <div className="chat-heading">
        {!historyOpen ? <button className="icon-button history-expand" type="button" onClick={() => setHistoryOpen(true)} title="展开历史会话" aria-label="展开历史会话"><PanelLeftOpen size={19} /></button> : null}
        <div><h1>答疑</h1><p>提出问题，沿着知识点继续学。</p></div>
      </div>
    </header>
    <div className="conversation" aria-live="polite">
      {entries.length === 0 ? <div className="chat-empty"><span className="empty-icon"><MessageCircle size={24} /></span><h2>从一个问题开始</h2><p>例如：定积分换元时，积分上下限怎么变化？</p></div> : entries.map((entry, index) => <div key={index} className={`message ${entry.role}`}>
        <span className="message-author">{entry.role === "user" ? "你" : "研岸"}{entry.intent && entry.intent !== "qa" ? ` · ${entry.intent}` : ""}{entry.streaming ? <span className="stream-label">生成中</span> : null}</span>
        <div className={`message-content${entry.streaming ? " streaming" : ""}`}>
          {entry.data?.knowledge_point ? <div className="answer-kp"><BookOpen size={15} /><span>知识点</span><strong>{entry.data.knowledge_point}</strong></div> : null}
          {entry.streaming && !entry.content ? <p className="muted">正在思考…</p> : <MathText>{entry.content}</MathText>}
          {entry.data?.sources?.length ? <AnswerSources sources={entry.data.sources} /> : null}
          {entry.data?.next_action?.knowledge_point ? <Link className="answer-action" to={`/practice?knowledge_point=${encodeURIComponent(entry.data.next_action.knowledge_point)}`}>
            练一道「{entry.data.next_action.knowledge_point}」题<ArrowRight size={16} />
          </Link> : null}
        </div>
      </div>)}
      <div ref={end} />
    </div>
    <div className="compose-area">{error ? <p className="error" role="alert">{error}<span className="error-hint">问题已放回输入框，可直接修改后重试。</span></p> : null}
      <form className="composer" onSubmit={submit}>
        <label className="sr-only" htmlFor="question">输入问题</label>
        <input id="question" autoComplete="off" value={draft} onChange={event => setDraft(event.target.value)} placeholder="输入你的数学问题…" />
        <button className="send-button" title="发送问题" aria-label="发送问题" disabled={!draft.trim() || historyBusy} type="submit"><ArrowUp size={20} /></button>
      </form>
    </div>
  </section></div>;
}
