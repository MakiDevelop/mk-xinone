# M1 五分鐘陌生人驗收紀錄

> 目標：5 人中 ≥4 無人協助、5 分鐘內完成 S1（真 backend 成功路徑）。  
> 本檔先提供**流程 + 自測樣本**；陌生人欄位待真人填。

## 流程（給受測者）

1. `git clone` / 取得 repo  
2. `python3 -m venv .venv && source .venv/bin/activate && pip install -e .`  
3. 確認 Ollama 或 API（或只用 mock 則標 **mock path**，不算 S1 通過）  
4. `xinone doctor`  
5. `xinone run "評估：本地 session 當 SSOT 是否合理" --preset council-lite --backend ollama --model <model>`  
   或 `xinone chat --backend ollama` 後貼同一句  
6. 確認：進度可見、`status=completed`、`mode=real`、能指出 `session` 路徑  

## 自測（operator）— 2026-08-13

| 欄位 | 值 |
|------|-----|
| 受測者 | Maki 工作站 operator（Grok 代跑） |
| 環境 | macOS, mk-xinone @ main, Ollama qwen3:8b |
| 指令 | `xinone run "用一句話評估：本地 session 當 SSOT 是否合理" --preset council-lite --backend ollama --model qwen3:8b` |
| 耗時 | < 2 min（4 席串行） |
| mode | **real** |
| status | **completed** |
| 分歧可見 | 是（Architect vs Analyst/Engineer） |
| 無人協助 | N/A（開發者自測） |
| S1 | **PASS（自測）** |

## 陌生人欄位（待填 ×5）

| # | 日期 | 受測者 | 環境 | backend | 耗時 | 無人協助? | S1 | 阻塞 |
|---|------|--------|------|---------|------|-----------|-----|------|
| 1 | | | | | | | | |
| 2 | | | | | | | | |
| 3 | | | | | | | | |
| 4 | | | | | | | | |
| 5 | | | | | | | | |

## 判定

- [ ] ≥4/5 S1 PASS → M1 陌生人門檻達標  
- [x] 工程 vertical slice + 自測 real 通過（2026-08-13）  
- [ ] 未達標時：依阻塞改 README / doctor / chat 文案（不開 Web）  
