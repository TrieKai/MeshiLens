import unittest

from meshi_lens.localization import station_name


class StationNameTests(unittest.TestCase):
    def test_keeps_the_station_when_the_access_text_is_cut_at_the_first_station(self) -> None:
        # gurume stops `各線「渋谷駅」ハチ公口より徒歩5分` at the first 駅.
        self.assertEqual(station_name("各線「渋谷駅"), "渋谷駅")
        self.assertEqual(station_name("JR各線「池袋駅"), "池袋駅")

    def test_reads_quoted_and_line_qualified_labels(self) -> None:
        self.assertEqual(station_name("東京メトロ銀座線「青山一丁目駅」"), "青山一丁目駅")
        self.assertEqual(station_name("JR山手線大塚駅"), "大塚駅")

    def test_leaves_plain_station_names_alone(self) -> None:
        self.assertEqual(station_name("JR渋谷駅"), "JR渋谷駅")
        self.assertEqual(station_name(" 青山一丁目駅 "), "青山一丁目駅")
        self.assertEqual(station_name(None), "")


if __name__ == "__main__":
    unittest.main()
