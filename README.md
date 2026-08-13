# mk-xinone

**Chat to run a council. Sessions stay on disk.**  
**Guardrails: planned / partial**（M0 = mock + 契約；M1 = 真 enforcement，見下方能力表）

用**一個對話／一句指令**調度 X 位 Agent，背後帶 Council 式多席與 Harness 護欄。  
不必懂 edge contract、hook 或 mk-agentos 才能跑完一輪。

> **Product face:** 輕鬆使用 X 位一體  
> **Not:** Herdr（coding agent 終端）、也不是本地 Ollama shell（那是 [agentX](https://github.com/MakiDevelop/agentX)）

---

## 能力現況（誠實表）

| 能力 | 狀態 |
|------|------|
| 離線 demo session | **yes** |
| `xinone run` mock 席位 | **yes**（浮水印） |
| OpenAI-compatible / Ollama 真 backend | **yes**（`--backend openai\|ollama`） |
| Done-gate / no_self_accept 硬擋 | **yes**（未過不得 `completed`） |
| Wall 2× 重試 | **yes** |
| `xinone chat` REPL | **yes**（人話開會 + 確認卡 + CLI/Ollama 真主席） |
| Session 不覆寫 / 原子寫 / redact | **yes** |
| Web UI | **不做**（v1 = CLI only） |

施工單：[`docs/NEXT.md`](docs/NEXT.md) · 驗收：[`docs/m1-acceptance.md`](docs/m1-acceptance.md)

---

## 5 分鐘劇本（驗收）

```bash
git clone https://github.com/MakiDevelop/mk-xinone.git   # 或本機 path
cd mk-xinone
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# 離線看 demo（不需 API key）— 推薦第一站
xinone show sessions/demo-repo-council-2026-08-12

# mock（預設）
xinone run "用多角度評估 https://github.com/example/hello" --preset council-lite

# 真跑（需 API 或本機 Ollama）
# xinone run "..." --preset council-lite --backend ollama --model qwen3:8b

# 看有哪些 Agent 可用（開會預設全員加入）
xinone agents

# 對話 REPL（啟動時指派主席；人話開會，先出確認卡）
# xinone chat --backend mock
# 讓 Codex 當主席
# 召集大家開會，評估本地 session 當 SSOT
# （slash /council 仍可用，只是逃生口）
```

成功標準（產品目標；M1 後對 real run 驗收）：

1. 看到 **席位進度**（誰 running / done）
2. 得到 **白話結論 + 判決**
3. 磁碟多出 `sessions/<id>/` 可 zip 給同事
4. **沒有**要求你先寫 YAML 或跑 `ack_*` CLI

---

## 這是什麼 / 不是什麼

| 是 | 不是 |
|----|------|
| 對話調度的 multi-seat council | 多 bot 無結構群聊 |
| Harness **目標**為完成門檻、禁自驗、撞牆（M1 硬化） | 已完整 enforcement 的黑盒（尚未） |
| 結果落 **本地資料夾** | 雲端帳號產品 |
| Preset 一鍵（3 席 + 顯性 synthesizer／雙人 review／…） | 要求使用者懂七供應商路由 |

進階可展開：席位原文、分歧、log（terminal 投影）。預設只露**對話 + 進度 + 結論**。

---

## 與其他 repo 的關係

| Repo | 角色 |
|------|------|
| **mk-xinone**（本 repo） | 產品臉：preset、orchestrator、session 契約、demo |
| [mk-agentos](https://github.com/MakiDevelop/mk-agentos) | 契約／loop／dual-review harness 語意（可對齊、可選依賴） |
| [agentX](https://github.com/MakiDevelop/agentX) | 本地腦 + 工具 shell（可當一席 runtime，非本產品本體） |

詳見 [docs/architecture.md](docs/architecture.md)。

---

## Session 資料夾（跑完你手上有什麼）

```text
sessions/<date>-<slug>/
  input.md
  meta.json
  seats/*.json
  logs/*.log
  synthesis.json
  verdict.md
  REPORT.md
  graph.json
```

契約： [docs/session-layout.md](docs/session-layout.md)

---

## 狀態

**v0 scaffold** — 目錄契約、preset、CLI 骨架、離線 demo session。  
真多模型 fan-out 與完整 harness 接線為後續 milestone。

產品規格： [docs/product-v0.md](docs/product-v0.md)

---

## License

Apache-2.0 — 見 [LICENSE](LICENSE)。
