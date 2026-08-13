# PRD — mk-xinone 自然語言開會 + 可指派主席 + 確認卡

| 欄位 | 內容 |
|------|------|
| 狀態 | **Maki ratify 2026-08-13**（可開工） |
| 產品 | mk-xinone（CLI-first；**不做** Web UI / Herdr multi-PTY） |
| 來源 | `~/Documents/agent-council/2026-08-13-xinone-nl-chair-ux/`（Codex + Gemini + SYNTHESIS） |
| 執行 | **另一 session 實作**；本檔為施工 SSOT |
| 相關 | `docs/product-v0.md`、`docs/architecture.md`、`docs/NEXT.md` |

---

## 1. 問題

現行 `xinone chat` 要記一堆 slash（`/council`、`/agents`、`/preset`…），且：

- 開會語意過寬（「評估／風險」就 fan-out）→ 易誤開會  
- 主席固定 persona，不能「讓 Codex 當主席」  
- all-hands 易變成「多個 Ollama 模型全員」而非身份  
- CLI agent（Claude/Codex/Gemini）偵測到但**不能入席／主持**  
- 結果難撿（缺 ls / latest）

**目標體驗：** 在 Terminal 裡用人話開會、指派主席；slash 只當逃生口。

---

## 2. 目標 / 非目標

### 做

1. **自然語言主路徑**：convene、appoint/revoke chair、list agents、show last session、chat-only — **不必 slash**  
2. **確認卡**：偵測到開會意圖後，**先確認再** `run_council`  
3. **啟動時指派預設主席**：從候選人池選第一個可用者  
4. **中途可改主席**：「讓 X 當主席」「你來當主席」「恢復預設」  
5. 能力誠實：`detected` / `chair_capable` / `seat_runnable` 分開  
6. Session 仍落 `sessions/<id>/`；harness（done-gate、no_self_accept、wall）**不放寬**

### 不做（本 PRD 範圍外）

- Web UI、Herdr 式 multi-PTY farm  
- 靜默 fallback 主席  
- LLM 單獨授權開會（無明確 multi-seat 語意）  
- 本 PRD 不強制完成 CLI seat runner（P1）；但 **chair_capable 必須誠實**（不能主持就說不能）

---

## 3. 使用者故事

1. 我開 `xinone`，看到「主席：Codex…」，不用設 env 才懂誰在回。  
2. 我說「先不要開會，幫我整理三點」→ 只有主席回。  
3. 我說「讓 Gemini 當主席」→ 提示符變 `Gemini（主席）>`，**還不開會**。  
4. 我說「召集大家評估 dig chunk 策略」→ **確認卡** → Enter → 多席跑 → session 路徑。  
5. 我說「上一場會議怎樣？」→ 顯示 latest session，不重跑。  
6. 我打 `/council …` 仍可用（進階／測試），但 help 不教一堆 slash。

---

## 4. 已拍板決策（不可在實作時偷改）

| # | 決策 |
|---|------|
| D1 | **確認卡：要。** 開會意圖 → 卡 → Enter/Y 才 `run_council` |
| D2 | **預設主席：啟動時指派**，候選人池：Claude, Codex, Gemini, Agy, Grok, Qwen, Gemma |
| D3 | Slash **降級**為隱藏相容；歡迎語只給人話例句 |
| D4 | 「評估／分析／風險」** alone 不得**自動開會；需 multi-seat 訊號 |
| D5 | 指派失敗 **禁止靜默換人**；保留原主席並說明 |
| D6 | v1 仍 **CLI only**；產品線 A = mk-xinone |

### D2 細節 — 啟動指派

候選人標籤（解析到實際 agent）：

| 標籤 | 預期 runtime |
|------|----------------|
| Claude | Claude Code CLI |
| Codex | Codex CLI |
| Gemini | Gemini CLI |
| Agy | agentX |
| Grok | Grok runtime（CLI/API，接上才 capable） |
| Qwen | Ollama qwen* chat 模型 |
| Gemma | Ollama gemma* |

啟動流程：

1. `discover_agents()`  
2. 依 **優先序**（預設見 §6）在池中找第一個 `chair_capable=yes`  
3. 設 `default_chair` = `active_chair`  
4. 印：`主席：{Label}（可改：讓 Gemini 當主席）`  
5. 皆無 → mock 主席 + 明示；不裝有  

中途：「恢復預設」→ 回到啟動的 `default_chair`。

