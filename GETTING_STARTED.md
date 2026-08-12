# Getting started — mk-xinone

## 安裝

```bash
cd mk-xinone
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

需要：Python 3.11+

## 離線 demo（推薦第一站）

不需 API key：

```bash
xinone show sessions/demo-repo-council-2026-08-12
xinone list-presets
```

## 跑一輪

```bash
xinone run "用多角度評估這個想法：本地 session 當 SSOT" --preset council-lite
```

產出目錄預設：`sessions/<timestamp>-<slug>/`

指定輸出：

```bash
xinone run "..." --preset dual-review --out sessions/my-run
```

## 常用指令

| 指令 | 用途 |
|------|------|
| `xinone list-presets` | 列出內建 preset |
| `xinone run "..."` | 開一輪 council（v0 mock 席位） |
| `xinone show <session_dir>` | 讀本地 session，印進度與判決 |
| `xinone doctor` | 檢查 Python／目錄／demo 是否完整 |

## 給同事

1. 把整個 `sessions/<id>/` zip 傳過去  
2. 對方 `xinone show path/to/session` 即可重播結論  
3. 不必重跑模型  

## 下一步（開發者）

- Preset：`presets/*.yaml`
- Schema：`schemas/`
- 架構：`docs/architecture.md`
