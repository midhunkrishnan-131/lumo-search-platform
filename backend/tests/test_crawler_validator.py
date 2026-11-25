"""Unit tests for URL validation, normalization, and SSRF shielding."""

import pytest

from app.crawler.validator import (
    is_prohibited_ip,
    normalize_url,
    validate_and_screen_url,
)
import ipaddress


def test_valid_http_and_https_urls():
    res_http = validate_and_screen_url("http://example.com/docs", resolve_dns=False)
    assert res_http.is_valid is True
    assert res_http.normalized_url == "http://example.com/docs"

    res_https = validate_and_screen_url("https://example.com/index.html", resolve_dns=False)
    assert res_https.is_valid is True
    assert res_https.normalized_url == "https://example.com/index.html"


def test_reject_unsupported_schemes():
    for scheme in ("ftp://files.example.com", "javascript:alert(1)", "file:///etc/passwd", "data:text/plain;base64,SGVsbG8="):
        res = validate_and_screen_url(scheme, resolve_dns=False)
        assert res.is_valid is False
        assert "Unsupported scheme" in (res.error or "") or "Missing URL scheme" in (res.error or "")


def test_reject_localhost_and_internal_hostnames():
    for bad_host in (
        "http://localhost/admin",
        "http://localhost:80/status",
        "https://app.localhost",
        "http://myhost.local/api",
        "http://service.internal/config",
        "http://server.lan/db",
    ):
        res = validate_and_screen_url(bad_host, resolve_dns=False)
        assert res.is_valid is False
        assert "prohibited" in (res.error or "").lower()


def test_reject_loopback_and_private_ips():
    for private_ip in (
        "http://127.0.0.1",
        "http://127.0.0.2:80/secret",
        "http://10.0.0.1",
        "http://172.16.0.1/status",
        "http://192.168.1.1/router",
        "http://169.254.169.254/latest/meta-data/",  # AWS metadata
        "http://0.0.0.0",
        "http://[::1]/",
    ):
        res = validate_and_screen_url(private_ip, resolve_dns=False)
        assert res.is_valid is False
        assert "blocked" in (res.error or "").lower() or "prohibited" in (res.error or "").lower()


def test_reject_non_standard_ports():
    for bad_port in (
        "http://example.com:22/ssh",
        "http://example.com:8080/app",
        "https://example.com:8443/dash",
        "http://example.com:5432/db",
    ):
        res = validate_and_screen_url(bad_port, resolve_dns=False)
        assert res.is_valid is False
        assert "Port" in (res.error or "")


def test_url_normalization():
    assert normalize_url("HTTP://EXAMPLE.COM:80/path/") == "http://example.com/path/"
    assert normalize_url("https://example.com:443/docs#section-1") == "https://example.com/docs"
    assert normalize_url("https://example.com/search?b=2&a=1") == "https://example.com/search?a=1&b=2"
    assert normalize_url("https://example.com//a//b//c") == "https://example.com/a/b/c"


def test_prohibited_ip_ranges():
    assert is_prohibited_ip(ipaddress.ip_address("127.0.0.1")) is True
    assert is_prohibited_ip(ipaddress.ip_address("10.10.10.10")) is True
    assert is_prohibited_ip(ipaddress.ip_address("192.168.0.1")) is True
    assert is_prohibited_ip(ipaddress.ip_address("172.20.1.1")) is True
    assert is_prohibited_ip(ipaddress.ip_address("169.254.1.1")) is True
    assert is_prohibited_ip(ipaddress.ip_address("::1")) is True
    assert is_prohibited_ip(ipaddress.ip_address("8.8.8.8")) is False
    assert is_prohibited_ip(ipaddress.ip_address("1.1.1.1")) is False
