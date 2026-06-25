from __future__ import annotations

from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from legalize_site.security import RateLimitRule, is_rate_limited


class RateLimitCacheFailureTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.rule = RateLimitRule(limit=2, window_seconds=60, by_user=False, by_ip=True)

    @patch("legalize_site.security.cache.add", side_effect=ConnectionError("redis down"))
    @override_settings(RATE_LIMIT_CACHE_FAILURE_MODE="closed")
    def test_cache_failure_can_fail_closed(self, _cache_add):
        request = self.factory.post("/login", REMOTE_ADDR="127.0.0.1")

        self.assertTrue(is_rate_limited(request, "account_login", self.rule))

    @patch("legalize_site.security.cache.add", side_effect=ConnectionError("redis down"))
    @override_settings(RATE_LIMIT_CACHE_FAILURE_MODE="open")
    def test_cache_failure_can_fail_open(self, _cache_add):
        request = self.factory.post("/login", REMOTE_ADDR="127.0.0.1")

        self.assertFalse(is_rate_limited(request, "account_login", self.rule))

    @patch("legalize_site.security.cache.add", side_effect=ConnectionError("redis down"))
    @override_settings(RATE_LIMIT_CACHE_FAILURE_MODE="open")
    def test_fail_closed_rule_blocks_even_when_global_mode_is_open(self, _cache_add):
        # Auth-sensitive endpoints opt into fail-closed so a cache outage cannot
        # silently disable brute-force protection, even if the global default is
        # fail-open.
        auth_rule = RateLimitRule(
            limit=2, window_seconds=60, by_user=False, by_ip=True, fail_closed=True
        )
        request = self.factory.post("/login", REMOTE_ADDR="127.0.0.1")

        self.assertTrue(is_rate_limited(request, "account_login", auth_rule))
