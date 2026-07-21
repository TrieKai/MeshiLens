# MeshiLens — Agent 指引

在 Google Maps 店家頁顯示 **Tabelog 日本語版**評分與 **Michelin Guide 日本**入選資訊。Chrome／Edge 擴充功能讀取目前店家，Python 服務負責比對。

## 架構

| 路徑 | 職責 |
|---|---|
| `extension/` | Manifest V3 擴充功能（content / background / popup） |
| `src/meshi_lens/` | 本機／雲端配對服務（Tabelog、Michelin、評分） |
| `scripts/update_michelin.py` | 低頻更新日本 Michelin SSR 快照 |
| `tests/` | 不連外網的單元測試 |

擴充功能只向設定的 API（預設本機或 Vercel）發送店家識別資訊；Michelin 快照在伺服器端，瀏覽 Maps 時不直接打 Michelin。

## 常用指令

```bash
uv sync
uv run meshilens-server

PYTHONPATH=src python3 -m unittest discover -s tests -v
node --check extension/background.js
node --check extension/content.js
node --check extension/popup.js
node --test tests/test_settings.js tests/test_toggle.js tests/test_category.js tests/test_maps.js tests/test_timeline.js tests/test_lookup_cache.js tests/test_advice.js tests/test_review_insights.js
```

更新 Michelin 快照：`uv run python scripts/update_michelin.py`

## 慣例

- UI 文案與 README 使用**繁體中文**；程式識別子用英文。
- 變更擴充功能 UI 時同步 `extension/content.css`（或 popup 樣式），並維持現有暖色卡片風格（赤紅 accent、避免紫系／暗黑預設）。
- 前端可測邏輯放进 `extension/*.js` 模組（掛 `globalThis.MeshiLens*`），以 `node --test` 覆蓋；勿只寫在 `content.js` 難以測試的閉包裡。
- 改版本時同步：`extension/manifest.json`、`pyproject.toml`、`src/meshi_lens/__init__.py`、`CHANGELOG.md`，以及依賴版本字串的測試。
- 不要為了「雙標籤／評論語言」去刮 Google Maps 星等或評論內容；配對靠店名、電話、地址、座標、官網。
- 遵守 README「隱私與限制」：低頻請求、不寫 exploit、不大量爬 Tabelog／Michelin。
- 未經要求不要 commit、push 或開 PR。

## 功能邊界（目前）

- 店家時間線：以已取得的百名店多年紀錄 + 目前 Michelin 狀態呈現；不做評分歷史曲線或升降星年表。
- Michelin 詳情（電話／官網）僅在跨語言且必要時低頻補查並快取。
- `/advice` 只接受結構化 `facts`（或相容的 place／candidate）；不接收評論原文或 Maps DOM；與「公開評論實驗摘要」完全分離。
- Michelin 初查與 `/match` 並行；若初查未命中且已有 Tabelog 選定店，可再以 Tabelog 識別做一次低頻補配。
- **公開評論實驗摘要**（`POST /review-insights`）：僅限使用者 **opt-in** 主動點擊後，後端低頻讀取該店**一頁**公開 Tabelog 評論（最多約 5–8 則、總字數受限），暫存於記憶體送 Groq 產生**主題摘要**後立即丟棄原文；只快取摘要（約 7 天）。不做：自動對每店抓評論、擴充功能直接抓 Tabelog、顯示原文／作者／頭像／逐字引言、列表批量抓取、或把評論寫入 `/advice`。不依賴 `gurume` 的 `fetch_reviews=True`。
