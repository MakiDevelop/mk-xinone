# GOAL — mk-xinone daily driver

- **Status:** done
- **Owner agent:** grok
- **Line / project:** mk-xinone
- **Started:** 2026-08-13
- **Updated:** 2026-08-13 18:30

## Intent（一句話）

讓 Maki 在任意目錄打 `xinone`，看到真主席、能指派 Codex/Claude、確認卡後開會不是 4 個 Ollama 灌進來。

## Definition of Done（可勾選、可驗證）

- [x] Claude/Codex/Gemini/Grok 在 PATH 上 → `chair_capable=yes`，seat 仍 `no`
- [x] 主席回話走 active_chair 的 adapter（CLI 或該顆 Ollama），不是空標籤
- [x] all-hands 每個身份最多 1 席（3 個 qwen + 1 gemma → 2 worker + synth）
- [x] 歡迎語只推薦當前 `chair_capable` 的名字
- [x] `~/.local/bin/xinone` 可從 `/tmp` 執行
- [x] VERIFY: `.venv/bin/pytest -q` → 全綠
- [x] VERIFY: `/tmp` 開 `xinone`，`讓 Codex 當主席` → 已由 Codex 主持、尚未開會

## Out of scope / 紅線

- 不做 Web UI / Herdr
- 不做 CLI 當 council seat runner（下一階段）
- 不呼叫 `--dangerously-bypass-approvals-and-sandbox`
- 不改治理檔
- pytest 不打真實 CLI（subprocess mock）

## Verify suite（完成前必跑）

```bash
cd ~/GitHub/mk-xinone && .venv/bin/ruff check src/mk_xinone tests && .venv/bin/pytest -q
which xinone
printf '%s\n' '讓 Codex 當主席。' '/quit' | xinone chat --backend mock --no-all-agents
```

## Progress log

| 時間 | 完成 | 證據 |
|------|------|------|
| 18:10 | GOAL 鎖定 | 本檔 |

## Attempts（撞牆計數）

| 問題 | 次數 | 最後證據 | 狀態 |
|------|------|----------|------|
| | 0 | | open |

## Blockers（等 Chair / 外部）

- （無）

## Notes

- 主席 CLI 用 print/exec 單輪；失敗 fail closed，不靜默換人
- all-hands 同身份取較小模型當席
