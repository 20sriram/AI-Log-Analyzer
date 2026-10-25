import unittest

from ai_engine.log_analytics import build_log_analytics


class BuildLogAnalyticsTests(unittest.TestCase):
    def test_counts_severities_and_groups_volume_into_time_buckets(self):
        logs = [
            {
                "id": 1,
                "timestamp": "2026-10-22 10:01:00",
                "level": "INFO",
            },
            {
                "id": 2,
                "timestamp": "2026-10-22 10:07:00",
                "level": "error",
            },
            {
                "id": 3,
                "timestamp": "2026-10-22 10:07:30",
                "level": "WARNING",
            },
            {
                "id": 4,
                "timestamp": "2026-10-22 10:08:00",
                "level": "DEBUG",
            },
        ]

        result = build_log_analytics(logs)

        self.assertEqual(result["total_logs"], 4)
        self.assertEqual(
            result["severity_counts"],
            {"INFO": 1, "WARNING": 1, "ERROR": 1, "UNKNOWN": 1},
        )
        self.assertEqual(result["invalid_timestamp_count"], 0)
        self.assertEqual(result["bucket_interval_seconds"], 300)
        self.assertEqual(result["bucket_interval_label"], "5 minutes")
        self.assertEqual(
            result["time_buckets"],
            [
                {"start": "2026-10-22 10:00:00", "count": 1},
                {"start": "2026-10-22 10:05:00", "count": 3},
            ],
        )
        self.assertEqual(result["log_ids"], [1, 2, 3, 4])

    def test_invalid_and_missing_timestamps_are_counted_and_omitted_from_buckets(self):
        logs = [
            {"id": 1, "timestamp": "2026-10-22 10:01:00", "level": "INFO"},
            {"id": 2, "timestamp": "bad timestamp", "level": "ERROR"},
            {"id": 3, "level": "WARNING"},
        ]

        result = build_log_analytics(logs)

        self.assertEqual(result["invalid_timestamp_count"], 2)
        self.assertEqual(
            result["time_buckets"],
            [{"start": "2026-10-22 10:00:00", "count": 1}],
        )
        self.assertEqual(result["severity_counts"]["WARNING"], 1)

    def test_empty_dataset_has_zero_counts_and_no_buckets(self):
        result = build_log_analytics([])

        self.assertEqual(result["total_logs"], 0)
        self.assertEqual(
            result["severity_counts"],
            {"INFO": 0, "WARNING": 0, "ERROR": 0, "UNKNOWN": 0},
        )
        self.assertEqual(result["invalid_timestamp_count"], 0)
        self.assertIsNone(result["bucket_interval_seconds"])
        self.assertEqual(result["time_buckets"], [])
        self.assertEqual(result["log_ids"], [])

    def test_single_timestamp_still_produces_a_volume_bucket(self):
        result = build_log_analytics(
            [{"id": 7, "timestamp": "2026-10-22 10:01:00", "level": "INFO"}]
        )

        self.assertEqual(
            result["time_buckets"],
            [{"start": "2026-10-22 10:00:00", "count": 1}],
        )


if __name__ == "__main__":
    unittest.main()