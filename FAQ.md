# FAQ — 15 个最常被问的问题

按出现频率排序。Ctrl-F 直接搜你看到的关键字。

---

## Q1. 为什么我的 daemon 总是 `peers=0`，看不到队友？

最常见 3 个原因：

1. **mDNS 被网络挡了**（学校 wifi、办公室 NAT 经常这样）。修法：用 starter-template 的 `scripts/two-node.sh`，它已经写了显式 `bootstrap_peers`。如果是跨机器，让两边都 `bootstrap_peers` 写对方的 `/ip4/<ip>/tcp/<p2p-port>/p2p/<peer-id>`。
2. **端口冲突**：你之前的 daemon 没杀干净。`lsof -i :14021`，看到的话 kill 掉。
3. **防火墙**：Mac 的 PF / Linux 的 ufw 把 P2P 端口挡了。临时关一下试试。

详细诊断走 [tutorials/99-troubleshooting.md](../tutorials/99-troubleshooting.md) §3.3。

---

## Q2. `anet svc register` 报 `endpoint host must be localhost`，但我就是要用远端 backend

预期行为，叫做 **SSRF guard（CP3）**。打开「双重 opt-in」就行：

```bash
# 1. 编辑 daemon 配置
$EDITOR ~/.anet/config.json
# 加一行： "svc_remote_allowlist": ["my-server.lab.example.com"]
# 然后重启 daemon

# 2. register 时显式列出 remote_hosts
anet svc register --name x --endpoint http://my-server.lab.example.com:8080 \
  --paths /api --modes rr --free \
  --remote-host my-server.lab.example.com
```

少哪一步都会被拒。SDK 写法：`svc.register(..., remote_hosts=["my-server.lab.example.com"])`。

---

## Q3. 我注册成功了，但队友 `discover --skill` 看不到我

先排除：
- 队友的 daemon 跟你**同一个 mesh**？（`anet peers` 互相能看到）
- 你 register 时**真的填了 tags**？`anet svc list` 看 TAGS 列。
- skill 名字精确匹配吗？`echo` 和 `Echo` 是两回事，`zh-en` 和 `zh_en` 也是。

如果都对，等 5-10 秒（ANS gossip 收敛），然后让队友重新 discover。

---

## Q4. SDK 报 `AuthMissingError: no API token`

按优先级解析：
1. 调用时显式传 `SvcClient(token="...")`；
2. 环境变量 `$ANET_TOKEN`；
3. 文件 `$HOME/.anet/api_token`。

最常见情况：你跑了多个 daemon，每个有自己的 `$HOME`，但 SDK 进程的 `$HOME` 指向另一个。修法：

```bash
export ANET_TOKEN=$(HOME=/tmp/anet-p2p-u1 anet auth token print)
python -m my_agent.client
```

---

## Q5. 调用方钱包不够余额怎么办？

> **重要细节**：每个 daemon 启动时给**自己的本地 DID** 5000 shells 的 bootstrap grant。这笔 grant **不会通过 gossip 传给别人**——所以 daemon-1 的 ledger 里 daemon-2 的 DID 余额是 0，反之亦然。结果：跨节点的付费调用第一次会直接 402 insufficient credits，**即使两边各自看 `anet balance` 都是 5000**。

**修法（已经做进 starter-template 了）**：在两个 daemon 都起来之后，做一笔 **mutual transfer** 把对方的 DID 行 ensure-peer 到自己 ledger 里：

```bash
# daemon-1 给 daemon-2 转 1000（这一步会把 u2 的 DID 行写进 u1 的 ledger）
curl -X POST http://127.0.0.1:13921/api/credits/transfer \
  -H "Authorization: Bearer $TOK1" -H "Content-Type: application/json" \
  -d '{"from":"'$DID1'","to":"'$DID2'","amount":1000,"reason":"seed"}'
# 反过来再转一笔
curl -X POST http://127.0.0.1:13922/api/credits/transfer \
  -H "Authorization: Bearer $TOK2" -H "Content-Type: application/json" \
  -d '{"from":"'$DID2'","to":"'$DID1'","amount":1000,"reason":"seed"}'
```

