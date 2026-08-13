# Architecture — mk-xinone

## 分層

```text
[ xinone CLI ]                 ← 使用者只碰這層（v1 無 Web）
         │
[ Orchestrator + Presets ]     ← 一句話 → fan-out 工作席 → 顯性 synthesizer
         │
[ Seat runtimes ]              ← mock | OpenAI-compatible（Ollama/雲端）| 可選 agentX
         │
[ Harness ]                    ← done-gate、no self-accept、wall（M1 硬化）
         │
[ ./sessions/<id>/ ]           ← 本地 SSOT
```

## 顯性 synthesizer（Council A4）

- Preset **必須**宣告 `synthesizer`（或 `chair`）席，不得隱形綜合。  
- 該席出現在 `meta.seats` 與 `seats/<id>.json`，可單獨指定 model。  
- 工作席（architect/…）與 synthesizer **上下文隔離**：synthesizer 只吃各席結構化產出，不吃私有 chain-of-thought log。

## 與相鄰 repo

| 系統 | 本 repo 怎麼用 |
|------|----------------|
| **mk-agentos / agent-contract-kit** | 語意對齊（可選）；**2 週主線不依賴** kit 安裝 |
| **agentX** | 可作 local seat；**不先深綁**；非本產品本體 |
| **私人 skills** | 公司 preset 不進 public |

## 實作邊界

- M0：mock 席位 + 契約 + demo  
- M1：OpenAI-compatible vertical slice + harness 硬閘（見 `docs/NEXT.md`）  
- 不做 persistent multi-PTY farm（非 Herdr）

## 明確非目標

- 取代 Claude Code / agentX 本體  
- Board daemon UI / Web UI（v1）  
- 雲端多人即時房間  
- 使用者手寫 chair-input YAML  
