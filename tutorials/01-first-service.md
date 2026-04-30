---
title: "P2P 01 — Your First P2P Service in 30 Minutes"
description: "From a 30-line stdlib HTTP server to a service that another peer can discover and call across the libp2p mesh."
icon: "play"
---

## 1. 你将完成什么

把一个 30 行的 Python HTTP 服务，挂到 P2P 网络上变成 `echo` 服务，让**第二个 daemon**通过技能标签发现它并发起调用。完成后你能解释：

- 一条 `ServiceEntry` 长什么样（`name / endpoint / paths / modes / cost_model / tags`）；
- `anet svc discover --skill=…` 是如何穿越 ANS 找到对方的；
- 为什么调用会出现在 `anet svc audit` 里、且 `status` 是 200（CP6）。

## 2. 前置条件

- 已完成 `00-setup.md`，两个 daemon alive、SDK 装好。
- `../examples/01-echo-svc/` 目录可访问（这是参考实现）。

## 3. 步骤（CLI + Python 双轨）

### 3.1 起最小 echo 后端

```bash
cd ../examples/01-echo-svc
python3 echo_backend.py &      # 监听 127.0.0.1:7100
sleep 1; curl -s -X POST :7100/echo -d '{"hi":1}'
# {"echo": {"hi": 1}, "caller_did": "<missing>"}
```

`<missing>` 是因为我们直接 curl，没有 daemon 注入 X-Agent-DID。下面让 daemon 接管。

### 3.2 注册（CLI 一行）

```bash
export ANET_BASE_URL=http://127.0.0.1:13921
export ANET_TOKEN=$(HOME=/tmp/anet-p2p-u1 anet auth token print)

anet svc register \
  --name echo-l1 \
  --endpoint http://127.0.0.1:7100 \
  --paths /echo,/health,/meta \
  --modes rr \
  --free \
  --tags echo,demo \
  --description "L1 p2p echo" \
  --health-check /health
```

输出最后一行：

```
✓ service "echo-l1" registered
  ans:  published=true uri=agent://svc/echo-l1-…
```

### 3.2'（等价的 Python 写法）

```python
from anet.svc import SvcClient

with SvcClient(base_url="http://127.0.0.1:13921") as svc:
    svc.register(
        name="echo-l1",
        endpoint="http://127.0.0.1:7100",
        paths=["/echo", "/health", "/meta"],
        modes=["rr"],
        free=True,
        tags=["echo", "demo"],
        description="L1 p2p echo",
        health_check="/health",
        meta_path="/meta",
    )
```

### 3.3 从另一个 daemon 发现 + 调用

```bash
export ANET_BASE_URL=http://127.0.0.1:13922
export ANET_TOKEN=$(HOME=/tmp/anet-p2p-u2 anet auth token print)

# 等 ANS gossip 收敛 1~3s
sleep 3
anet svc discover --skill echo
```

输出：

```
✓ skill="echo" found 1 peer(s)

  peer:  12D3KooW…
  owner: did:key:z6Mk…
  ans:   agent://svc/echo-l1-…
    - echo-l1            [http/rr] L1 p2p echo
```

调用：

```bash
PEER=$(anet svc discover --skill echo --json | python3 -c "import sys,json;print(json.load(sys.stdin)['results'][0]['peer_id'])")
anet svc call "$PEER" echo-l1 /echo --method POST --body '{"msg":"hi"}'
# HTTP 200
#   echo: {"msg":"hi"}
#   caller_did: did:key:...
```

Python 写法见 `../examples/01-echo-svc/caller.py`，逻辑一致。

### 3.4 一键复跑

```bash
cd ../examples/01-echo-svc
bash run.sh
# 最后一行：✓ L1 demo PASSED
```

## 4. 自检命令

```bash
# A. /api/svc 列表里有 echo-l1
anet svc list
# NAME    TRANSPORT  MODES  ENDPOINT                  COST  TAGS         META
# echo-l1 http       rr     http://127.0.0.1:7100     free  echo,demo    /meta

# B. /api/svc/health 报告 healthy
anet svc health
# NAME      STATUS    CODE  LATENCY
# echo-l1   healthy   200   3ms

# C. 真实 status 写进 audit 表
anet svc audit --name echo-l1 --limit 1
# WHEN              CALLER  SERVICE  MODE METHOD PATH STATUS COST DUR
# 04-30 12:34:56    did:…   echo-l1  rr   POST /echo  200    0    8ms

# D. backend log 看到了 X-Agent-DID
# (看 echo_backend.py 的 stderr，应该写了 did=did:key:…)
```

## 5. 故障对照表

| 现象 | 最可能原因 | 修法 |
|---|---|---|
| `register failed: name is required\n  - endpoint is required` | CP2 同时报错 — 你漏了字段 | 按 errors 数组里逐项补 |
| `register failed: endpoint host must be localhost ...` | endpoint 写了非 127.0.0.1 但没 SSRF 白名单 | 改 endpoint，或编辑 daemon `~/.anet/config.json` 加 `svc_remote_allowlist` 然后 register 时带 `remote_hosts=[…]` |
| `discover --skill=echo` 返回 0 个 | ANS gossip 还没收敛 / topic 没订阅 / mesh 没成 | `sleep 5` 再试；查 daemon-1 log 里 `[ans] published svc:echo` 有没有出现 |
| `call` 报 `peer not found in routing table` | 拿到的 peer_id 是另一个 daemon 的，你打错节点 | 重新从同一个 discover 输出里取 peer_id |
| `audit` 表 `status` 始终是 0 | 你跑的是 v1.1.10 之前的版本 | 升级 anet 到 v1.1.10+ |
| `meta` 返回 404 | 你 register 时没填 `meta_path`，且 backend 也没 /meta | 加 `--meta-path /meta` 重 register，或在 backend 实现 GET /meta |

完成 → 进入 `02-llm-service.md`。