starter 的 `scripts/two-node.sh` 已经在 boot 完成后自动做这件事。L3 的 `scripts/four-node.sh` 也对所有 12 对组合做了 seed。如果你**自己写 boot 脚本**，记得也要做一次。

**不要**在 demo 里设 `per_call=1000`，那评委一次都调不起。

如果真的钱包没钱了：

```bash
# 看你自己 balance
anet balance

# 比赛会发 founder code 给每队领额外余额（看赛事公告）
anet founder claim <your-code>
```

---

## Q5b. 我设了 `per_call=10`，rr 调用 audit 显示 cost=10，**stream 调用 audit 显示 cost=0**？

不是 bug，是 cost_model 的语义被误解了：

| 模式 | 实际计费公式 |
|---|---|
| `rr` | `per_call`（每次调用固定） |
| `server-stream` / `chunked` / `bidi` | `per_kb × KB + per_minute × minutes`（按用量） |

`per_call` 在 stream 模式里**只用作初始 deposit**，结束时按实际 usage 找零（`settlePostCall` 会 refund 多余部分）。所以如果你只设 `per_call`，stream 调用的 deposit 全额退还，audit cost = 0。

**修法**：streaming 服务想真的收费，必须显式给 `per_kb` 或 `per_minute`：

```python
svc.register(
    name="llm-svc",
    ...,
    per_call=10,    # rr 调用每次 10
    per_kb=2,       # stream 调用按 KB 计 2/KB
    per_minute=5,   # 或长连接按分钟 5/min
)
```

`examples/02-llm-as-a-service/register.py` 现在用 `per_call=10 + per_kb=2`，audit 行就会显示 stream 真的扣到钱。

---

## Q5c. 在调用方 daemon 上 `anet svc audit --name=llm-svc` 永远是空的？

audit 表是**写在服务端 daemon**（who owns the service）的，因为是它真的代理了请求 + 写了 `svc_call_log`。调用方 daemon 自己没注册过这个服务，所以 `--name=llm-svc` filter 出来 0 行。

**修法**：去服务端 daemon 上查 audit：

```bash
HOME=/tmp/anet-p2p-u1 anet svc audit --name=llm-svc --limit 5
```

或在你 SDK 里同时持两边 token：

```python
caller_svc = SvcClient(base_url="http://127.0.0.1:13922", token=caller_tok)
provider_svc = SvcClient(base_url="http://127.0.0.1:13921", token=provider_tok)
caller_svc.call(...)              # 实际调用走这个
rows = provider_svc.audit(name="llm-svc", limit=5)   # audit 在那一边
```

---

## Q6. stream 调用看不到任何 event 就 hang 住了

99% 是 backend 的 generator 实现有问题。FastAPI 必须：

```python
def gen():
    for tok in tokens:
        yield tok          # 每个 yield 必须是 str / bytes，不能是 None / dict
    yield ""               # optional sentinel — 帮助 client 知道结束

return StreamingResponse(gen(), media_type="text/plain")
```

如果你 `return JSONResponse(...)`，那只会发一次然后断 — 自然只看到一帧。

---

## Q7. `anet svc audit` 里 `cost` 是 0，但我设了 `per_call=10`

可能性：
1. 你 register 时**同时**传了 `free=true`（`free` 优先级最高），用 `anet svc show <name> --json` 看实际 cost_model 是不是 `{"free":true}`；
2. 路径有 per-path cost override，比如 `paths=[{"prefix":"/free", "cost":0}]`；
3. 你看的是**调用方**的 audit，调用方那一行 cost 是它**付出去**的金额（仍是 10），看的是负值还是绝对值要确认列含义。

---

## Q8. cost_model 不止一种，到底怎么选？

