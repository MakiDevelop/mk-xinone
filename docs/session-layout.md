# Session layout contract

每一輪 council 寫入一個目錄。UI／CLI／同事交接都以**該目錄**為 SSOT。

## 路徑

```text
sessions/<YYYY-MM-DD>-<slug>/
```

`slug`：短橫線小寫，來自目標摘要或 `--out`。

## 檔案

| 路徑 | 必填 | 說明 |
|------|------|------|
| `input.md` | yes | 使用者原始輸入 |
| `meta.json` | yes | preset、席位表、時間、狀態 |
| `seats/<seat_id>.json` | yes | 每席結構化輸出 |
| `logs/<seat_id>.log` | no | 該席 stdout／trace（terminal 面板） |
| `synthesis.json` | yes | 共識／分歧／盲點（機器可讀） |
| `verdict.md` | yes | 人可讀判決卡 |
| `REPORT.md` | no | 完整報告 |
| `graph.json` | no | 分歧圖專用 |

## meta.json（最小）

```json
{
  "schema": "mk-xinone.session.meta.v1",
  "id": "2026-08-12-demo-repo-council",
  "preset": "council-lite",
  "status": "completed",
  "created_at": "2026-08-12T00:00:00+08:00",
  "seats": [
    {"id": "architect", "role": "Architect", "status": "done"},
    {"id": "analyst", "role": "Analyst", "status": "done"},
    {"id": "engineer", "role": "Engineer", "status": "done"}
  ]
}
```

`status`：`running` | `completed` | `blocked` | `failed`

## seats/<id>.json（最小）

```json
{
  "schema": "mk-xinone.seat.v1",
  "id": "architect",
  "role": "Architect",
  "status": "done",
  "one_line_verdict": "...",
  "key_points": ["..."],
  "risks": ["..."],
  "confidence": 4
}
```

## synthesis.json（最小）

```json
{
  "schema": "mk-xinone.synthesis.v1",
  "consensus": ["..."],
  "disagreements": [
    {"topic": "...", "a": "architect", "b": "engineer", "summary": "..."}
  ],
  "blind_spots": ["..."],
  "verdict_label": "WATCH",
  "confidence": 3
}
```

## graph.json（可選）

```json
{
  "schema": "mk-xinone.graph.v1",
  "nodes": [{"id": "architect", "label": "Architect"}],
  "edges": [{"source": "architect", "target": "engineer", "label": "disagrees on X"}]
}
```

變更 schema 時 bump `*.vN`，並更新 demo session。
