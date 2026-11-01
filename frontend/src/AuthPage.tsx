import { FormEvent, useState } from "react";
import { ArrowRight, BookOpen } from "lucide-react";
import { authenticate, type Session } from "./api";

export default function AuthPage({ onAuthenticated }: { onAuthenticated: (session: Session) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      onAuthenticated(await authenticate(mode, username.trim(), password));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "无法完成登录");
    } finally {
      setPending(false);
    }
  }

  return <div className="auth-layout">
    <div className="auth-brand"><div className="brand-symbol"><BookOpen size={23} /></div><span>研岸 <small>ASHORE</small></span></div>
    <main className="auth-main">
      <h1>{mode === "login" ? "欢迎回来" : "加入研岸"}</h1>
      <p className="muted">继续你的考研数学学习。</p>
      <div className="auth-switch" role="group" aria-label="账号操作">
        <button type="button" className={mode === "login" ? "active" : ""} onClick={() => { setMode("login"); setError(""); }}>登录</button>
        <button type="button" className={mode === "register" ? "active" : ""} onClick={() => { setMode("register"); setError(""); }}>注册</button>
      </div>
      <form onSubmit={submit}>
        <label htmlFor="username">用户名</label>
        <input id="username" autoComplete="username" minLength={mode === "register" ? 2 : undefined} maxLength={32} required value={username} onChange={event => setUsername(event.target.value)} placeholder="输入用户名" />
        <label htmlFor="password">密码</label>
        <input id="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={mode === "register" ? 6 : undefined} required value={password} onChange={event => setPassword(event.target.value)} placeholder="输入密码" />
        {error ? <p className="error" role="alert">{error}</p> : null}
        <button className="primary wide" disabled={pending} type="submit">{pending ? "请稍候…" : mode === "login" ? "登录" : "创建账号"} <ArrowRight size={17} /></button>
      </form>
    </main>
    <footer>研岸 · 考研数学学习工作台</footer>
  </div>;
}