### D1 細節 — 確認卡

觸發：`convene` 意圖（NL 或 `/council`）且有 goal（或澄清後有 goal）。

卡上至少顯示：

- 議程目標  
- 主席（active_chair）  
- 預計席次 N（all-hands 或 preset）  

輸入：

| 輸入 | 行為 |
|------|------|
| Enter / `y` / `Y` / `是` / `開` | 執行 `run_council` |
| `n` / `N` / `取消` / `不要` | 取消；chat-only 本輪 |
| `讓 X 當主席` | 改 active_chair，**重繪確認卡**，仍不開會 |
| 其它閒聊句 | 取消確認狀態，當一般 chair reply |

---

## 5. 自然語言意圖（不必 slash）

優先序：矛盾/缺參 → clarify → chat_only → chair 變更 → read-only → convene → reply。

| 意圖 | 中文例 | 行為 | 建 session？ |
|------|--------|------|----------------|
| appoint_chair | 讓 Codex 當主席；你來當主席 | 更新 active_chair | 否 |
| revoke_chair | 恢復預設主席；不要讓 Codex 當主席了 | 回到 default_chair | 否 |
| stay_chat_only | 先不要開會；只跟你聊 | chat_only lock | 否 |
| list_agents | 有哪些 agent；誰能當主席 | 能力表 | 否 |
| show_last_session | 上一場會議；最近 session | latest session show | 否 |
| convene | 召集大家開會評估 X；請多個 agent 比較 A/B；開 council … | **先確認卡**再 run | 確認後 yes |
| clarify | 開個會（無目標） | 問一個問題 | 否 |
| reply | 嗨；整理三點 | 主席 alone | 否 |

**Convene 明確訊號（collective）示例：**  
開會、召集大家、多個 agent、多席、council、請大家審議  

**不得單獨觸發 convene：**  
評估、分析、風險、方案（無 collective 訊號時 → reply 或 clarify「要正式多席嗎？」）

**Atomic plan：**「讓 Codex 當主席，召集大家評估 X」→ 先 appoint（成功）→ 確認卡 → run。appoint 失敗則**整包不開會**。

---

## 6. 預設優先序（可配置，預設如下）

```text
Claude > Codex > Gemini > Grok > Qwen > Gemma > Agy > mock
```

實作允許：

- `xinone chat --chair Codex`  
- 之後：`~/.config/xinone/config.toml` 的 `default_chair_order`（可 P1）

---

## 7. 資料模型（最小）

```python
# 概念；檔案落點見 §8

IntentPlan:
  primary: reply | convene | list_agents | show_last_session | clarify | exit
  chair_change: keep | appoint | revoke
  chair_ref: str | None          # 使用者字串 "Codex"
  goal: str | None
  question: str | None           # clarify 用
  reason: str

ChairAssignment:
  agent_id: str                  # e.g. cli:codex, ollama:qwen3_8b
  label: str
  source: default | user-explicit
  appointed_at_turn: int

ChatState:
  history, turns
  default_chair: ChairAssignment
  active_chair: ChairAssignment
  convene_mode: normal | chat_only
  pending_confirm: ConveneCard | None   # 確認卡狀態
  last_session_id: str | None
```

`AgentInfo` 擴充：

- `aliases: list[str]`  
- `chair_capable: bool`  
- `chair_unavailable_reason: str`  
- 保留 `available` / `runnable`（seat）

**規則：**  
- `chair_capable` 僅當有 adapter 能完成 Chair 對話與結構化輸出  
- 目前 CLI 若尚無 chair adapter → `chair_capable=false`，NL 指派時**明示不能**，不裝能  

Session `meta.json` 可選欄位：

```json
"chair": {
  "agent_id": "cli:codex",
  "label": "Codex",
  "source": "user-explicit",
  "appointed_at_turn": 3
}
```

禁止寫入 secrets、完整 chat history、API key。

---

## 8. 檔案級變更清單

| 檔案 | 變更 |
|------|------|
| `src/mk_xinone/chair.py` | IntentPlan parser；收窄 convene；chat_only；與 model reply 分離 |
| `src/mk_xinone/agents.py` | chair_capable、aliases、`resolve_agent_ref()`；優先序選 default chair |
| `src/mk_xinone/session_io.py` | `list_sessions()` / `latest_session()` |
| `src/mk_xinone/cli.py` | NL 先解析；確認卡 REPL；`Label（主席）>`；無 subcommand → chat（若尚未） |
| `src/mk_xinone/orchestrator.py` | 可選傳入 chair meta 寫入 session |
| `schemas/meta.schema.json` | optional `chair` |
| `tests/test_chair.py` 等 | §10 驗收句 table-driven；sessions_dir → tmp_path |
| `README.md` / `GETTING_STARTED.md` | 人話例句；slash 降級 |

