---
title: "P2P — Troubleshooting Cookbook"
description: "Diagnostic recipes for the dozen most-likely failure modes during a event weekend. Read this when something is mysteriously not working."
icon: "stethoscope"
---

## 1. 你将完成什么

学会一套**有顺序的**诊断动作，遇到「调用没回来 / 钱没扣 / 发现不到」时不再瞎试。本篇分两部分：
- §3 是按现象切入的处方；
- §4 是日常常用的「单步检查」工具箱（每条都拷贝即用）。

## 2. 前置条件

只要你已经能 `anet svc list` 不报错，本篇就用得上。

## 3. 现象 → 处方

### 3.1 「register 报 errors.Join 一堆」

```
register failed:
  - name is required
  - endpoint is required
  - modes is required
```

**含义**：daemon 用 `errors.Join` 把全部缺失字段一次性甩回来（CP2），不再一条一条让你试。

**处方**：照着 list 把每条补齐；最少需要 `name + endpoint + paths + modes + (cost_model 至少 1 维 或 free=true)`。

### 3.2 「register 报 endpoint must be localhost」

**含义**：daemon 默认只允许 `127.0.0.1 / localhost / ::1` 作为 endpoint，防止有人在你机器上代理到外网做 SSRF。

**处方**：

1. 编辑 daemon 的 `~/.anet/config.json`：
   ```json
   { "svc_remote_allowlist": ["my-private.gpu.lan"] }
   ```
2. 重启 daemon。
3. register 时同时传 `remote_hosts=["my-private.gpu.lan"]`（CLI: `--remote-host`）。

两层 opt-in，少一层都不行（CP3）。

### 3.3 「discover --skill=… 永远返回 0 个」

**最常见 4 种**：

| 子症状 | 检查 | 修法 |
|---|---|---|
| 自己的 daemon 上 `anet svc list` 空 | register 没成功（看 stderr） | 见 3.1 |
| 自己的 daemon 上 list 有，对方 daemon 上 discover 空 | ANS gossip 还没穿过去 | 等 5s；查 `~/.anet/daemon.log` 里 `[ans] published`、`[ans] received` 行 |
| `peers=0` 说明根本没成 mesh | mDNS 被网络挡 / 没写 bootstrap_peers | starter 已写显式 bootstrap_peers，重启即可 |
| skill 名字不一样 | tag 是 `[python,coding]` 但你 discover 的是 `python_coding` | tag 必须**完整等于**才匹配；用 `anet svc list` 看实际 tags |

### 3.4 「call 报 peer not found」

**含义**：拿到的 peer_id 串字面没问题，但 libp2p 路由表里找不到那个 peer。

**处方**：
1. 你拿 peer_id 的 daemon 和你打 call 的 daemon 是不是同一个？必须同一个，否则它对那个 peer 没 routing 信息。
2. 重新走一次 discover 拿最新 peer_id（peer_id 偶尔会因为 daemon 重启而变）。

### 3.5 「call 200 成功了，但 body 是字符串而不是 dict」

**含义**：upstream backend 没返回合法 JSON，daemon 帮你把原始 bytes 当字符串塞进 `body` 字段了。

**处方**：在你的 backend 里**永远返回 JSON**：FastAPI 用 `JSONResponse(...)`、Flask 用 `jsonify(...)`、stdlib 用 `Content-Type: application/json` + `json.dumps(...)`。

### 3.6 「stream 只看到一帧 JSON envelope，没看到 SSE」

**含义**：你跑的 anet daemon 是 v1.1.10 之前的版本，`statusWriter` middleware 把 `http.Flusher` 接口吞了，stream 退化成 rr。

**处方**：升级 anet。验证：

```bash
anet --version    # 必须 ≥ 1.1.10
```

### 3.7 「audit 表里 status 永远是 0」

**含义**：同上，旧版 daemon 没把 upstream HTTP 状态写进 `svc_call_log.status`（CP6）。

**处方**：升级 anet。

### 3.8 「balance 对不上」

