# mk-xinone

**Chat to run a council. Guardrails included. Sessions stay on disk.**

用**一個對話／一句指令**調度 X 位 Agent，背後帶 Council 式多席與 Harness 護欄。  
不必懂 edge contract、hook 或 mk-agentos 才能跑完一輪。

> **Product face:** 輕鬆使用 X 位一體  
> **Not:** Herdr（coding agent 終端）、也不是本地 Ollama shell（那是 [agentX](https://github.com/MakiDevelop/agentX)）

---

## 5 分鐘劇本（驗收）

```bash
git clone https://github.com/MakiDevelop/mk-xinone.git
cd mk-xinone
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# 離線看 demo（不需 API key）
xinone show sessions/demo-repo-council-2026-08-12

# 跑一輪（v0：結構化 mock / 本機可擴真模型）
xinone run "用多角度評估 https://github.com/example/hello" --preset council-lite
```

成功標準：

1. 看到 **席位進度**（誰 running / done）
2. 得到 **白話結論 + 判決**
3. 磁碟多出 `sessions/<id>/` 可 zip 給同事
4. **沒有**要求你先寫 YAML 或跑 `ack_*` CLI

---

## 這是什麼 / 不是什麼

| 是 | 不是 |
|----|------|
| 對話調度的 multi-seat council | 多 bot 無結構群聊 |
| 預設開啟 harness（完成門檻、禁自驗、撞牆） | 黑箱「AI 說做完了」 |
| 結果落 **本地資料夾** | 雲端帳號產品 |
| Preset 一鍵（3 席／雙人 review／…） | 要求使用者懂七供應商路由 |

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
