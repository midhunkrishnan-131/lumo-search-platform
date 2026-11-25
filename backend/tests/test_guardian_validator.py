"""Unit tests for Guardian URL Validator and SSRF screening."""

from unittest.mock import patch
import socket

import pytest

from app.guardian.validator import validate_guardian_url


def test_validator_accepts_valid_public_https_url():
    res = validate_guardian_url("https://www.example.org/downloads/document.pdf", resolve_dns=False)
    assert res.is_valid is True
    assert res.is_blocked is False
    assert res.scheme == "https"
    assert res.hostname == "www.example.org"
    assert res.port == 443
    assert res.normalized_url == "https://www.example.org/downloads/document.pdf"


def test_validator_rejects_unsupported_schemes():
    bad_schemes = [
        "ftp://ftp.example.com/file.txt",
        "file:///etc/passwd",
        "gopher://gopher.example.com",
        "javascript:alert(1)",
        "data:text/html,<html></html>",
    ]
    for url in bad_schemes:
        res = validate_guardian_url(url, resolve_dns=False)
        assert res.is_valid is False
        assert res.is_blocked is True
        assert "Unsupported scheme" in (res.error or "")


def test_validator_rejects_embedded_credentials():
    res = validate_guardian_url("https://admin:secret123@example.com/dashboard", resolve_dns=False)
    assert res.is_valid is False
    assert res.is_blocked is True
    assert "embedded user credentials" in (res.error or "")


def test_validator_blocks_loopback_and_internal_hostnames():
    blocked_hosts = [
        "http://localhost/admin",
        "http://loopback:8080/",
        "http://router.internal/config",
        "http://printer.local/",
    ]
    for url in blocked_hosts:
        res = validate_guardian_url(url, resolve_dns=False)
        assert res.is_valid is False
        assert res.is_blocked is True
        assert "Prohibited internal hostname" in (res.error or "")


def test_validator_blocks_private_and_loopback_ip_literals():
    prohibited_ips = [
        "http://127.0.0.1/",
        "http://127.0.0.2:8000/api",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "http://169.254.169.254/latest/meta-data/",  # Cloud metadata
        "http://0.0.0.0/",
    ]
    for url in prohibited_ips:
        res = validate_guardian_url(url, resolve_dns=False)
        assert res.is_valid is False
        assert res.is_blocked is True
        assert "private, loopback, or reserved range" in (res.error or "")


def test_validator_dns_resolution_blocks_ssrf_rebinding():
    # Simulate a domain that resolves to a private IP (e.g. 192.168.1.50)
    mock_addr_info = [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("192.168.1.50", 80))
    ]
    with patch("socket.getaddrinfo", return_value=mock_addr_info):
        res = validate_guardian_url("http://spoofed.attack.org/payload", resolve_dns=True)
        assert res.is_valid is False
        assert res.is_blocked is True
        assert "SSRF blocked" in (res.error or "")
        assert "192.168.1.50" in res.resolved_ips
