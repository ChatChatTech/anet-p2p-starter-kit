---
title: "P2P 02 — Sell LLM Tokens Over P2P (1 hour)"
description: "Wrap any LLM behind /v1/chat and /v1/chat/stream, charge per call, consume the SSE stream from a second peer. The smallest billed P2P service you can ship."
icon: "bolt"
---

## 1. 你将完成什么

把任意 LLM（默认 Ollama，零模型也能用 fake provider 跑通）暴露成 P2P 上的 `llm-svc` 服务，**按调用次数计费**。完成后你能解释：

- `cost_model.per_call=10` 在调用方/服务方两边账本上分别发生了什么；
- `modes=["rr","server-stream"]` 怎么让同一个服务同时支持单次请求和 token 流；
- SDK 的 `SvcClient.stream(...)` 拿到的 SSE 帧长什么样；
- 为什么 audit 表里 `cost` 列必然等于 `per_call × #calls`。

## 2. 前置条件

- 完成 `00-setup.md` + `01-first-service.md`。
- 可选：本地装了 [Ollama](https://ollama.com/)，并 `ollama pull llama3.2:1b`。**没装也可以**，把 `LLM_PROVIDER=fake` 设置一下，会用一个确定性的 5 词假回复。
- `../examples/02-llm-as-a-service/` 是参考实现。

## 3. 步骤（CLI + Python 双轨）

### 3.1 起 LLM 后端

```bash
cd ../examples/02-llm-as-a-service
export LLM_PROVIDER=fake          # 或 ollama
export LLM_PORT=7200
uvicorn llm_backend:app --host 127.0.0.1 --port $LLM_PORT --log-level warning &
sleep 1; curl -s :7200/health     # {"ok":true,"provider":"fake"}
```

### 3.2 注册（带 per_call **+ per_kb** 计费）

> ⚠️ **必读：cost_model 在不同 mode 下的语义不一样**。
>
> | 模式 | 实际计费 |
> |---|---|
> | `rr` | `per_call`（每次固定） |
> | `server-stream` / `chunked` / `bidi` | `per_kb × KB + per_minute × min`（按用量） |
>
> 如果你只设 `per_call`，stream 调用的 deposit 会在结束时**全额退还**（usage=0）→ audit 显示 cost=0。所以 streaming 服务想真的收费，必须显式给 `per_kb` 或 `per_minute`。

CLI：

```bash
export ANET_BASE_URL=http://127.0.0.1:13921
export ANET_TOKEN=$(HOME=/tmp/anet-p2p-u1 anet auth token print)

anet svc register \
  --name llm-svc \
  --endpoint http://127.0.0.1:7200 \
  --paths /v1/chat,/v1/chat/stream,/health,/meta \
  --modes rr,server-stream \
  --per-call 10 \
  --per-kb 2 \
  --tags llm,chat,streaming \
  --description "Streaming LLM proxy — 10🔐/rr + 2🔐/KB" \
  --health-check /health
```

Python 等价：

```python
from anet.svc import SvcClient
with SvcClient(base_url="http://127.0.0.1:13921") as svc:
    svc.register(
        name="llm-svc",
        endpoint="http://127.0.0.1:7200",
        paths=["/v1/chat", "/v1/chat/stream", "/health", "/meta"],
        modes=["rr", "server-stream"],
        per_call=10,
        per_kb=2,
        tags=["llm", "chat", "streaming"],
        description="Streaming LLM proxy — 10🔐/rr + 2🔐/KB",
        health_check="/health",
    )
```

注意：CLI 不能同时给 `--per-call` 和 `--free`；走 SDK 也是一样的互斥（`free=True` 会忽略所有 cost 维度）。

### 3.3 单次调用（rr 模式）

从 daemon-2 调：

```bash
export ANET_BASE_URL=http://127.0.0.1:13922
export ANET_TOKEN=$(HOME=/tmp/anet-p2p-u2 anet auth token print)
sleep 3      # ANS 收敛

PEER=$(anet svc discover --skill llm --json | python3 -c "import sys,json;print(json.load(sys.stdin)['results'][0]['peer_id'])")
anet svc call "$PEER" llm-svc /v1/chat --method POST --body '{"prompt":"why is the sky blue?"}'
```

输出：

```
HTTP 200
  completion: hi, this is a fake completion for: why is the sky blue?
  caller_did: did:key:…
```

### 3.4 流式调用（server-stream 模式）

```bash
anet svc stream "$PEER" llm-svc /v1/chat/stream \
  --method POST --mode server-stream \
  --body '{"prompt":"give me 3 ticks"}'
```

输出（SSE 实时刷新）：

```
event: status
data: 200

data: hi,
data: this
data: is
...
event: done
data: end
```

Python 等价：

```python
from anet.svc import SvcClient
with SvcClient(base_url="http://127.0.0.1:13922") as svc:
    peers = svc.discover(skill="llm")
    target = peers[0]
    for ev in svc.stream(target["peer_id"], target["services"][0]["name"],
                         "/v1/chat/stream", method="POST",
                         body={"prompt": "give me 3 ticks"},
                         mode="server-stream"):
        print(ev.event, ev.data)
        if ev.is_terminal:
            break
```

### 3.5 一键复跑

```bash
# term-1
bash run.sh provider                    # 后端 + 注册
# term-2
bash run.sh caller-both                 # rr + stream + audit dump
```

## 4. 自检命令

```bash
# A. 在 *服务端* daemon 上看 audit（audit 行写在服务方，不是调用方）
HOME=/tmp/anet-p2p-u1 anet svc audit --name llm-svc --limit 5
# 期望看到至少 2 行：
#   POST /v1/chat        mode=rr            status=200  cost=10
#   POST /v1/chat/stream mode=server-stream status=200  cost=2  ← per_kb × KB

# B. 在 *调用方* daemon 上同名 query 是空的（这是设计，不是 bug）
HOME=/tmp/anet-p2p-u2 anet svc audit --name llm-svc --limit 5
# 0 行 — 因为 daemon-2 自己没 own 这个 service

# C. 钱包对账：扣的钱进了服务方
HOME=/tmp/anet-p2p-u2 anet balance      # Δ ≈ -12（10 + 2）
HOME=/tmp/anet-p2p-u1 anet balance      # Δ ≈ +12（gossip 1-2s 收敛）

# D. 流式 vs 单次 mode 列对得上
HOME=/tmp/anet-p2p-u1 anet svc audit --name llm-svc --limit 5 \
  | awk '{print $5,$3}'
```

## 5. 故障对照表

| 现象 | 最可能原因 | 修法 |
|---|---|---|
| `register failed: cost model: must specify at least one positive dimension` | per_call=0 且没有 free=true | 改 `--per-call 10` 或 `--free` |
| `call returned status=402 error="insufficient credits"` | **典型陷阱**：本地 balance 看着是 5000，但服务方 ledger 上调用方 DID 行是 0（bootstrap grant 不 gossip） | 让两个 daemon **互相 transfer** 一笔 seed；starter 的 `scripts/two-node.sh` 已经做了，自己写 boot 时记得加 |
| stream audit 行 cost=0 | 你只设了 per_call，stream 模式按 per_kb/per_minute 计费，per_call 只是 deposit | 加 `--per-kb 2`（或 per_minute），见 §3.2 蓝色 callout |
| stream 永远只看到 `event: status` 然后 hang | backend 的 generator 没 flush 或没 yield | FastAPI 用 `StreamingResponse(gen(), media_type="text/plain")`，generator 必须 yield 字符串/字节，不能返回完整字符串 |
| stream 直接降级成 JSON envelope | 你的 anet daemon 是 1.1.10 之前的，statusWriter 不支持 Flusher | 升级 |
| Ollama 报 `connection refused` | ollama 没起 / 没 pull 模型 | `ollama serve` + `ollama pull llama3.2:1b`，或 `LLM_PROVIDER=fake` |
| audit 里 cost=0 但 per_call=10 | 你 register 时 free 也设了 / cost_model 字段名拼错 | `anet svc show llm-svc --json` 检查实际写进去的 cost_model |

完成 → 进入 `03-multi-agent.md`。
