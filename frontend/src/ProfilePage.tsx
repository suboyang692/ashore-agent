import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRight, BookOpen, RefreshCw, Target } from "lucide-react";
import { Link } from "react-router-dom";
import { getProfile, type Profile, type Session } from "./api";
import { masteryPercent } from "./format";
import PageHeader from "./PageHeader";

function ProfileSkeleton() {
  return <div className="skeleton-stack" aria-label="正在加载学情">
    <div className="skeleton-row skeleton-short" />
    <div className="skeleton-row" />
    <div className="skeleton-row" />
    <div className="skeleton-row" />
  </div>;
}

export default function ProfilePage({ session }: { session: Session }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setProfile(await getProfile(session.user.id, session.token));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "学情加载失败");
    } finally {
      setLoading(false);
    }
  }, [session.token, session.user.id]);

  useEffect(() => { void load(); }, [load]);

  const items = profile?.items ?? [];
  const average = useMemo(() => {
    if (!items.length) return 0;
    return Math.round(items.reduce((sum, item) => sum + masteryPercent(item.mastery), 0) / items.length);
  }, [items]);
  const weak = profile?.weak_points ?? [];

  return <section className="workspace-page">
    <PageHeader title="学情" description="看清掌握度，把复习时间放在最需要的地方。" action={
      <button className="secondary-button" type="button" onClick={() => void load()} disabled={loading}>
        <RefreshCw size={16} />刷新
      </button>
    } />
    <div className="page-scroll">
      {error ? <div className="notice error-notice" role="alert">{error}</div> : null}
      {loading ? <ProfileSkeleton /> : items.length ? <>
        <section className="profile-overview">
          <div className="profile-overview-copy">
            <span className="field-label">当前学情</span>
            <strong>{items.length} 个知识点有练习记录</strong>
            <p>{weak.length ? `优先复习 ${weak.length} 个薄弱知识点，先从掌握度最低的开始。` : "当前没有明显薄弱项，继续保持练习节奏。"}</p>
          </div>
          <div className="profile-average">
            <span>平均掌握度</span>
            <strong>{average}%</strong>
          </div>
        </section>

        {weak.length ? <section className="weak-points">
          <div className="weak-points-head"><Target size={17} /><h2>优先复习</h2></div>
          <div className="weak-chip-list">
            {weak.slice(0, 6).map(point => <Link className="weak-chip" key={point} to={`/practice?knowledge_point=${encodeURIComponent(point)}`}>
              {point}<ArrowRight size={14} />
            </Link>)}
          </div>
        </section> : null}

        <section className="mastery-section">
          <div className="section-row-head"><div><BookOpen size={17} /><h2>知识点掌握度</h2></div><span>按掌握度从低到高</span></div>
          <div className="mastery-list">
            {items.map(item => {
              const percent = masteryPercent(item.mastery);
              return <article className="mastery-row" key={item.knowledge_point}>
                <div className="mastery-row-head"><strong>{item.knowledge_point}</strong><span>{percent}%</span></div>
                <div className="mastery-meter" role="progressbar" aria-label={`${item.knowledge_point}掌握度`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}><span style={{ width: `${percent}%` }} /></div>
                <div className="mastery-meta">
                  <span>已练 {item.total_count} 次</span>
                  <span>错 {item.wrong_count} 次</span>
                  <Link to={`/practice?knowledge_point=${encodeURIComponent(item.knowledge_point)}`}>去练习<ArrowRight size={14} /></Link>
                </div>
              </article>;
            })}
          </div>
        </section>
      </> : <div className="empty-state">
        <Target size={28} className="empty-inline-icon" />
        <h2>还没有学情记录</h2>
        <p>完成几道练习题后，这里会显示各知识点的掌握度和复习优先级。</p>
        <div className="empty-actions"><Link className="primary" to="/practice">去练习<ArrowRight size={17} /></Link><Link className="secondary-button" to="/chat">回到答疑</Link></div>
      </div>}
    </div>
  </section>;
}
