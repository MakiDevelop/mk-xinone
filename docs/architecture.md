# Architecture — mk-xinone

## 分層

```text
[ Chat UI / xinone CLI ]     ← 使用者只碰這層（本 repo 產品臉）
         │
[ Orchestrator + Presets ]   ← 一句話 → 選 preset → fan-out → synth
         │
[ Seat runtimes ]            ← agentX / Claude / Codex / Gemini / mock
         │
[ Harness ]                  ← done-gate、no self-accept、wall（對齊 mk-agentos 語意）
         │
[ ./sessions/<id>/ ]         ← 本地 SSOT
```

## 與相鄰 repo

| 系統 | 本 repo 怎麼用 |
|------|----------------|
| **mk-agentos / agent-contract-kit** | 對齊 loop / dual-review / gap 語意；可選依賴，不強迫 clone 整包 OS |
| **agentX** | 可作 local seat + tools；**不要**把 mk-xinone 做成第二個 Ollama shell |
| **~/.claude skills（七位／vendor）** | 私人／公司 preset 來源；public 只留通用骨架 |

## v0 實作邊界

- Orchestrator 可先 **mock 席位**（固定結構化輸出），契約先穩  
- 真模型接線後：同一 session 目錄格式不變  
- 不做 persistent multi-PTY farm（非 Herdr）

## 明確非目標

- 取代 Claude Code / agentX 本體  
- Board daemon UI  
- 雲端多人即時房間  
- 使用者手寫 chair-input YAML  
