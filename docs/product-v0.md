# mk-xinone product v0

## 北極星驗收

一個沒讀過 mk-agentos 的同事，能否在 **5 分鐘內** 用對話／一句指令跑完一輪**有護欄**的多席，並拿到可交結果（本地資料夾）？

## 產品定義

> 一個對話視窗（或一句 CLI）調度 X 位 Agent；內建 Council 式多席與 Harness 護欄；結果落本地；細節可展開。

## 觀眾

- GitHub 陌生人（clone + demo + 可選真跑）
- 同事（zip session、共用 preset）

## 主路徑 / 副路徑

| 優先 | 體驗 |
|------|------|
| P0 | 對話／指令 + 席位進度燈 + 結論卡 |
| P1 | 展開各席摘要、分歧列表 |
| P2 | 分歧圖、完整 terminal/log |
| — | 雲端帳號、Herdr 式 agent farm：**非目標** |

## Harness（使用者無感，系統必做）

- Wall：同錯 2 次 → 停手 + 白話說明  
- Done-gate：宣稱完成前要有可檢查結果  
- No self-accept：dual-review 的 reviewer 不可是 executor  
- 高風險操作需人確認（寫檔／push／刪除 — runtime 接線後）  
- 每輪寫入 `sessions/<id>/`  
- 撞牆時可附 system-gap 一行（可摺疊）

## v0 範圍

| 做 | 不做 |
|----|------|
| Session 目錄契約 + demo | 完整 Web UI |
| Preset YAML + CLI | 真七供應商並跑 |
| Mock fan-out + synthesis 骨架 | 綁死家裡 lab 路徑 |
| 文件對齊 agentX / mk-agentos | rebrand 既有 repo |

## 成功指標（產品）

不是 star 數，而是：

1. 陌生人能否只靠 README 跑通 demo  
2. 同事能否不重跑模型就理解判決  
3. 是否**預設**帶護欄，而不是靠使用者自律  
