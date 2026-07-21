from __future__ import annotations

from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from legalize_site.security import RateLimitRule, _client_ip, is_rate_limited


class ClientIpTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(TRUSTED_PROXY_IPS=[])
    def test_untrusted_forwarded_for_is_ignored(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="198.51.100.8",
            HTTP_X_FORWARDED_FOR="203.0.113.99",
        )

        self.assertEqual(_client_ip(request), "198.51.100.8")

    @override_settings(TRUSTED_PROXY_IPS=["10.0.0.5"])
    def test_forwarded_for_is_used_only_from_trusted_proxy(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="10.0.0.5",
            HTTP_X_FORWARDED_FOR="203.0.113.99, 10.0.0.4",
        )

        self.assertEqual(_client_ip(request), "203.0.113.99")

    @override_settings(TRUST_RAILWAY_CLIENT_IP=True, TRUSTED_PROXY_IPS=[])
    def test_railway_uses_platform_x_real_ip(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="10.0.0.5",
            HTTP_X_REAL_IP="203.0.113.45",
        )

        self.assertEqual(_client_ip(request), "203.0.113.45")

    @override_settings(TRUST_RAILWAY_CLIENT_IP=True, TRUSTED_PROXY_IPS=[])
    def test_invalid_platform_ip_falls_back_to_direct_peer(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="10.0.0.5",
            HTTP_X_REAL_IP="not-an-ip|forged",
        )

        self.assertEqual(_client_ip(request), "10.0.0.5")


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
        auth_rule = RateLimitRule(limit=2, window_seconds=60, by_user=False, by_ip=True, fail_closed=True)
        request = self.factory.post("/login", REMOTE_ADDR="127.0.0.1")

        self.assertTrue(is_rate_limited(request, "account_login", auth_rule))