**含义**：`service_charge` 或 `service_refund` gossip 没收敛。两边 daemon 必须订阅同一个 `/anet/credits` topic。

**处方**：

```bash
# 两边 daemon 都要看到这个 topic
HOME=/tmp/anet-p2p-u1 anet topic list | grep credits
HOME=/tmp/anet-p2p-u2 anet topic list | grep credits

# 等 2-3s 再查 balance
```

如果 1 分钟后仍不收敛，查 `daemon.log` 里 `[credits]` 开头的行——通常是签名校验失败（DID 解析不出 publickey）。

### 3.9 「passthrough_status 不生效」

```bash
curl -i ... /api/svc/call?passthrough_status=1
# HTTP/1.1 200 OK         ← 想看到 4xx，结果还是 200
```

**最可能原因**：你访问的 daemon 没拿到 query string，比如你前面挂了反代把 query 吃掉了。

**处方**：直接打 daemon 的 `127.0.0.1:13921`，绕开任何代理。SDK 写法：`svc.call(..., passthrough_status=True)`。

### 3.10 「meta 返回 404」

**含义**：daemon 找不到 meta 路径。

**处方**：register 时传 `meta_path=/meta`（CP7 优先用注册时探测到的路径）；同时确认 backend 真的实现了 GET /meta。

## 4. 单步检查工具箱

### 4.1 daemon 自检

```bash
# 是否 alive + 看到几个 peer
curl -s --noproxy '*' :13921/api/status | python3 -m json.tool

# 自己 owns 哪些服务
anet svc list

# 哪些服务的 health check 不通
anet svc health

# 最近 20 条 service-call 审计行
anet svc audit --limit 20
```

### 4.2 ANS / 发现自检

```bash
# 我自己宣传了哪些 ANS record
curl -s --noproxy '*' -H "Authorization: Bearer $ANET_TOKEN" \
  :13921/api/ans/records | python3 -m json.tool | head -30

# 全网能搜到 skill=foo 的有谁
anet svc discover --skill foo --json | python3 -m json.tool
```

### 4.3 P2P mesh 自检

```bash
anet peers          # 当前连接的 peer 列表
anet ping <peer-id> # 最少 1 个能 ping 通
```

### 4.4 钱包对账

```bash
anet balance
anet credits events --limit 10
```

### 4.5 SDK 自检（一行 smoke test）

```bash
python3 -c "from anet.svc import SvcClient; c=SvcClient(); print('list:', len(c.list()), 'audit:', len(c.audit(limit=1)))"
# list: 0 audit: 0
```

### 4.6 看 daemon 日志（最高频救命动作）

```bash
tail -n 100 -f /tmp/anet-p2p-u1/daemon.log

# 关键关键字：
#   [svc]       服务网关相关
#   [ans]       发现 / 公告
#   [credits]   钱包 / 对账
#   [p2p]       libp2p / mesh
#   [mdns]      局域网发现
```

## 5. 故障对照表（meta-table）

把 §3 的所有处方汇成一张：

| 关键词出现在哪 | 去看 |
|---|---|
| `errors.Join` 报错 | §3.1 |
| `must be localhost` | §3.2 |
| `discover` 返回 0 | §3.3 |
| `peer not found` | §3.4 |
| body 是字符串不是 dict | §3.5 |
| stream 只一帧 | §3.6 |
| `audit.status = 0` | §3.7 |
| `balance` 对不上 | §3.8 |
| `passthrough_status` 不生效 | §3.9 |
| `meta` 404 | §3.10 |
| 上面都不是 | 看 §4 工具箱按顺序排查 |

仍然搞不定 → 在比赛 Slack/微信群里贴：
1. `anet --version`；
2. `anet status` 完整输出；
3. `anet svc list / discover / audit` 的相关输出；
4. `daemon.log` 最近 50 行；
5. 你期待发生什么 vs 实际发生了什么。

这五样齐了，热心选手 / 工作人员 90% 能 5 分钟帮你定位。
