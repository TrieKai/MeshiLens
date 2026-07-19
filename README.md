# ![MeshiLens logo](extension/icons/icon-48.png) MeshiLens

在 Google Maps 店家頁旁顯示 **Tabelog 日本語版**評分與 **Michelin Guide 日本**入選資訊。Chrome／Edge 擴充功能讀取目前店家，再交給 Python 服務進行店家比對。

## 已完成的 MVP

- 監聽 Google Maps 單頁式切換，不用重新整理頁面
- 擴充功能彈出視窗顯示目前版本，並提供啟用／停用開關及五種主題色；停用後立即移除評分卡並停止新的店家查詢
- 讀取店名、地址、電話與真正的店家座標（網址含多組 `!3d...!4d...` 時使用最後一組目前店家座標）
- Google Maps 已列出 Tabelog 菜單／店家連結時，直接使用該 URL 並視為高信心配對
- 以 Google Maps 餐飲類別為快速判斷，未知類別若有菜單、每人價格或明確提供內用，也會視為餐飲店家；沒有任何餐飲訊號的地點不顯示也不呼叫 API
- Maps 使用英文譯名時，同時擷取隱藏的當地語言店名，去除「うなぎ、割烹」等類型詞後查找 Tabelog 店家 ID
- Tabelog 缺少電話或地址格式不同時，從店家地圖頁補讀座標並與 Maps 位置比對
- Tabelog 出現同名、同電話、同座標的重複頁面時，優先選擇已有評分與較多評論的成熟頁面
- 使用 `gurume` 搜尋 Tabelog，並補抓候選店家的基本資料
- Tabelog 搜尋頁回覆 403 時，以低頻率公開網頁搜尋找出候選店家 URL，再由 `gurume` 讀取 Tabelog 詳細頁
- 以電話、地址、座標及正規化店名計算配對信心
- 在 Maps 店家區塊顯示評分、評論數、店家時間線（百名店多年紀錄 + 目前 Michelin）、價位、車站、營業資訊及 Tabelog 連結
- 顯示 Tabelog 的預約狀態；有穩定的線上預約連結時提供直接按鈕
- 顯示信用卡、電子支付與 QR Code 支付的接受狀態及 Tabelog 列出的品牌
- 顯示日本全地區目前 Michelin Guide 的三星、二星、一星、必比登及指南入選資訊
- Michelin 資料使用繁中 SSR 清單建立低頻本地快照；使用者瀏覽 Maps 時不會向 Michelin 發出請求
- 跨語言店名且有 Maps 電話或官網時，只低頻補查 100 公尺內的 Michelin 詳情頁，結果快取一天
- Tabelog 與 Michelin 以獨立請求並行比對，先完成的一方先顯示，另一方再補入卡片
- Tabelog 比對完成後，以店名、類型、評分／評論數、價位、獎項、訂位與付款等**結構化資料**非同步產生繁中「AI 用餐建議」；不擷取、不傳送也不摘要 Tabelog 或 Google Maps 評論原文
- 中低信心時列出候選店家，讓使用者手動切換
- 六小時結果快取（記憶體 L1 + 本機檔案或選用 Redis／Upstash）與 Tabelog 依 host 節流

## 安裝與啟動

