# M1 Acceptance — Guarded vertical slice

> Ratified 2026-08-13（council A1–A6）  
> 未全部通過前，**不得**宣告 M1 完成，也不得在 README 宣稱 harness 已完整啟用。

## 成功定義（一句）

陌生人用 README，在乾淨環境 **5 分鐘內** 完成一次 **real**（非 mock）`council-lite` run，看到進度與判決，並找到可 zip 的 `sessions/<id>/`。

## 情境表

| ID | 情境 | 預期 CLI | `meta.status` | 必備 artifacts | exit |
|----|------|----------|---------------|----------------|------|
| S1 | 真 backend 成功 | 進度 → 判決卡 | `completed` | seats/*、synthesis、verdict、input、meta | 0 |
| S2 | API timeout / 連線失敗 | 白話錯誤 | `failed` | meta + 部分 logs；**不得**假 completed | ≠0 |
| S3 | 模型回傳 malformed JSON | 白話 + 可重試提示 | `failed` 或 seat `failed` | 失敗席位有記錄 | ≠0 |
| S4 | dual-review：Reviewer FAIL | 不得宣稱完成 | `blocked` 或 `failed` | executor + reviewer seats；verdict 說明未過 | ≠0 |
| S5 | dual-review：同 actor 自審 | 硬拒 | 不進入 completed | 錯誤說明 no_self_accept | ≠0 |

## Capability 標示（對外）

| 能力 | M0 | M1 目標 |
|------|----|---------|
| mock run | yes | 保留，且浮水印 |
| real backend | no | yes |
| done-gate enforced | no | yes |
| no_self_accept enforced | no | yes |
| wall (2×) | planned | yes（至少 dual-review） |
| Web UI | no | **不做** |

## 5 人陌生人測試（可選加強，不阻塞工程合併）

- 目標：5 人中 ≥4 無人協助、5 分鐘內完成 S1  
- 記錄：`docs/validation/m1-five-minute-test.md`（建立於實測時）
