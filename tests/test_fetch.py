import unittest
from unittest.mock import patch

from meshi_lens.fetch import Deadline, DeadlineExceeded, HTTPStatusError, ThrottledFetcher


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakeResponse:
    def __init__(self, status_code: int = 200, text: str = "<html></html>") -> None:
        self.status_code = status_code
        self.text = text


class FetchTests(unittest.TestCase):
    def test_request_timeout_never_outlives_the_deadline(self) -> None:
        clock = FakeClock()
        deadline = Deadline(25, clock=clock)
        fetcher = ThrottledFetcher(minimum_interval=0)
        with patch("curl_cffi.requests.get", return_value=FakeResponse()) as get:
            fetcher.fetch("https://tabelog.com/a/", deadline=deadline)
            clock.now = 12
            fetcher.fetch("https://tabelog.com/b/", deadline=deadline)

        self.assertEqual(
            [call.kwargs["timeout"] for call in get.call_args_list], [20.0, 13.0]
        )

    def test_does_not_start_a_request_the_deadline_cannot_fit(self) -> None:
        clock = FakeClock()
        deadline = Deadline(25, clock=clock)
        clock.now = 24.5
        with patch("curl_cffi.requests.get") as get:
            with self.assertRaises(DeadlineExceeded):
                ThrottledFetcher(minimum_interval=0).fetch(
                    "https://tabelog.com/a/", deadline=deadline
                )

        get.assert_not_called()

    def test_does_not_wait_for_a_host_slot_past_the_deadline(self) -> None:
        fetcher = ThrottledFetcher(minimum_interval=0.8)
        clock = FakeClock()
        with (
            patch("curl_cffi.requests.get", return_value=FakeResponse()) as get,
            patch("meshi_lens.fetch.time.sleep") as sleep,
        ):
            fetcher.fetch("https://tabelog.com/a/")
            # Tabelog's next slot is about 0.8 s away, leaving under a second to request.
            with self.assertRaises(DeadlineExceeded):
                fetcher.fetch("https://tabelog.com/b/", deadline=Deadline(1.5, clock=clock))
            # Yahoo keeps its own interval, so it is not held back.
            fetcher.fetch(
                "https://search.yahoo.co.jp/search", deadline=Deadline(1.5, clock=clock)
            )

        sleep.assert_not_called()
        self.assertEqual(get.call_count, 2)

    def test_error_status_raises_with_its_code(self) -> None:
        with patch("curl_cffi.requests.get", return_value=FakeResponse(403)):
            with self.assertRaises(HTTPStatusError) as raised:
                ThrottledFetcher(minimum_interval=0).fetch("https://tabelog.com/a/")

        self.assertEqual(raised.exception.status, 403)
        self.assertIn("403", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
