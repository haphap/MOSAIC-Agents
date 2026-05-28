# MOSAIC-Agents

> A 股版 ATLAS：自我改进多智能体交易框架。
> 基于 [ETFAgents](https://github.com/haphap/ETFAgents) 的混合架构经验
> （Python sidecar + TypeScript 前端）。

**当前状态**：Phase 0 Day 1（Python sidecar + bridge 骨架）。

完整实施计划见 [`mosaic-tsplan.md`](./mosaic-tsplan.md)（工作主文档）。

## 仓库布局

```
mosaic/                  # Python sidecar（JSON-RPC stdio）
├── bridge/              # 协议 + handler 注册（Phase 0 Day 1）
├── default_config.py    # 运行时默认配置
└── ...                  # dataflows / agents / paper_trading 等将在后续 Phase 落地

mosaic-ts/               # TypeScript 前端（Phase 1+）
prompts/mosaic/          # Cohort 双语 prompt 仓库（Phase 2+）
data/                    # SQLite + 缓存（受 MOSAIC_DATA_DIR 控制；.gitignore）
tests/                   # Python 测试
```

## 快速开始

```bash
# Phase 0 Day 1 验证：bridge 启动并能响应 tools.list
uv venv
source .venv/bin/activate
uv pip install -e .
python -m mosaic.bridge < /dev/null     # 应当干净退出（stdin 为空）

# 用 JSON-RPC 探测：
echo '{"jsonrpc":"2.0","id":1,"method":"tools.list","params":{}}' | python -m mosaic.bridge
# → {"jsonrpc":"2.0","id":1,"result":[]}（Phase 0 Day 1 时工具列表为空）
```

## 关键决策

- **Q1=a**：完整复刻 ATLAS 4 层 25+ agents
- **Q2**：数据 = Tushare + akshare + FRED + opencli/brave
- **Q5=a**：执行层仅 paper trading + backtrader
- **Q6=c**：autoresearch = Git + SQLite 混合
- **默认语言**：Chinese
- **默认 LLM**：Anthropic Claude Sonnet（开发期可切到本地 Lemonade Qwen 零成本）
- **启动 cohort**：`euphoria_2021`

更多决策与详细计划见 `mosaic-tsplan.md`。

## 关联仓库

- [ATLAS 公开版](https://github.com/general-intelligence-capital/atlas)
  （`/home/hap/Projects/atlas-gic/`）— 架构文档 + janus.py + mirofish/ 移植源
- [ETFAgents](https://github.com/haphap/ETFAgents)
  （`/home/hap/Projects/ETFAgents/`）— bridge / dataflows / paper_trading / backtest 复用源

## License

待添加（Phase 9 末确定）。
