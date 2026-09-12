"""研岸 D11：缓存巡检 —— 看当前后端、命中率、键分布和多轮会话记忆。

用法:
    python -m app.inspect_cache                 # 概况（后端 / 版本号 / 键数量 / 命中率）
    python -m app.inspect_cache demo            # 冷热检索对比，直观看到缓存效果
    python -m app.inspect_cache sess default    # 看某个用户的多轮记忆
    python -m app.inspect_cache keys            # 列出 ashore: 前缀下的键
    python -m app.inspect_cache bump            # 手动 +1 知识库版本（模拟重新入库）
    python -m app.inspect_cache flush           # 按前缀清理缓存
"""
import sys
import time

from app import cache


def show_overview():
    info = cache.stats()
    print("===== 缓存概况 =====")
    print(f"后端        : {info['backend']}"
          + ("   ← Redis 没连上，已自动降级为进程内" if info["backend"] == "memory" else ""))
    print(f"知识库版本  : {info['kb_version']}")
    print(f"键总数      : {info['keys']}（ashore: 前缀）")
    print(f"会话用户数  : {info['sessions']}")
    print(f"命中 / 未命中: {info['hit']} / {info['miss']}  命中率 {info['hit_rate']:.1%}")


def show_keys():
    keys = sorted(cache.backend().scan_iter(match="ashore:*"))
    print(f"===== ashore:* 共 {len(keys)} 个键 =====")
    for key in keys[:50]:
        print(f"  {key}   ttl={cache.backend().ttl(key)}s")
    if len(keys) > 50:
        print(f"  …（其余 {len(keys) - 50} 个省略）")


def show_session(user_id):
    key = cache.session_key(user_id)
    messages = cache.session_load(user_id)
    ttl = cache.backend().ttl(key)
    print(f"===== {user_id} 的会话记忆：{len(messages)} 条（键 {key}，TTL {ttl}s）=====")
    if not messages:
        print("  （空；跑一轮 python -m app.router_agent 或调 POST /chat 后再看）")
    for i, m in enumerate(messages, 1):
        role = m.get("role", "?") if isinstance(m, dict) else "?"
        content = m.get("content", "") if isinstance(m, dict) else str(m)
        print(f"  [{i}] {role:5} | {content[:70]}")


def demo(query="定积分有哪些计算方法", top_k=4):
    """冷启动 vs 命中缓存：对比耗时，并演示「重新入库后缓存自动失效」。"""
    from app.retriever import cached_hybrid_search

    top_k = int(top_k)          # 命令行传进来是字符串

    cache.reset_stats()
    t0 = time.perf_counter()
    cold = cached_hybrid_search(query, top_k=top_k)
    cold_cost = time.perf_counter() - t0

    # 命中路径快到会落到计时器精度下限，所以取若干次的平均，避免出现几十万倍的假数字
    rounds = 200
    t0 = time.perf_counter()
    for _ in range(rounds):
        warm = cached_hybrid_search(query, top_k=top_k)
    warm_cost = (time.perf_counter() - t0) / rounds

    print("===== 检索缓存冷热对比 =====")
    print(f"查询: {query}  (top_k={top_k})")
    print(f"  第 1 次（未命中，真检索）: {cold_cost * 1000:8.1f} ms   返回 {len(cold)} 条")
    print(f"  命中缓存（{rounds} 次平均）  : {warm_cost * 1000:8.3f} ms   返回 {len(warm)} 条")
    if warm_cost > 0:
        print(f"  提速                     : {cold_cost / warm_cost:.0f}x")
    print(f"  两次结果一致             : {cold == warm}")
    print(f"  后端 / 版本号            : {cache.backend_name()} / {cache.kb_version()}")
    print(f"  缓存键                   : {cache.retrieval_key(query, top_k)}")
    info = cache.stats()
    print(f"  本轮到目前               : 命中 {info['hit']} / 未命中 {info['miss']} / 命中率 {info['hit_rate']:.0%}")

    print("\n===== 模拟重新入库：版本号 +1，旧缓存立即失效 =====")
    old_key = cache.retrieval_key(query, top_k)
    version = cache.bump_kb_version()
    new_key = cache.retrieval_key(query, top_k)
    print(f"  新版本号  : {version}")
    print(f"  旧缓存键  : {old_key}")
    print(f"  新缓存键  : {new_key}")
    print("  两个键不同 -> 旧缓存再也命中不到，剩下的交给 TTL 回收（不用 KEYS 扫删）")


def main():
    args = sys.argv[1:]
    action = args[0] if args else "overview"
    if action == "overview":
        show_overview()
    elif action == "keys":
        show_keys()
    elif action == "sess":
        show_session(args[1] if len(args) > 1 else "default")
    elif action == "demo":
        demo(*args[1:])
    elif action == "bump":
        print(f"知识库版本号 -> {cache.bump_kb_version()}")
    elif action == "flush":
        print(f"已清理 {cache.flush()} 个键（ashore: 前缀）")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
