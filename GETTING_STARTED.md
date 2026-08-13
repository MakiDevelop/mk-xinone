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

## 跑一輪（mock — 不需 key）

```bash
xinone run "用多角度評估這個想法：本地 session 當 SSOT" --preset council-lite
```

產出目錄預設：`sessions/<date>-<slug>/`（碰撞自動加 `-2`）。  
非空 `--out` 預設拒絕覆寫；需要時加 `--force`。

## 真 backend（OpenAI-compatible / Ollama）

```bash
# 雲端或任意兼容端點
export XINONE_BASE_URL="https://api.openai.com/v1"   # 或自架
export XINONE_API_KEY="sk-..."
export XINONE_MODEL="gpt-4o-mini"
xinone run "評估本地 session SSOT" --preset council-lite --backend openai

# 本機 Ollama（OpenAI 兼容埠）
xinone run "評估本地 session SSOT" --preset council-lite --backend ollama --model qwen3:8b
# 等同 base_url=http://127.0.0.1:11434/v1
```

`xinone doctor --probe` 可探測 `/models` 是否可達。

## 常用指令

| 指令 | 用途 |
|------|------|
| `xinone list-presets` | 列出內建 preset |
| `xinone run "..." [--backend mock\|openai\|ollama]` | 開一輪 council |
| `xinone show <session_dir>\|demo` | 讀本地 session（`--verbose` 全文） |
| `xinone doctor [--probe]` | 檢查目錄／demo／API env |
| `xinone agents` | 偵測目前可用 Agent（runnable 會進 all-hands） |
| `xinone chat [--backend …]` | 跟**主席**對話；其它席預設不發言 |
| `xinone chat` 內 `/council <目標>` | 開會；**預設全員**（有真實 agent 時） |
| `xinone chat` 內 `/agents` | 同 `xinone agents` |
| `xinone run "…"` | 直接開會（有真實 agent 時預設全員） |
| `xinone run … --no-all-agents` | 改用固定 `--preset` |

## 給同事

1. 把整個 `sessions/<id>/` zip 傳過去  
2. 對方 `xinone show path/to/session` 即可重播結論  
3. 不必重跑模型  

## 下一步（開發者）

- Preset：`presets/*.yaml`
- Schema：`schemas/`
- 架構：`docs/architecture.md`
