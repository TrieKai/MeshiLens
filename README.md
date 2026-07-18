# MeshiLens

在 Google Maps 店家頁旁顯示 **Tabelog 日本語版**評分、評論數與原始連結。第一版由 Chrome／Edge 擴充功能讀取目前店家，再交給只監聽本機的 Python 服務搜尋與比對 Tabelog。

## 已完成的 MVP

- 監聽 Google Maps 單頁式切換，不用重新整理頁面
- 讀取店名、地址、電話與真正的店家座標（優先使用網址中的 `!3d...!4d...`）
- Google Maps 已列出 Tabelog 菜單／店家連結時，直接使用該 URL 並視為高信心配對
- 以 Google Maps 餐飲類別為快速判斷，未知類別若有菜單、每人價格或明確提供內用，也會視為餐飲店家；沒有任何餐飲訊號的地點不顯示也不呼叫 API
- Maps 使用英文譯名時，同時擷取隱藏的當地語言店名，去除「うなぎ、割烹」等類型詞後查找 Tabelog 店家 ID
- Tabelog 缺少電話或地址格式不同時，從店家地圖頁補讀座標並與 Maps 位置比對
- Tabelog 出現同名、同電話、同座標的重複頁面時，優先選擇已有評分與較多評論的成熟頁面
- 使用 `gurume` 搜尋 Tabelog，並補抓候選店家的基本資料
- Tabelog 搜尋頁回覆 403 時，以低頻率公開網頁搜尋找出候選店家 URL，再由 `gurume` 讀取 Tabelog 詳細頁
- 以電話、地址、座標及正規化店名計算配對信心
- 在 Maps 店家區塊顯示評分、評論數、多年度百名店紀錄、價位、車站、營業資訊及 Tabelog 連結
- 中低信心時列出候選店家，讓使用者手動切換
- 六小時記憶體快取與 Tabelog 請求節流

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
`POST /api/match`。目前為測試階段，API 未啟用存取驗證。未來接上瀏覽器
擴充功能時，再將其正式網址設定到 `MESHI_ALLOWED_ORIGIN` 並啟用驗證。

## 配對規則

配對最高為 100 分：

| 訊號 | 分數／作用 |
|---|---:|
| 電話完全相同 | 52 |
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
```

測試包含「割烹 清水屋」對 Tabelog「清水屋」的電話與地址差異案例。

## 隱私與限制

- 本機服務只監聽 `127.0.0.1`，`/match` 只接受瀏覽器擴充功能來源。
- 擴充功能只有 Google Maps、本機服務及本機儲存權限，不讀取其他網站。
- Tabelog 搜尋頁可能依網路環境回覆 403；此時會改用公開搜尋索引尋找 Tabelog URL。若兩條路徑都失敗，擴充功能會顯示明確錯誤，不會誤認為「沒有這家店」。
- Tabelog 頁面格式調整可能使 `gurume` 暫時失效；正式發布前應增加持久快取、併發限制與監控。
- 請遵守 Tabelog 的使用條款與 robots 政策，不要大量或自動化濫用請求。
- Tabelog 商標與資料屬其權利人；本專案不隸屬於 Google 或 Tabelog。

## 專案結構

```text
extension/                 Chrome／Edge Manifest V3 擴充功能
src/meshi_lens/provider.py gurume 介接與節流
src/meshi_lens/matching.py 店家正規化、距離與配對評分
src/meshi_lens/server.py   只監聽本機的 JSON HTTP 服務
tests/                     不連網單元測試
```
