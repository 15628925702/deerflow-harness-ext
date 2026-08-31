# Harness 可改问题清单（先记不改）

记录时间：2026-08-30  
约束：模型和基准都不能换，只改 harness。当前评测继续跑，本清单供后续一次性改。

对照现场：BrowseComp-ZH 10%、BrowseComp ~1.3%（75 题时）。绝对分低，但和 GPT-4o+browsing（1.9%）同一档；真正能拉开的是搜索深度和坚持轮次，不是换题。

2026-08-30 16:01 控制台：`apodex-1.1` 在准入阶段大量 **已拒绝**，错误 `rate_limit_exceeded`（账号并发或每分钟 token 上限打满），tokens `0/0/0`。多把测试 key（测试1/4/5/6/9/10/11/12）同一秒被拒。这会把本应做成的题变成空答案，分数比模型真实能力更低。

---

## P0 — 改了最可能涨分（深度研究环）

### 0. 429 重试会打满账号并发，空答案当错题

- **位置：** `browsecomp_agent.py::call_model`：429 时立刻换下一把 key，最多 8 次，退避仅 `1.5*(attempt+1)` 秒
- **位置：** `run_all_benchmarks.py`：`--workers 4`，环境里约 12 把 `APODEX_KEYS`；`answer_question` 失败则 `except: pass`，无预测 → judge 判错
- **现象：** 限流是**账号级**并发/TPM，不是 per-key。4 个 worker 同时 429 后再轮转 12 把 key，控制台会出现「测试6/12/4/1…」同一秒全拒。拒了的请求 0 token，该步等于没推理。
- **建议：** 全局信号量把同时 in-flight 的 chat 请求压到账号并发上限以下（先试 1–2）；429 后指数退避，**不要**换 key 再打（同一账号换 key 只会更挤）；评测日志记下每题 `n_429` / 是否空答案。
- **已落地（调试集）：** `run_debug_suite.py` 强制 `--workers 1`、只用第一把 key、丢掉 `APODEX_KEYS`；`apodex_harness.call_model` 对 429 做同一把 key 的指数退避。不要再跑 `run_all_benchmarks.py`。

---

### 1. 过早强制收束，搜索被掐死

- **位置：** `examples/browsecomp_agent.py` → `answer_question`，`max_steps=12`，`step >= max_steps * 0.5` 时注入 `CONVERGE NOW ... Do NOT search again`
- **现象：** 大约第 6 步起禁止再搜，只能闭卷猜。BrowseComp 需要反复改查询、翻很多页。
- **建议：** 收束改为「预算/步数将近耗尽」才触发（例如最后 2 步）；中间步只提醒「还没交叉验证就不要 final」。探索类任务和提交类任务用不同阈值。

### 2. 允许不搜索直接答

- **位置：** 同一文件 `SYSTEM`：「If you are already confident ... you may reply `final_answer` immediately without searching」
- **现象：** 弱模型最爱走这条。BrowseComp 的答案几乎不在参数知识里，闭卷猜 ≈ 0 分。
- **建议：** 深度研究任务强制至少 N 次 `web_search` + M 次 `web_fetch` 才能 `final_answer`；parametric skip 只留给 trivia/选择题。

### 3. 用「文本里塞 JSON」而不是原生 function calling

- **位置：** `browsecomp_agent.py` / `apodex_harness.py` 的 `_parse_action` / `_extract_action`；请求体只有 `messages`，没有 `tools`
- **现象：** 弱模型经常输出散文或坏 JSON，一轮浪费在「请用 JSON」上；不能并行调多个工具。
- **建议：** 走 OpenAI 兼容 `tools` / `tool_calls`（apodex 接口兼容 chat completions）。JSON 兜底只作为解析失败时的 fallback。

### 4. 搜索工具太浅，没有「搜不到就换打法」

- **位置：** `examples/web_tools.py`
  - `web_search` 固定 `num=5`，无翻页、无 `site:` / 时间 / 地区
  - `web_fetch` 经 Jina，截断 20k；失败只回 `{"error": ...}`
- **位置：** `browsecomp_agent.py` 循环：搜到 snippets 后没有「查询改写 / 换实体 / 换语言」策略
- **现象：** 一次 Google 前 5 条不够；snippets 对 BrowseComp 几乎没用（官方也说要持久浏览）。工具报错后模型常重复同一 query。
- **建议：**
  - 结果数 8–10，支持 `start` 翻页
  - 连续两次搜索无新实体 → 强制改写 query（加引号、换同义词、拆子问题、中英互搜）
  - Jina 失败则直连抓取或换 endpoint；对 PDF/表格给专用抽取
  - 维护「已访问 URL / 已证伪线索 / 候选答案+出处」工作记忆，下一轮只把摘要而不是 4000 字生 JSON 塞进上下文

### 5. 三条独立 run 的 self-consistency 性价比差

- **位置：** `examples/run_all_benchmarks.py`：每题 `answer_question` ×3，再对**字符串** `Counter.most_common`
- **对照：** `run_gaia.py` 里已有 `self_verify` / `cluster_vote`，评测没用
- **现象：** 三次都很浅的失败，多数投票仍是错的；费用 ×3，轮次却不加深。
- **建议：** 同一预算下优先「1 次深搜（更多步、更多 fetch）」而不是「3 次浅搜」。若保留 best-of-N，用语义聚类投票，不要精确字符串。

