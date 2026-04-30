---
title: "P2P 03 — Three Agents Talk to Each Other (2 hours)"
description: "Build a translate → summarise → sentiment pipeline running on three daemons, with each hop billed and audited. The smallest demo that exercises real service composition."
icon: "diagram-project"
---

## 1. 你将完成什么

让 4 个本地 daemon 上的 4 个进程演一出戏：

```
D 客户端  ───▶  C 情感分类  ───▶  B 摘要  ───▶  A 翻译
                                       (内部按需调 A)        (zh→en 时调用)
```

完成后你能解释：

- 一个 P2P 服务**内部**怎么变成另一个服务的客户端（service-of-services）；
- 三跳调用链上每个 daemon 各自的 `svc_call_log` 长什么样；
- per_call 计费如何在 4 个钱包之间结算（D → C → B → A，跳一次扣一次）；
- ANS skill 发现为什么让你不必关心对方的 peer_id。

## 2. 前置条件

- 完成 `00-setup.md` + `02-llm-service.md`。
- 至少 4 GB 内存、能同时跑 4 个 anet daemon（每个约 80-150 MB）。
- `../examples/03-multi-agent-pipeline/` 是参考实现。

## 3. 步骤

### 3.1 起 4 个 daemon

```bash
cd ../examples/03-multi-agent-pipeline
bash scripts/four-node.sh start
# ✓ u1 alive  PEER=12D3KooW…
# ✓ u2 alive on :13922
# ✓ u3 alive on :13923
# ✓ u4 alive on :13924
```

### 3.2 在 4 个终端里依次起 3 个 agent

```bash
# term-2  (daemon-1)
bash run.sh agent-a
# [A] ✓ registered (per_call=5, ans.published=True)

# term-3  (daemon-2)
bash run.sh agent-b
# [B] ✓ registered (per_call=10, ans.published=True)

# term-4  (daemon-3)
bash run.sh agent-c
# [C] ✓ registered (per_call=10, ans.published=True)
```

每一个 agent 进程都做了三件事：起 FastAPI backend、register 自己、然后阻塞跑下去。

### 3.3 客户端发起一次调用

```bash
# term-5
bash run.sh client "上海明天天气怎么样？给我用一句话总结。"
```

控制台依序打印：
1. discover sentiment（在 daemon-3 上找到 C）
2. 一次 call → C 内部 discover summarise（找到 B）→ call B → B 内部 discover translate（找到 A）→ call A → 链路返程
3. **每个 daemon 上的 svc_call_log 各打印 1-2 条**

最后输出：

```
[client] result:
  text:        '上海明天天气怎么样？给我用一句话总结。'
  source_lang: zh
  summary:     'shanghai tomorrow weather how is'
  label:       neutral
  score:       0.5

[client] svc_call_log per node:
  u1 (A): 1 row(s) recent
    translate-a   POST  /v1/translate    status=200  cost=  5
  u2 (B): 1 row(s) recent
    summarise-b   POST  /v1/summarise    status=200  cost= 10
  u3 (C): 1 row(s) recent
    sentiment-c   POST  /v1/sentiment    status=200  cost= 10
  u4 (D): 0 row(s)        # client 是发起方，audit 在 D 上记录的是它对外发起的调用（C 服务）
```

### 3.4 把链路收尾用到的对账验一遍

```bash
HOME=/tmp/anet-p2p-u4 anet balance      # D 应该 -10（付给 C）
HOME=/tmp/anet-p2p-u3 anet balance      # C 应该  0  （收 +10、付出 -10 给 B）
HOME=/tmp/anet-p2p-u2 anet balance      # B 应该  +5 （收 +10、付出 -5 给 A）
HOME=/tmp/anet-p2p-u1 anet balance      # A 应该  +5
```

总和 = 0（守恒），对的上。

## 4. 自检命令

```bash
# A. 4 个 daemon 全 alive
bash scripts/four-node.sh status

# B. 4 个服务全 ans.published=True
for h in /tmp/anet-p2p-u{1,2,3}; do
  HOME=$h anet svc list | head -2
done

# C. 三个 agent 进程都注册了
anet svc discover --skill translate
anet svc discover --skill summarise
anet svc discover --skill sentiment
# 每个都至少 1 个 peer

# D. 计费守恒
python3 - <<'PY'
import subprocess, re, os
total = 0
for h in ["/tmp/anet-p2p-u1","/tmp/anet-p2p-u2","/tmp/anet-p2p-u3","/tmp/anet-p2p-u4"]:
    out = subprocess.check_output(["anet","balance"], env={**os.environ,"HOME":h}).decode()
    bal = int(re.search(r"(-?\d+)", out).group(1))
    print(h, bal)
    total += bal
print("Σ =", total, "(应为 0 ± initial seed)")
PY
```

## 5. 故障对照表

| 现象 | 最可能原因 | 修法 |
|---|---|---|
| `agent-b` 启动后立刻 `register failed: insufficient credits` | B 还没收到任何调用，但 register 不要钱；多半是你 ssh 进了别人的环境 | 检查你跑的 `ANET_BASE_URL` 是不是对的 daemon |
| client 打印 `no sentiment peers` | C agent 还没 register / ANS gossip 还没收敛 | 等 5s；或 `anet svc list` 在 daemon-3 上确认 C 已经在 |
| 整条链路返回 `body.summary` 是中文原文 | A 没找到（调用 B 时 B fallback 了不翻译） | 在 B 那个 terminal 看 `[B] ↳ translated to en: …` 这行有没有；没有说明 B→A discover 失败 |
| 链路总耗时 > 2s | 三跳 + ANS lookup，正常上限 1-2s；超过就是 backend 阻塞 | 各 agent 的 print 行有时间戳，看哪一跳慢 |
| 4 个 daemon 中某个 cpu 100% | libp2p 跟自己疯狂重连 — 通常因为 bootstrap_peers 写错 | `bash scripts/four-node.sh stop && start` 重置 |
| `anet balance` 全部对不上 | service_charge / service_refund gossip 还没收敛（最多 1-2s） | 等几秒重查；如果持续不收敛，看 `daemon.log` 里 `[credits]` 行有没有 reject |

完成 → 进入 `99-troubleshooting.md` 学进阶诊断。
