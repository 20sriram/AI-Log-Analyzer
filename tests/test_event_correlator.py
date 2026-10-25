import unittest

from ai_engine.event_correlator import correlate_events, find_root_cause


def make_log(
    event_id,
    timestamp="2026-01-01 12:00:00",
    service="worker",
    level="ERROR",
    message="synthetic event",
):
    return {
        "id": event_id,
        "timestamp": timestamp,
        "service": service,
        "level": level,
        "message": message,
    }


class CorrelateEventsTests(unittest.TestCase):
    def test_includes_events_within_window_and_excludes_later_events(self):
        earliest = make_log("first", "2026-01-01 12:00:00")
        inside = make_log("inside", "2026-01-01 12:00:10", level="WARNING")
        outside = make_log("outside", "2026-01-01 12:00:11")
        info = make_log("info", "2026-01-01 12:00:01", level="INFO")

        result = correlate_events([outside, info, inside, earliest])

        self.assertEqual([log["id"] for log in result], ["first", "inside"])

    def test_malformed_timestamp_is_excluded_when_valid_event_exists(self):
        valid = make_log("valid", "2026-01-01 12:00:00")
        malformed = make_log("malformed", "not-a-timestamp")

        result = correlate_events([malformed, valid])

        self.assertEqual([log["id"] for log in result], ["valid"])

    def test_all_missing_timestamps_return_no_related_events(self):
        missing_value = make_log("missing-value", None)
        missing_key = make_log("missing-key")
        del missing_key["timestamp"]

        self.assertEqual(
            correlate_events([missing_value, missing_key]), []
        )

    def test_all_malformed_timestamps_return_no_related_events(self):
        logs = [
            make_log("malformed-one", "not-a-timestamp"),
            make_log("malformed-two", "2026/01/01 12:00:00"),
        ]

        self.assertEqual(correlate_events(logs), [])

    def test_missing_timestamp_key_is_skipped_when_valid_timestamp_exists(self):
        valid = make_log("valid", "2026-01-01 12:00:00")
        missing = make_log("missing-key")
        del missing["timestamp"]

        result = correlate_events([missing, valid])

        self.assertEqual([log["id"] for log in result], ["valid"])

    def test_no_qualifying_levels_returns_no_related_events(self):
        logs = [
            make_log("info", level="INFO"),
            make_log("debug", level="DEBUG"),
        ]

        self.assertEqual(correlate_events(logs), [])