| 场景 | 选项 |
|---|---|
| Demo / 公益服务 | `free=true` |
| 简单 LLM API | `per_call=N` |
| 流量大的下载 / 上传服务 | `per_kb=N` |
| 长连接（chat / push） | `per_minute=N` |
| 大文件传输，先冻结额度 | `deposit=N` + `per_kb=M` |
| 部分路径免费、部分收费 | `paths=[{"prefix":"/free","cost":0},{"prefix":"/paid","cost":10}]` |

可以组合，比如同时 `per_call=2 + per_kb=1`。

---

## Q9. 我能在一个 daemon 里注册多个服务吗？

可以，没数量限制。`name` 唯一就行。两个服务名字相同会冲突 → 老的会被覆盖。

---

## Q10. WebSocket 模式（bidi-ws）SDK 怎么用？

SDK 的 `SvcClient.ws_url(name)` 返回 `ws://...`，你拿任何 WebSocket 库连上去：

```python
import asyncio, websockets, json
from anet.svc import SvcClient

svc = SvcClient()
url = svc.ws_url("chat-svc")   # ws://127.0.0.1:3998/api/svc/ws/chat-svc

async def main():
    async with websockets.connect(url, additional_headers={"Authorization": f"Bearer {svc.token}"}) as ws:
        await ws.send(json.dumps({"hello":"world"}))
        msg = await ws.recv()
        print(msg)

asyncio.run(main())
```

注意 `bidi-ws` 是**桥接到本地 WS backend**，不是 P2P 直接 WS。流量路径仍是：你的 client ↔ daemon ↔ libp2p ↔ 对面 daemon ↔ 对面本地 WS backend。

---

## Q11. 我的服务能调用别的服务吗？（service-of-services）

可以。在你的 backend handler 里直接 `from anet.svc import SvcClient` 然后 discover/call。看 `examples/03-multi-agent-pipeline/agent_b_summarise.py` 的写法。

注意：嵌套调用每一跳都会被各自 daemon 计费 + 写 audit，所以一次外部调用可能产生多条 audit 行（这是 feature，不是 bug）。

---

## Q12. 有 JS / TS SDK 吗？

`sdk/js/` 是已有的 anet 通用 SDK，但**还没封装 svc 模块**。短期内只能直接用 `fetch` 打 `/api/svc/*`：

```js
const r = await fetch(`${ANET_BASE}/api/svc/discover?skill=echo`, {
  headers: { "Authorization": `Bearer ${TOKEN}` }
});
const peers = (await r.json()).results;
```

REST 接口的形状跟 Python SDK 完全一样（去 `sdk/python/anet/svc.py` 看 endpoint / payload 形状直接抄）。

---

## Q13. 怎么模拟「我离线了」？

最简单：直接 kill 你那个 daemon 的进程。其他 peer 会发现你掉线，等重连。

```bash
kill $(lsof -ti tcp:13921)        # daemon-1 模拟离线
# … 这时 daemon-2 上 discover 几秒后就看不到你了
```

也可以更细粒度地 unregister 单个服务：

```bash
anet svc unregister llm-svc
```

---

## Q14. 我能不能改 daemon 配置 / 加 endpoint？

赛事期间**不要改** anet 二进制；它已经稳定。可改的是：
- `~/.anet/config.json`（端口、bootstrap_peers、svc_remote_allowlist 等）；
- 你自己 backend 的实现；
- starter-template 的 my_agent 代码。

如果你真的需要 daemon 加新 endpoint，说明你在做奇怪的事，找工作人员聊一下。

---

## Q15. 评委怎么知道我的服务存在？

约定：所有提交的服务都**必须**带一个赛事 tag（开赛时主办方公布，比如 `p2p-2026`）。评委统一这样找：

```bash
anet svc discover --skill p2p-2026 --json | python3 -m json.tool | less
```

所以 register 的时候一定要：

```python
svc.register(..., tags=["p2p-2026", "your-product-tag", "其他可选 skill 标签"])
```

少了赛事 tag = 评委找不到你 = 完成度 0 分。
