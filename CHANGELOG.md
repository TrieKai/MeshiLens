# Changelog

本專案的版本變更紀錄，依 `pyproject.toml`／`extension/manifest.json` 版號與 git commit 整理。格式大致遵循 [Keep a Changelog](https://keepachangelog.com/)。

## [0.5.5] — 2026-07-20

### Fixed
- 僅在明確日本店家顯示 MeshiLens；海外精確座標店家與訊號不足店家皆靜默略過
- URL viewport 座標不再作為店家所在地判定，避免拖曳地圖或瀏覽歷史誤判

## [0.5.4] — 2026-07-20

### Fixed
- 清單店名清除 Maps「開啟過的連結」等造訪尾綴，避免 Michelin badge 配對失敗
- 清單 badge 改用 session 快取與增量回掛，減少閃爍與滑回後消失
- 詳情模式下若 feed 仍在，從快取保留／回掛列表 badge
- 列表 cache key 改採穩定的 `/maps/place/店名`，忽略會變動的 `data=` 片段

### Changed
- 列表 badge 改絕對定位、hint 改固定浮層，降低側欄重排影響

## [0.5.3] — 2026-07-20

### Added
- Michelin 批次比對 API，清單模式可一次處理多張店家卡片
- 清單徽章（list badges）模組，於列表顯示 Michelin 入選標記

### Changed
- 擴充功能整合批次請求與清單 UI

## [0.5.2] — 2026-07-19

### Added
- Maps 清單模式提示（list hint）與 UI 模式（list／detail／map）判斷模組
- Michelin 可依 Tabelog 識別做低頻補配並快取
- `/advice` 改為接受結構化 `facts`（相容 place／candidate），並加強驗證與清理

### Changed
- 重構用餐建議與 Michelin 配對流程
- 清單與詳情模式掃描邏輯分離，減少多餘查詢

## [0.5.1] — 2026-07-19

### Changed
- AI 用餐建議快取 TTL 由 30 天改為 24 小時
- 建議快取鍵改依店家結構化 facts 產生，行為更一致

## [0.5.0] — 2026-07-19

### Added
- 持久化快取：記憶體 L1 + 本機檔案，可選 Redis／Upstash
- 擴充功能端 lookup 快取模組

## [0.4.9] — 2026-07-18

### Fixed
- 避免重複送出 AI 用餐建議請求

## [0.4.8] — 2026-07-18

### Changed
- 對 Groq 請求標示 MeshiLens 身分，便於追蹤

## [0.4.7] — 2026-07-18

### Fixed
- 允許完整回傳的 Qwen 建議 JSON，減少截斷造成的失敗

## [0.4.6] — 2026-07-18

### Changed
- Qwen 改用非 reasoning 的 JSON mode 產生建議

## [0.4.5] — 2026-07-18

### Changed
- 用餐建議改以 Qwen 模型產生

## [0.4.4] — 2026-07-18

### Added
- 以 Tabelog 結構化資料非同步產生繁中「AI 用餐建議」（Groq）
- `/advice` API 與擴充功能建議區塊 UI

## [0.4.3] — 2026-07-18

### Added
- 店家時間線：百名店多年紀錄 + 目前 Michelin 狀態
- `AGENTS.md` 專案指引

## [0.4.2] — 2026-07-18

### Changed
- Tabelog 與 Michelin 並行比對，先完成的一方先顯示於卡片

## [0.4.1] — 2026-07-18

### Added
- Michelin 可依電話、官網補強配對
- 必要時低頻補查附近詳情頁並快取

## [0.4.0] — 2026-07-18

### Added
- 日本 Michelin Guide（繁中 SSR）快照與店家入選資訊顯示
- `scripts/update_michelin.py` 低頻更新快照

## [0.3.7] — 2026-07-18

### Added
- MeshiLens 品牌圖示

## [0.3.6] — 2026-07-18

### Added
- Tabelog 預約狀態與線上預約按鈕
- 信用卡／電子支付／QR Code 接受狀態與品牌
- 彈出視窗五種主題色設定

## [0.3.5] — 2026-07-18

### Added
- 擴充功能啟用／停用開關；停用後立即移除評分卡並停止查詢

## [0.3.4] — 2026-07-18

### Fixed
- Maps 網址含多組座標時，改用目前店家座標

## [0.3.3] — 2026-07-18

### Added
- 未知餐飲類別的啟發式判斷（菜單、價位、內用等）
- Maps 英文譯名時一併擷取當地語言店名

## [0.3.2] — 2026-07-18

### Fixed
- 咖啡廳類別辨識
- 座標補強與配對

## [0.3.1] — 2026-07-18

### Changed
- 略過非餐飲的 Google Maps 地點，不顯示也不呼叫 API

## [0.3.0] — 2026-07-18

### Added
- 百名店歷史與更完整的店家詳情（價位、車站、營業資訊等）

## [0.1.0] — 2026-07-17

### Added
- 初版 MVP：Google Maps 監聽、Tabelog 配對與評分卡
- 本機 Python 配對服務（`meshilens-server`）
- Vercel 雲端 API 部署與擴充功能連線（含東京區域設定）
