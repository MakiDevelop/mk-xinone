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
| 2 | Session lifecycle 修補 | 不覆寫；running→終態；原子寫入；secrets 不落盤；測試綠 | pending |
| 3 | OpenAI-compatible SeatRunner | 真/假 server 測；seat.v1；可指 Ollama | pending |
| 4 | `council-lite` 真跑 | `xinone run` 非 mock 判決；meta 標 real | pending |
| 5 | Harness 硬閘 | Done-gate + no_self_accept 單測全過；未過不得 `completed` | pending |
| 6 | CLI 進度 + 濃縮輸出 | 預設進度+結論；`--verbose` 展開；mock 浮水印 | pending |
| 7 | 顯性 synthesizer + doctor 升級 | preset 宣告 synthesizer；doctor 查 API/key 白話 | pending |

### 可選（不進 2 週必達）

- `xinone chat` 薄 REPL  
- 5 人陌生人實測記錄  

---

## M0（已完成）

- [x] repo 骨架、Apache-2.0  
- [x] session 契約 + demo  
- [x] presets + `xinone` CLI mock  
- [x] Council 發想 + Maki ratify A1–A7  
- [x] README 誠實標示 harness 狀態（A5）  

---

## 歷史草案（作廢為施工順序）

舊 M1/M2/M3 三段鬆散 milestone **已由 vertical slice 取代**（Codex 異議 A1 採納）。  
細節只保留在 git 歷史，勿再當施工順序。