需要 Python 3.12 以上。建議安裝 [uv](https://docs.astral.sh/uv/)，然後在本專案資料夾執行：

```bash
uv sync
uv run meshilens-server
```

看到 `MeshiLens 已啟動：http://127.0.0.1:18765` 後：

1. 在 Chrome 開啟 `chrome://extensions`（Edge 為 `edge://extensions`）。
2. 開啟「開發人員模式」。
3. 選擇「載入未封裝項目」，指定本專案的 `extension` 資料夾。
4. 開啟 Google Maps 的日本餐廳頁；評分卡會自動出現在店家資訊區塊。
5. 點工具列上的 MeshiLens 圖示，可檢查本機服務狀態。

## Vercel 後端部署

專案可部署為 Vercel Python Function，提供 `GET /api/health` 和
`POST /api/match`、`POST /api/michelin` 與選用的 `POST /api/advice`。目前為測試階段，API 未啟用存取驗證。未來接上瀏覽器
擴充功能時，再將其正式網址設定到 `MESHI_ALLOWED_ORIGIN` 並啟用驗證。

## 更新 Michelin 日本快照

目前快照涵蓋繁中 Michelin Guide 日本全地區。需要更新時手動執行：

```bash
uv run python scripts/update_michelin.py
```

更新器預設只低頻讀取伺服器端渲染的餐廳清單，並檢查官方宣告筆數與解析筆數完全一致。跨語言配對所需的電話與官方網站由後端只在必要時補查附近詳情頁並快取；若要離線預抓全部詳情，可加上 `--include-details`。

## 持久化結果快取（選用）

`/match`、`/michelin`、`/advice` 會快取結果（TTL 分別約 6 小時、24 小時、24 小時）。
預設為**記憶體 L1 + 本機檔案**（目錄見 `MESHI_CACHE_DIR`，預設系統暫存）。
在 Vercel Marketplace 連結 Upstash Redis 後，會自動設定：

```bash
KV_REST_API_URL=https://xxxx.upstash.io
KV_REST_API_TOKEN=...
```

也可直接設定 Upstash REST 憑證：

```bash
UPSTASH_REDIS_REST_URL=https://xxxx.upstash.io
UPSTASH_REDIS_REST_TOKEN=...
```

或使用 `MESHI_REDIS_URL`／`REDIS_URL`（需 `uv sync --extra redis`）。詳見 `.env.example`。
擴充功能另有 45 分鐘的 session／記憶體短快取，並會取消過期的店家查詢請求。

## AI 用餐建議（選用）

設定 Vercel 或本機伺服器的 `GROQ_API_KEY` 後，擴充功能會在配對成功時向
`/advice` 發出一個獨立、低優先的請求。預設模型為 `qwen/qwen3.6-27b`，可用
`GROQ_MODEL` 覆寫。API key 只存於伺服器環境變數，絕不可放在擴充功能內。

摘要只接收 MeshiLens 已取得的店名、餐廳類型、Tabelog 分數及評論**數量**、價位、
百名店／米其林、訂位與付款欄位；不接收評論正文、評論者、照片或 Google Maps 評論。
同一份店家資料會在瀏覽器本機快取 24 小時，資料關鍵欄位（`advice_facts`）改變才重新生成。

## 配對規則

配對最高為 100 分：

| 訊號 | 分數／作用 |
|---|---:|
| 電話完全相同 | 52 |
| Michelin 電話或官方網站相同且座標接近 | 高信心配對 |
| 正規化店名相似 | 最多 25 |
| 地址相似 | 最多 35 |
| 座標 100 公尺內 | 52（總分仍封頂 100） |

75 分以上自動視為高信心；52–74.9 分會顯示提醒；更低則不自動選定。名稱正規化會移除「割烹、食堂、レストラン、本店」等類型或分店詞，但常見店名仍須靠電話、地址或座標確認。

## 測試

不需連上 Tabelog 即可執行單元測試：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --check extension/background.js
node --check extension/content.js
node --check extension/popup.js
node --test tests/test_settings.js tests/test_toggle.js tests/test_category.js tests/test_maps.js tests/test_timeline.js tests/test_lookup_cache.js
```

測試包含「割烹 清水屋」對 Tabelog「清水屋」的電話與地址差異案例。

## 隱私與限制

- 本機服務只監聽 `127.0.0.1`，`/match` 只接受瀏覽器擴充功能來源。
- 擴充功能只有 Google Maps、本機服務及本機儲存權限，不讀取其他網站。
- Tabelog 搜尋頁可能依網路環境回覆 403；此時會改用公開搜尋索引尋找 Tabelog URL。若兩條路徑都失敗，擴充功能會顯示明確錯誤，不會誤認為「沒有這家店」。
- Tabelog 頁面格式調整可能使 `gurume` 暫時失效；已提供持久結果快取，正式發布前仍應加強併發限制與監控。
- 請遵守 Tabelog 的使用條款與 robots 政策，不要大量或自動化濫用請求。
- Tabelog 商標與資料屬其權利人；本專案不隸屬於 Google 或 Tabelog。
- Michelin 功能僅保存店家識別、座標、料理類型、價位、獎項與官方連結，不保存照片或評審文章；此非官方授權功能，請維持低頻、個人及非商業用途。
- AI 用餐建議是根據有限結構化欄位的輔助判讀，不是評論摘要，也不應取代店家頁最新資訊或個人判斷。

## 專案結構

```text
extension/                 Chrome／Edge Manifest V3 擴充功能
extension/timeline.js      店家時間線條目組裝
src/meshi_lens/provider.py gurume 介接與節流
src/meshi_lens/michelin.py Michelin SSR 解析、本地快照與店家配對
src/meshi_lens/matching.py 店家正規化、距離與配對評分
src/meshi_lens/server.py   只監聽本機的 JSON HTTP 服務
scripts/update_michelin.py 低頻更新日本全地區 Michelin 快照
tests/                     不連網單元測試
AGENTS.md                  AI／協作代理人專案指引
```
