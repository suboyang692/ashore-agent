import { useEffect, useState } from "react";
import { BookOpen, ClipboardList, GraduationCap, LogOut, MessageCircle, NotebookPen, ShieldCheck, Target } from "lucide-react";
import { Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { ApiError, getMe, type Session } from "./api";
import AdminPage from "./AdminPage";
import AuthPage from "./AuthPage";
import ChatPage from "./ChatPage";
import MistakesPage from "./MistakesPage";
import PlanPage from "./PlanPage";
import PracticePage from "./PracticePage";
import ProfilePage from "./ProfilePage";
import { loadSession, saveSession } from "./session";

export default function App() {
  const [session, setSession] = useState<Session | null>(loadSession);
  const location = useLocation();

  function updateSession(value: Session | null) { saveSession(value); setSession(value); }
  useEffect(() => {
    if (!session) return;
    let alive = true;
    getMe(session.token).then(user => {
      if (alive) updateSession({ ...session, user });
    }).catch(cause => {
      if (alive && cause instanceof ApiError && (cause.status === 401 || cause.status === 403)) {
        updateSession(null);
      }
    });
    return () => { alive = false; };
  }, [session?.token]);
  if (!session) return <Routes><Route path="*" element={<AuthPage onAuthenticated={updateSession} />} /></Routes>;
  const sections = [
    { path: "/chat", label: "答疑", icon: MessageCircle },
    { path: "/practice", label: "练习", icon: NotebookPen },
    { path: "/mistakes", label: "错题", icon: Target },
    { path: "/plan", label: "规划", icon: ClipboardList },
    { path: "/profile", label: "学情", icon: GraduationCap },
    ...(session.user.role === "admin"
      ? [{ path: "/admin", label: "管理", icon: ShieldCheck }]
      : []),
  ];

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="sidebar-top"><span className="brand-symbol"><BookOpen size={22} /></span><div className="brand-name">研岸 <small>ASHORE</small></div></div>
      <nav aria-label="主导航" className={session.user.role === "admin" ? "admin-nav" : undefined}>{sections.map(({ path, label, icon: Icon }) => <NavLink key={path} to={path} className={({ isActive }) => `nav-link${isActive ? " selected" : ""}`}><Icon size={19} strokeWidth={1.9} /><span>{label}</span></NavLink>)}</nav>
      <div className="sidebar-bottom"><div className="account"><span className="avatar">{session.user.username.slice(0, 1).toUpperCase()}</span><span className="account-name">{session.user.username}</span></div><button className="icon-button" type="button" title="退出登录" aria-label="退出登录" onClick={() => updateSession(null)}><LogOut size={18} /></button></div>
    </aside>
    <main className="main-area">
      <div className="retained-page" hidden={location.pathname !== "/chat"}><ChatPage key={session.user.id} session={session} /></div>
      <div className="retained-page" hidden={location.pathname !== "/practice"}><PracticePage key={session.user.id} session={session} /></div>
      <Routes><Route path="/chat" element={null} /><Route path="/practice" element={null} /><Route path="/mistakes" element={<MistakesPage session={session} />} /><Route path="/plan" element={<PlanPage session={session} />} /><Route path="/profile" element={<ProfilePage session={session} />} /><Route path="/admin" element={session.user.role === "admin" ? <AdminPage session={session} /> : <Navigate to="/chat" replace />} /><Route path="*" element={<Navigate to="/chat" replace />} /></Routes>
    </main>
  </div>;
}
