# TRACES 调试集（测试版）

单 key、严格顺序、禁止并发。改 harness 后用这一套循环回归，不要再跑 BrowseComp / `run_all_benchmarks.py`。

## 一次怎么跑

在仓库根目录：

```bash
python harness/examples/run_debug_suite.py
```

常用裁剪：

```bash
python harness/examples/run_debug_suite.py --only ew          # 只跑 executable-world 五题
python harness/examples/run_debug_suite.py --only dw,sab      # 跳过 EW / TAC
python harness/examples/run_debug_suite.py --dry-run          # 只打印任务清单
python harness/examples/run_debug_suite.py --pause 5          # 题与题之间多歇几秒
```

`--workers` 只能是 `1`，传别的会直接退出。

结果目录：`results/debug-suite/<时间戳>/summary.json`。

## 密钥策略

脚本读 `keys/apodex_keys.env`：

1. 只启用 **第一把** key，写成 `APODEX_API_KEY`
2. **立刻丢掉** `APODEX_KEYS`，禁止轮换
3. 模型调用走 `apodex_harness.call_model`：同一把 key，429 指数退避（最多 8 次）

`PYTHONUTF8` / `python -X utf8` 建议在启动时带上；轨迹文件已按 UTF-8 写入，避免 Windows GBK 碰到 `²` 崩掉。

## 任务顺序

清单在 `eval/debug_suite.yaml`。

| 顺序 | stage | 内容 | 缺依赖时 |
|---|---|---|---|
| 1 | `ew` | executable-world 五题：verify_solutions → clinical_signal → corpus_dedup → treatment_response → corpus_procurement | 必跑 |
| 2 | `dw` | DiscoveryWorld Easy × 3：Proteomics / Space Sick / Plant Nutrients，seed=0，最多 20 步 | 未 `pip install` 则 skip |
| 3 | `sab` | ScienceAgentBench：HF 数据集前 3 条，只生成 Python 程序 | 无 `datasets` 或下不了 HF 则 skip |
| 4 | `tac` | TheAgentCompany 4 道简单题：只做镜像就绪探测，**不在本脚本里起容器跑 agent** | 先查 Windows `docker`，没有则查 WSL 发行版 `tac-docker` |

ScienceAgentBench 官方 `ScienceAgent` 绑 litellm 的 `model_cost`，不能直接填 `apodex-1.1`。调试集用自写薄调用层（`sab_debug_agent.py`）。完整打分还要 SharePoint 的 artifacts zip（密码见官方 README：`scienceagentbench`），没有 zip 就只看生成的代码，不算官方分。

TheAgentCompany 需要本机 Docker 任务镜像 + 环境 LLM + 容器内 agent，和 EW/DW 的 `ep.act` 不是同一套接口。镜像齐之前本 suite 只记录哪几张 image 在本地，避免再并发拉 175 个容器。

## 改 harness 的循环

1. 改 `harness/`（策略层或 `apodex_harness.py` 的 prompt / 提交提醒）
2. `--only ew` 先确认五题接口没回退
3. 再 `--only dw` 看发现过程是否还在乱动
4. 需要交代码时 `--only sab`
5. 对比两次 `results/debug-suite/*/summary.json`

不要在调试循环里加 self-consistency、多 worker、或多 key 轮换。
