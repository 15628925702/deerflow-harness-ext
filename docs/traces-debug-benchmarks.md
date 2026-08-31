# TRACES 向调试基准

筛选标准：断网或仅环境内工具、可执行世界、过程/提交可验证、科学发现或长程工具使用。不收录公网搜索 QA。

## 已落地（本仓库）

| 基准 | 路径 | 规模 | 为何贴合 | 状态 |
|---|---|---|---|---|
| executable-world | `benchmarks/executable-world/` | 5 练习任务 | TRACES 官方接口：typed actions、预算、陷阱、隐藏真值 | 已有，可跑 |
| DiscoveryWorld | `benchmarks/discoveryworld/` | 约 120 题（8 主题 × 难度 × 种子） | 本地科学发现模拟器：假设→实验→分析→结论；Gym 式动作接口；三套过程指标 | 已 clone，需 `pip install -e .` |
| ScienceAgentBench | `benchmarks/scienceagentbench/` | HF 102 题（调试集只跑前 3 条） | 真实论文数据任务，目标是交一份可执行 Python | 仓库已 clone；官方打分需 artifacts zip |
| TheAgentCompany | `theagentcompany/` | 175 题 | 本机 Docker 办公栈，无 Google；测长程工具与提交 | 仓库已有，服务镜像仍在拉；调试集只探测 4 张简单题镜像 |

**怎么跑（单 key、顺序、禁止并发）：** 见 `docs/debug-suite.md`。

```bash
python harness/examples/run_debug_suite.py
```

DiscoveryWorld 安装（本机、不联网评测）：

```bash
cd G:\0-newResearch\5.ApodexHarness\benchmarks\discoveryworld
pip install -r requirements.txt
pip install -e .
```

人机界面：`python scripts/userstudy.py`  
Agent API：`DiscoveryWorldAPI.loadScenario(...)` 后逐步 `performAction`，与 executable-world 的 `ep.act` 同类。

ScienceAgentBench 不要走官方 `ScienceAgent` + litellm（绑死了 `model_cost`，填不进 `apodex-1.1`）。调试集用 `harness/examples/sab_debug_agent.py`。完整执行评分还需 SharePoint zip，密码见官方 README。

## 建议后续再下（未 clone，避免再占几十 GB）

| 基准 | 贴合点 | 代价 | 何时再下 |
|---|---|---|---|
| [SciCode](https://github.com/scicode-bench/SciCode) | 科研问题拆成子题再写成可运行代码 | 中等，偏写代码不是「看世界」 | SAB 不够用、还要测子题分解时 |
| [Terminal-Bench](https://www.tbench.ai/) | 终端里长程真实任务，每题独立环境 | 多 Docker 镜像，类似 TAC | 不要和 TAC 同时拉 |
| [CORE-Bench](https://github.com/siegelz/core-bench) | 复现论文计算实验 | Docker / 云主机 | 测「提交是否真的跑通」时 |
| ScienceWorld | DiscoveryWorld 的小学版科学实验 | 需 Java，比 DW 简单 | 仅当 DW 对 1.1 模型过难 |

明确不收：BrowseComp 系、GAIA、任何必须 Google/Serper 的深度研究榜。

## 调试优先级（与 suite 顺序一致）

1. executable-world 五题（接口契约）
2. DiscoveryWorld Easy 三个 scenario（发现循环，不断网）
3. ScienceAgentBench 前 3 条（交程序；无 artifacts 则只看生成代码）
4. TheAgentCompany 镜像齐后再跑 1 个简单任务（真实软件栈；本 suite 先做镜像探测）
