import json
import unittest

from meshi_lens.similar_ai import (
    MAX_SIMILAR_AI_CANDIDATES,
    GroqSimilarRanker,
    apply_similar_ai_ranking,
    similar_ai_input,
    validate_similar_ai_ranking,
)


class SimilarAiTests(unittest.TestCase):
    def test_bounds_structured_candidates_and_excludes_review_bodies(self) -> None:
        payload = similar_ai_input(
            {
                "name": "つばめパン",
                "genres": ["カフェ", "パン", "ソフトクリーム"],
                "station": "名古屋駅",
            },
            [
                {
                    "name": f"候選{index}",
                    "genres": ["カフェ"],
                    "rating": 3.5,
                    "review_count": 100,
                    "review_text": "不得傳送",
                    "author": "不得傳送",
                }
                for index in range(35)
            ],
        )

        self.assertEqual(len(payload["candidates"]), MAX_SIMILAR_AI_CANDIDATES)
        self.assertEqual(payload["candidates"][0]["id"], "c0")
        self.assertEqual(payload["candidates"][-1]["id"], "c29")
        self.assertNotIn("review_text", json.dumps(payload, ensure_ascii=False))
        self.assertNotIn("author", json.dumps(payload, ensure_ascii=False))

    def test_prompt_requires_existing_ids_and_treats_broad_genres_as_weak(self) -> None:
        ranker = GroqSimilarRanker(api_key="test-key")
        body = ranker._request_body(
            similar_ai_input(
                {"name": "つばめパン", "genres": ["カフェ", "パン"]},
                [{"name": "候選", "genres": ["カフェ"]}],
            )
        )
        content = body["messages"][0]["content"]

        self.assertIn("不得新增、改寫或猜測候選 id", content)
        self.assertIn("泛用類別", content)
        self.assertEqual(body["response_format"], {"type": "json_object"})

    def test_rejects_unknown_or_duplicate_candidate_ids(self) -> None:
        with self.assertRaisesRegex(ValueError, "未知"):
            validate_similar_ai_ranking(
                {"ranking": [{"id": "c9", "score": 80, "reason": "不在名單"}]},
                candidate_count=2,
            )
        with self.assertRaisesRegex(ValueError, "未知"):
            validate_similar_ai_ranking(
                {
                    "ranking": [
                        {"id": "c0", "score": 80, "reason": "第一筆"},
                        {"id": "c0", "score": 70, "reason": "重複"},
                    ]
                },
                candidate_count=2,
            )

    def test_maps_only_validated_ids_back_to_server_candidates(self) -> None:
        recommendations = apply_similar_ai_ranking(
            [
                {"name": "咖啡廳", "url": "https://tabelog.com/example/1/"},
                {"name": "麵包店", "url": "https://tabelog.com/example/2/"},
            ],
            [{"id": "c1", "score": 91, "reason": "麵包類別相近"}],
        )

        self.assertEqual(recommendations[0]["name"], "麵包店")
        self.assertEqual(recommendations[0]["similarity_score"], 91)
        self.assertEqual(recommendations[0]["reasons"], ["麵包類別相近"])


if __name__ == "__main__":
    unittest.main()