---

## P1 — 策略层空转 / 评测看不见失败原因

### 6. ContextPolicy 从未真正压上下文

- **位置：** `policies/context.py` 看 `state.context_fraction`；`HarnessState.context_fraction` 默认 0.0，loop 里**从不更新**
- **位置：** `browsecomp_agent.py` 的 `before_model` 只处理 `inject_hint`，忽略 `compact`
- **现象：** 长任务上下文膨胀，旧搜索噪声压过新证据；compaction 是死代码。
- **建议：** 每步按 token/字符更新 `context_fraction`；触发后做「保留 brief + 工作记忆 + 最近 2 次观察」的压缩，并真正执行 `compact` 决策。

### 7. Recovery / Failure / Stall 对搜索任务没有可执行建议

- **位置：** `policies/failure.py` 提示形如 `repeated failure <fingerprint> x3 (tool=web_search)`
- **位置：** `policies/stall.py` 只检测「观察完全相同」
- **位置：** `policies/recovery.py` 成功一次就把 hints 清空
- **现象：** 指纹字符串对模型几乎无用；搜索每次 error 文本略不同则 stall 不触发；偶然一次成功搜索会清掉「该换策略」的提示。
- **建议：** 针对 web 工具给出动作级 hint：换 query、换源、停止重复 URL、必须 fetch 而不是只看 snippet。Stall 用「候选答案/新实体是否增加」而不是 raw 观察相等。

### 8. 评测不落盘，改了无法对照

- **位置：** `run_all_benchmarks.py` 只打印正确数；`except Exception: pass` 吞掉失败
- **现象：** 不知道错在格式、空答案、搜错、还是 judge。无法回归。
- **建议：** 每题写 jsonl：`id, question, pred, gt, ok, judge_reason, n_search, n_fetch, n_parse_fail, error`。轨迹可选另存。进度 checkpoint，中断可续跑。

### 9. Judge 是 GAIA 那套，套在 BrowseComp 上会偏

- **位置：** `run_gaia.py::judge` 被 `run_all_benchmarks.py` 直接调用
- **现象：**
  - 抽「第一个数字」匹配，短数字易误判对
  - 长度 ≥4 的包含匹配，专有名词易误判
  - 短事实题用 LLM-as-judge，比官方规范化 exact match 吵
- **建议：** 按 `answer_type` 分流：BrowseComp / 短事实 → 规范化 exact match；开放题 / rubric → LLM judge；GAIA 保持现有宽松规则。

### 10. 工具失败与限流没有重试阶梯

- **位置：** `web_tools.py` 一次失败即返回 error；`call_model` 只对 429 重试
- **现象：** Serper/Jina/代理抖一下，整题可能提前 final 或空答案。
- **建议：** 搜索/抓取 2–3 次退避；429 换 key（已有 key pool，可复用到 Serper）；记录工具成功率到评测日志。

---

## P2 — 架构与官方 harness 对标（不一定立刻涨 BrowseComp 分）

### 11. 两套 loop，不是一个 harness

- `examples/apodex_harness.py`：executable-world，40 步，40% 步数催 submit
- `examples/browsecomp_agent.py`：深度研究，12 步，50% 步数禁止再搜
- **建议：** 一个 engine + 任务适配器（EW actions vs web tools）；催 submit / 催搜索的阈值按任务类型配置，不要两套复制粘贴。

### 12. 无子问题分解、无并行

- DeerFlow 设计里有 subagent，当前 deep-research 环没用
- BrowseComp 多跳适合「拆成 2–3 个子查询再汇合」
- **建议：** 第一轮只产出 search plan（3–5 个子问题），再串行或并行搜，最后综合。弱模型也吃得下短 plan。

### 13. executable-world 的 SUBMIT 催促过早（已在 EVALUATION.md 提过）

- `apodex_harness.py`：`step >= max_steps * 0.4` 就 REMINDER
- 探索重的任务（procurement）会被催着乱交
- **建议：** 与 P0-1 同一套「按任务类型的收束策略」，阈值可配。

### 14. `max_tokens=1200`（研究）/ `1024`（EW）可能截断

- 弱模型一截断就 JSON 残缺，再浪费一轮修格式
- **建议：** tool 调用轮次用较小 max_tokens；final_answer 轮次加大。或改原生 tool_calls 后不再依赖完整 JSON 文本。

---

## 明确先不动的

- 不换模型、不换基准、不改正在跑的评测进程
- 不把「换更强模型」或「换更简单的题」写进改进范围
- DeerFlow 完整中间件/子代理如果引入过重依赖，作为 P2 可选项，不作为第一批必改

---

## 建议的改动批次（以后执行时）

1. **第一批（深搜环）：** P0-1 收束、P0-2 禁止闭卷、P0-4 查询改写+工作记忆、P1-8 落盘轨迹  
   → 用很小样本（10–20 题 BrowseComp-ZH）A/B，看搜索轮次和准确率，不要立刻全量重跑。
2. **第二批（协议与投票）：** P0-3 原生 tools、P0-5 深搜替代浅投票、P1-9 judge 分流
3. **第三批（策略层真正接上）：** P1-6 compact、P1-7 可执行 hint、P2 统一 loop

第一批不碰正在跑的 690 题评测；等本轮结束或另开实验目录。