class FindRootCauseTests(unittest.TestCase):
    def test_each_configured_service_can_be_selected(self):
        configured_services = ("database", "auth", "payment", "order", "api")

        for service in configured_services:
            with self.subTest(service=service):
                candidate = make_log(
                    f"{service}-candidate",
                    service=service,
                    level="WARNING",
                )

                result = find_root_cause([candidate])

                self.assertEqual(result["id"], f"{service}-candidate")

    def test_each_service_priority_outranks_the_next_lower_priority(self):
        ordered_services = ("database", "auth", "payment", "order", "api")

        for preferred, lower_priority in zip(
            ordered_services, ordered_services[1:]
        ):
            with self.subTest(preferred=preferred, lower_priority=lower_priority):
                lower = make_log(
                    "lower-priority",
                    "2026-01-01 12:00:00",
                    service=lower_priority,
                )
                preferred_later = make_log(
                    "preferred-service",
                    "2026-01-01 12:00:01",
                    service=preferred,
                )

                result = find_root_cause([lower, preferred_later])

                self.assertEqual(result["id"], "preferred-service")

    def test_service_priority_can_outrank_earlier_payment_and_order_errors(self):
        payment = make_log(
            "payment-first", "2026-01-01 12:00:00", service="payment"
        )
        order = make_log(
            "order-second", "2026-01-01 12:00:01", service="order"
        )
        database = make_log(
            "database-last", "2026-01-01 12:00:02", service="database"
        )

        result = find_root_cause([payment, order, database])

        self.assertEqual(result["id"], "database-last")
        # Selection indicates a probable root cause under current rules, not proof.

    def test_service_priority_is_case_insensitive_and_message_is_not_scored(self):
        payment = make_log(
            "payment", "2026-01-01 12:00:00", service="payment",
            level="ERROR", message="critical payment failure",
        )
        database = make_log(
            "database", "2026-01-01 12:00:01", service="DATABASE",
            level="WARNING", message="routine database notice",
        )

        result = find_root_cause([payment, database])

        self.assertEqual(result["id"], "database")

    def test_equal_timestamp_candidates_keep_input_order(self):
        first = make_log(
            "first-input", service="payment", timestamp="2026-01-01 12:00:00"
        )
        second = make_log(
            "second-input", service="payment", timestamp="2026-01-01 12:00:00"
        )

        result = find_root_cause([first, second])

        self.assertEqual(result["id"], "first-input")

    def test_unconfigured_service_falls_back_to_earliest_error(self):
        later = make_log(
            "later-error", "2026-01-01 12:00:02", service="worker"
        )
        earlier = make_log(
            "earlier-error", "2026-01-01 12:00:01", service="cache"
        )

        result = find_root_cause([later, earlier])

        self.assertEqual(result["id"], "earlier-error")

    def test_warning_only_group_returns_probable_warning(self):
        later = make_log(
            "later-warning", "2026-01-01 12:00:02",
            service="worker", level="WARNING",
        )
        earlier = make_log(
            "earlier-warning", "2026-01-01 12:00:01",
            service="cache", level="WARNING",
        )

        result = find_root_cause([later, earlier])

        self.assertEqual(result["id"], "earlier-warning")
        self.assertEqual(result["level"], "WARNING")

    def test_empty_input_returns_no_probable_root_cause(self):
        self.assertIsNone(find_root_cause([]))

    def test_correlator_excludes_info_only_group_and_root_selector_returns_first_log(self):
        later_info = make_log(
            "later-info", "2026-01-01 12:00:01", level="INFO"
        )
        earlier_info = make_log(
            "earlier-info", "2026-01-01 12:00:00", level="INFO"
        )

        self.assertEqual(correlate_events([later_info, earlier_info]), [])
        # find_root_cause assumes it receives correlated inputs. If called
        # directly with INFO-only input, the current fallback returns one.
        self.assertEqual(
            find_root_cause([later_info, earlier_info])["id"], "earlier-info"
        )

    def test_invalid_timestamps_are_sorted_after_valid_candidates(self):
        invalid = make_log("invalid", "bad-time", service="worker")
        valid = make_log(
            "valid", "2026-01-01 12:00:00", service="worker"
        )

        result = find_root_cause([invalid, valid])

        self.assertEqual(result["id"], "valid")

    def test_temporal_order_selects_candidate_without_proving_causality(self):
        first = make_log(
            "earliest", "2026-01-01 12:00:00",
            service="unconfigured-a", message="unrelated scheduled task",
        )
        later_error = make_log(
            "later", "2026-01-01 12:00:01",
            service="unconfigured-b", message="unrelated downstream timeout",
        )

        probable_root_cause = find_root_cause([later_error, first])

        self.assertEqual(probable_root_cause["id"], "earliest")
        # Synthetic messages provide no causal evidence; this asserts only the
        # current probable-candidate selection rule.

    def test_correlation_then_root_selection_for_database_payment_order_errors(self):
        payment = make_log(
            "payment", "2026-01-01 12:00:00", service="payment"
        )
        order = make_log(
            "order", "2026-01-01 12:00:02", service="order"
        )
        database = make_log(
            "database", "2026-01-01 12:00:04", service="database"
        )

        related = correlate_events([order, database, payment])
        probable_root_cause = find_root_cause(related)

        self.assertEqual(
            [log["id"] for log in related], ["payment", "order", "database"]
        )
        self.assertEqual(probable_root_cause["id"], "database")
        # Event order and configured priority do not prove that database caused
        # the later payment or order symptoms.


if __name__ == "__main__":
    unittest.main()
