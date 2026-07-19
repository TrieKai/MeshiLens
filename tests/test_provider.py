import unittest
from urllib.parse import quote

from meshi_lens.provider import (
    canonical_restaurant_url,
    coordinates_from_tabelog_html,
    extract_tabelog_urls,
    hyakumeiten_from_tabelog_html,
    merge_candidate_details,
    parse_tabelog_page,
    payment_from_tabelog_html,
    reservation_from_tabelog_html,
    restaurant_to_dict,
    stable_reservation_url,
    web_search_queries,
)


class ProviderTests(unittest.TestCase):
    def test_searches_by_local_phone_before_translated_name(self) -> None:
        self.assertEqual(
            web_search_queries(
                {
                    "name": "Sandwich Shop MURATA",
                    "alternate_name": "",
                    "phone": "+81 29-897-1508",
                }
            ),
            [
                'site:tabelog.com "029-897-1508"',
                'site:tabelog.com "Sandwich Shop MURATA"',
            ],
        )

    def test_canonicalizes_review_and_language_urls(self) -> None:
        self.assertEqual(
            canonical_restaurant_url(
                "https://tabelog.com/tw/ibaraki/A0804/A080401/8000477/dtlrvwlst/"
            ),
            "https://tabelog.com/ibaraki/A0804/A080401/8000477/",
        )

    def test_extracts_duckduckgo_redirect_once(self) -> None:
        target = "https://tabelog.com/ibaraki/A0804/A080401/8000477/"
        redirect = f"//duckduckgo.com/l/?uddg={quote(target, safe='')}"
        html = (
            f'<a class="result__a" href="{redirect}">清水屋</a>'
            f'<a class="result__a" href="{target}dtlrvwlst/">review</a>'
        )
        self.assertEqual(extract_tabelog_urls(html), [target])

    def test_extracts_tabelog_map_coordinates(self) -> None:
        html = '<div id="js-basics" data-lat="36.175271769" data-lng="139.837251778"></div>'
        self.assertEqual(
            coordinates_from_tabelog_html(html),
            (36.175271769, 139.837251778),
        )

    def test_extracts_hyakumeiten_history(self) -> None:
        html = """
        <div class="rdheader-badge-award">
          <a title="百名店ページへ"
             href="https://award.tabelog.com/hyakumeiten/japanese_west/2025/">
            <span><i>日本料理WEST百名店2025選出店</i></span>
          </a>
          <div class="rdheader-badge-award__tooltip">
            <p>食べログ 日本料理 WEST 百名店 2025 選出店</p>
          </div>
        </div>
        <div class="rstinfo-table-badge-hyakumeiten">
          <a href="https://award.tabelog.com/hyakumeiten/japanese_west/2025/">
            <i>日本料理 百名店 2025 選出店</i>
          </a>
        </div>
        <div class="rstinfo-table-badge-hyakumeiten">
          <a href="https://award.tabelog.com/hyakumeiten/japanese_west/2023/">
            <i>日本料理 百名店 2023 選出店</i>
          </a>
          <div class="rstinfo-table-badge-hyakumeiten__tooltip"><p>食べログ 日本料理 WEST 百名店 2023 選出店</p></div>
        </div>
        <div class="rstinfo-table-badge-hyakumeiten">
          <a href="https://award.tabelog.com/hyakumeiten/japanese_west/2021/">
            <i>日本料理 百名店 2021 選出店</i>
          </a>
          <div class="rstinfo-table-badge-hyakumeiten__tooltip"><p>食べログ 日本料理 WEST 百名店 2021 選出店</p></div>
        </div>
        """
        self.assertEqual(
            hyakumeiten_from_tabelog_html(html),
            [
                {
                    "label": "食べログ 日本料理 WEST 百名店 2025 選出店",
                    "category": "日本料理",
                    "area": "WEST",
                    "year": 2025,
                    "url": "https://award.tabelog.com/hyakumeiten/japanese_west/2025/",
                },
                {
                    "label": "食べログ 日本料理 WEST 百名店 2023 選出店",
                    "category": "日本料理",
                    "area": "WEST",
                    "year": 2023,
                    "url": "https://award.tabelog.com/hyakumeiten/japanese_west/2023/",
                },
                {
                    "label": "食べログ 日本料理 WEST 百名店 2021 選出店",
                    "category": "日本料理",
                    "area": "WEST",
                    "year": 2021,
                    "url": "https://award.tabelog.com/hyakumeiten/japanese_west/2021/",
                },
            ],
        )

    def test_keeps_additional_restaurant_details(self) -> None:
        candidate = restaurant_to_dict(
            {
                "name": "片折",
                "genres": ["日本料理"],
                "station": "金沢駅",
                "lunch_price": "￥40,000～￥49,999",
                "dinner_price": "￥40,000～￥49,999",
                "business_hours": "月・火 11:30 - 14:00",
                "closed_days": "日曜日",
                "reservation_url": "https://tabelog.com/booking/example",
                "has_reservation": True,
            }
        )
        self.assertEqual(candidate["station"], "金沢駅")
        self.assertEqual(candidate["lunch_price"], "￥40,000～￥49,999")
        self.assertEqual(candidate["dinner_price"], "￥40,000～￥49,999")
        self.assertEqual(candidate["business_hours"], "月・火 11:30 - 14:00")
        self.assertEqual(candidate["closed_days"], "日曜日")
        self.assertEqual(
            candidate["reservation_url"], "https://tabelog.com/booking/example"
        )
        self.assertTrue(candidate["has_reservation"])

    def test_extracts_reservation_and_payment_information(self) -> None:
        html = """
        <div id="js-basics" data-lat="36.175271769" data-lng="139.837251778"></div>
        <table>
          <tr><th>予約可否</th><td>予約可<br>週末は早めの予約を推奨</td></tr>
          <tr>
            <th>支払い方法</th>
            <td>
              カード可（VISA、Master、JCB、AMEX）
              電子マネー可（Suica、iD、QUICPay）
              QRコード決済可（PayPay、楽天ペイ）
            </td>
          </tr>
        </table>
        """
        self.assertEqual(
            reservation_from_tabelog_html(html),
            {
                "status": "available",
                "url": "",
                "details": "予約可 週末は早めの予約を推奨",
            },
        )
        payment = payment_from_tabelog_html(html)
        self.assertTrue(payment["cards"]["accepted"])
        self.assertEqual(payment["cards"]["details"], "VISA、Master、JCB、AMEX")
        self.assertEqual(payment["electronic_money"]["details"], "Suica、iD、QUICPay")
        self.assertEqual(payment["qr_code"]["details"], "PayPay、楽天ペイ")
        page = parse_tabelog_page(html)
        self.assertEqual(page["latitude"], 36.175271769)
        self.assertEqual(page["longitude"], 139.837251778)
        self.assertEqual(page["reservation"]["status"], "available")
        self.assertTrue(page["payment"]["cards"]["accepted"])

    def test_online_reservation_wins_and_payment_rejections_are_kept(self) -> None:
        html = """
        <table>
          <tr><th>予約可否</th><td>予約不可</td></tr>
          <tr><th>支払い方法</th><td>カード不可 電子マネー不可 QRコード決済不可</td></tr>
        </table>
        """
        self.assertEqual(
            reservation_from_tabelog_html(html, "https://example.com/reserve")["status"],
            "online",
        )
        payment = payment_from_tabelog_html(html)
        self.assertFalse(payment["cards"]["accepted"])
        self.assertFalse(payment["electronic_money"]["accepted"])
        self.assertFalse(payment["qr_code"]["accepted"])

    def test_rejects_generic_tabelog_reservation_help_links(self) -> None:
        self.assertEqual(
            stable_reservation_url(
                "https://tabelog.com/ai_request_booking/guide/index"
            ),
            "",
        )
        actionable = "https://yoyaku.tabelog.com/yoyaku/net_booking_form/index?rcd=123"
        self.assertEqual(stable_reservation_url(actionable), actionable)

    def test_merges_coordinates_from_enriched_detail(self) -> None:
        summary = {
            "name": "カフェ ポエティカ",
            "url": "https://tabelog.com/ibaraki/A0802/A080201/8028118",
            "rating": 3.32,
            "latitude": None,
            "longitude": None,
        }
        detail = {
            "name": "カフェ ポエティカ",
            "url": "https://tabelog.com/ibaraki/A0802/A080201/8028118/",
            "rating": None,
            "latitude": 36.126572,
            "longitude": 140.118419,
            "genres": ["カフェ"],
            "is_hyakumeiten": False,
        }
        merged = merge_candidate_details(summary, detail)
        self.assertEqual(merged["rating"], 3.32)
        self.assertEqual(merged["latitude"], 36.126572)
        self.assertEqual(merged["longitude"], 140.118419)
        self.assertEqual(merged["genres"], ["カフェ"])

    def test_ignores_non_hyakumeiten_award(self) -> None:
        html = """
        <div class="rdheader-badge-award">
          <a href="https://award.tabelog.com/2026/restaurants/gold">
            The Tabelog Award 2026 Gold
          </a>
        </div>
        """
        self.assertEqual(hyakumeiten_from_tabelog_html(html), [])


if __name__ == "__main__":
    unittest.main()
