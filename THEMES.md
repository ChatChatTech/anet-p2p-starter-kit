# 赛题方向 — 6 条灵感线

不限定题目，但如果你卡题，下面 6 个方向都已被验证「在 anet svc gateway 上可行、容易出 demo 效果、有判分维度」。

每条标注：
- **核心 anet 能力**：你必然要用到的子系统；
- **最小可行版**：1 天能跑出的 demo；
- **加分项**：拿出来评委会"哇"的细节。

---

## A. P2P LLM 推理市场

> 一台机器有 GPU，全网都能租；按 token / 按调用付费。

- **核心**：`cost_model.per_call` 或 `per_kb`、`server-stream` 模式、按 DID 限流。
- **MVP**：把本地 Ollama 包成 `llm-svc`，per_call=10，调用方流式看到 token；做一个简陋 web UI 让用户输入 prompt，后端从全网 discover 一个 llm-svc。
- **加分**：
  - 服务方 backend 在 `X-Agent-DID` 上做配额（同一 DID 每分钟最多 N 次）；
  - 调用方 SDK 自动重试 + 选 reputation 最高的 peer；
  - 模型卡片 `/meta` 暴露 model_name / context_window / TPS。

参考起点：`examples/02-llm-as-a-service/`。

---

## B. 协作式数据标注 / RAG knowledge swap

> 多人共同标注一份数据集；标注变成 P2P knowledge，可以被检索 / 引用 / 反向悬赏。

- **核心**：`anet knowledge` + `anet svc`（注册一个标注分发服务）+ `anet topic`（实时同步标注事件）。
- **MVP**：A 起标注任务（图片 URL + 候选标签），B/C 通过 `anet svc call` 提交标注，A 的 backend 把每条标注落 `anet knowledge publish`，最后用 `anet knowledge search` 检索。
- **加分**：
  - 双盲：标注者互相不知道对方标了什么，结算时高一致性给奖励；
  - 用 PoI 验证标注质量；
  - 用 `anet topic post` 实时推标注 leaderboard。

---

## C. 跨设备文件 / 计算资源调度

> 你的笔记本算力 / 闲置 SSD 空间挂出来，被全网租走。

- **核心**：`chunked` 传输模式（大 body 分片）、`per_kb` 计费。
- **MVP**：注册一个 `disk-svc`，路径 `/put`、`/get`、`/list`；客户端通过 `anet svc call --body-stdin < file.bin` 上传文件，服务方按 KB 收费。
- **加分**：
  - 自动副本（同时存到 N 个 peer，`/get` 时随机挑一个）；
  - 文件加密：上传前 SDK 帮你 AES-GCM 加密，私钥不出本机；
  - 带宽自适应：根据 audit 里历史 latency 选最快 peer。

---

## D. 去中心化 webhook / push notifier

> 你订阅别人的事件流，事件主人主动推到你 daemon，按订阅时间收费。

- **核心**：`bidi-ws` 模式、`per_minute` 计费。
- **MVP**：A 注册一个 `news-svc`，paths=`/subscribe`，modes=`bidi-ws`；B 通过 SDK 的 `ws_url("news-svc")` + `websockets` 库连上去，A 每 5 秒推一条新闻；A 按分钟扣 B 的钱。
- **加分**：
  - 推送过滤：B 在握手时发 `{topics:["bitcoin","ai"]}`，A 只推匹配的；
  - 多消费者扇出：A 内部维护 connection pool，一次抓取推给 N 个订阅者；
  - 消费回执：B 收到一条就回 `{ack: id}`，A 写进 audit。

---

## E. 多 agent 自动协作完成复合任务

> 「翻译 + 摘要 + 情感」、「OCR + 实体抽取 + 入库」一类的流水线，每环都是独立 agent，自动 discover & 串接。

- **核心**：service-of-services（你的服务也是其他服务的客户端）、`discover --skill`、跨节点 audit 对账。
- **MVP**：抄 `examples/03-multi-agent-pipeline/`，把翻译换成 OCR、摘要换成实体抽取、情感换成 KG 入库。
- **加分**：
  - 链路里某一跳故意限流，演示 SDK 自动选其他 provider；
  - 一份长输入分片处理 + 并行扇出，结果按顺序合并；
  - **判分友好**：评委只要在他们自己的笔记本上 `discover --skill=<your top-level>`，调一次就能看到全链路 audit。

---

## F. 本地工具 MCP-over-P2P

> 任何 [MCP server](https://modelcontextprotocol.io/)（filesystem / git / sqlite / playwright …）一键 p2p 化，全网 agent 都能用。

- **核心**：`bidi-mcp-stdio` 传输模式、把 MCP server 的 stdin/stdout 桥接到 P2P stream。
- **MVP**：起一个 npx @modelcontextprotocol/server-filesystem，注册成 `fs-svc` modes=`bidi-mcp-stdio`，让另一个 daemon 上的 Claude / GPT agent 通过 MCP 协议远程访问你的文件夹。
- **加分**：
  - 路径白名单：在 daemon 配置里限制只允许某些目录；
  - 操作审计：每个 `tools/call` 写一条 `svc_call_log`，事后能追责；
  - 多 MCP server 同时挂出去，组成「全网共享工具集市」。

---

## 小提示

- 不要在「自己也不知道为啥要 P2P」的产品上耗时间。先问自己：**为什么这个东西必须分布式？** 答得清楚的题更容易拿到「复用 anet 能力」高分。
- 评委更看重 demo **能不能在他们机器上 5 分钟内跑通**。所以 starter 模板的 README + `bash scripts/two-node.sh start` 必须无脑能跑。
- 没什么主意时直接抄一个上面的方向 + 把它做扎实，比天马行空但跑不动好太多。
