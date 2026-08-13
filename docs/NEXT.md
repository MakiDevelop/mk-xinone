# NEXT — 唯一施工單（Council ratify 2026-08-13）

> **SSOT for work.** 來源：`~/Documents/agent-council/2026-08-12-mk-xinone-council/`  
> 裁決：A1–A7 全部 RATIFIED。  
> 同時只允許這一條主線；完成定義見 `docs/m1-acceptance.md`。

## 主線（2 週）

**Guarded vertical slice**

OpenAI-compatible 真 backend → `council-lite` 真跑 → 席位進度可見 → Done-gate 真執行 → session 誠實落盤。  
同週：dual-review **no_self_accept** 以測試硬起來；顯性 **synthesizer** 席。

## 明確不做

- Web UI  
- 深綁 agentX / 多 provider 路由  
- mk-agentos kit 對齊  
- 公司 preset 進 public  
- Herdr 式 multi-PTY  

---

## Backlog 1–7（有序）

| # | 項目 | 完成定義 | 狀態 |
|---|------|----------|------|
| 1 | 驗收表 `docs/m1-acceptance.md` | 四～五情境 + 預期 status/exit | **done** |
| 2 | Session lifecycle 修補 | 不覆寫；running→終態；原子寫入；secrets 不落盤；測試綠 | **done** |
| 3 | OpenAI-compatible SeatRunner | 真/假 transport 測；seat.v1；可指 Ollama | **done** |
| 4 | `council-lite` 真跑 | `--backend openai\|ollama`；`mode=real`；本機 Ollama 實測通過 | **done** |
| 5 | Harness 硬閘 | Done-gate + no_self_accept；未過不得 `completed` | **done** |
| 6 | CLI 進度 + 濃縮輸出 | 進度行；mock 浮水印；`--verbose` | **done** |
| 7 | 顯性 synthesizer + doctor | preset 宣告；doctor + `--probe` | **done** |

### Follow-up（逐項）

| # | 項目 | 狀態 |
|---|------|------|
| F1 | `xinone chat` 薄 REPL | **done** |
| F2 | wall 2× 自動重試 | **done** |
| F3 | 五分鐘驗收紀錄 `docs/validation/m1-five-minute-test.md` | **done**（自測 + 模板） |
| F4 | GitHub public | **done**（2026-08-13） |

---

## M0 + M1 vertical slice（已完成）

- [x] repo 骨架、Apache-2.0、private GitHub  
- [x] session 契約 + demo  
- [x] Council A1–A7 ratify  
- [x] Guarded vertical slice 程式 + 測試 + Ollama 實跑  

---

## 歷史草案（作廢為施工順序）

舊 M1/M2/M3 三段鬆散 milestone **已由 vertical slice 取代**。

---

## 後續主線（Maki 2026-08-13）

**NL 開會 + 可指派主席 + 確認卡** — 施工 SSOT：

→ [`docs/prd-nl-chair-convenience-v1.md`](prd-nl-chair-convenience-v1.md)

P0 + P1 日常可用（2026-08-13）：NL convene + 確認卡 + CLI 真主席（Claude/Codex/Gemini/Grok）+ all-hands 身份制。`xinone` 已掛 `~/.local/bin`。

Council 原始討論：`~/Documents/agent-council/2026-08-13-xinone-nl-chair-ux/`