P1（可另 PR）：

- `backends/cli_chair.py`：Claude/Codex/Gemini 真 chair adapter  
- all-hands 身份優先（禁 4× ollama flood）  
- `xinone ls` 子命令（若 NL show_last 不夠）

---

## 9. 確認卡 UI 規格（Terminal 純文字）

```text
==================================================
 開會確認
--------------------------------------------------
 目標：{goal}
 主席：{chair_label}
 席次：{n}（{preset_or_all_hands}）
==================================================
 Enter / Y  → 召集開會
 n / 取消   → 只跟主席聊
 或輸入：讓 Gemini 當主席
==================================================
確認> 
```

---

## 10. 驗收（必須全綠）

| # | 使用者輸入 | 期望 |
|---|------------|------|
| 1 | `嗨，先跟你聊聊。` | reply only；無 session |
| 2 | `先不要開會，幫我整理三點。` | chat_only；soft convene 無效 |
| 3 | `召集大家開會，評估本地 session 當 SSOT。` | **確認卡** → Enter → session + harness |
| 4 | `請多個 agent 比較方案 A 和 B。` | 確認卡 → 可開會 |
| 5 | `開個會。` | 問目標；無 session、無卡 |
| 6 | `讓 Codex 當主席。` | 若 capable：active=Codex，提示未開會；不能則說明並保留 |
| 7 | `你來當主席，召集大家評估這份提案。` | appoint 當前 responder → 確認卡 goal=提案 |
| 8 | `不要讓 Codex 當主席了，恢復預設。` | revoke；無 session |
| 9 | `現在有哪些 agent？誰能當主席？` | 能力表；無 session |
| 10 | `顯示上一場會議結果。` | latest session show；無新 session |

**負向：**

- `幫我評估 X 的風險`（無 collective）→ 不得直接確認卡開會  
- `不要開會，但召集大家評估 X` → 一個澄清問題  
- `讓 qwen 當主席` 且兩個 qwen → 不得任選第一個  

**自動化：** mock-only pytest；sessions 寫入 tmp_path。

---

## 11. 成功指標（Daily driver）

> 在任意專案目錄執行 `xinone`，看到啟動時主席，用一句「讓 X 當主席，召集大家評估 …」經確認卡完成開會，**全程不必記 slash、不必手動 activate 一堆心智負擔**（全域安裝可 P1，但意圖解析 P0 必達）。

---

## 12. 實作順序（給下一個 Grok session）

```text
1. 讀本 PRD + SYNTHESIS 目錄（勿重開產品邊界）
2. 寫 failing tests（§10）
3. agents.py capability + resolve + pick_default_chair
4. chair.py IntentPlan + chat_only + 收窄 convene
5. session_io list/latest
6. cli.py 接 parser + 確認卡 loop + 主席提示符
7. meta.chair 可選
8. README 例句
9. pytest 全綠；mock run 手測一輪
10. 更新 docs/NEXT.md 一行 pointer 到本 PRD
```

**Verify：** `pytest` 綠 + 手動 `xinone chat --backend mock` 走 §10 句 1–5、6（mock 主席）、3 確認卡。

---

## 13. 風險

| 風險 | 緩解 |
|------|------|
| 真 CLI 尚不能當主席 | 誠實 chair_capable=false；P1 adapter |
| 確認卡多一步 | 已 ratify 要；接受 |
| all-hands 仍 flood | P0 確認卡顯示 N；P1 改 roster |
| 誤解析 convene | collective signal 硬條件 + 確認卡雙保險 |

---

## 14. 參考路徑

- Council：`~/Documents/agent-council/2026-08-13-xinone-nl-chair-ux/`  
  - `codex-answer.md`、`gemini-answer.md`、`SYNTHESIS.md`  
- 現況 code：`src/mk_xinone/{cli,chair,agents,session_io,orchestrator}.py`  

---

**End of PRD.** 實作 session 開場請讀本檔 §4 + §12，不要重新發明 Web UI。
