"""Unit tests for Guardian static URL structural analysis and pattern detection."""

import pytest

from app.guardian.url_analyzer import UrlStructureAnalyzer


def test_url_analyzer_detects_insecure_http():
    analyzer = UrlStructureAnalyzer()
    findings, meta = analyzer.analyze("http://example.com/test", "http://example.com/test")
    names = {f.name for f in findings}
    assert "Insecure HTTP Scheme" in names
    assert meta["scheme"] == "http"


def test_url_analyzer_detects_ip_address_hostname():
    analyzer = UrlStructureAnalyzer()
    findings, meta = analyzer.analyze("http://93.184.216.34/path", "http://93.184.216.34/path")
    names = {f.name for f in findings}
    assert "IP Address Literal in Hostname" in names


def test_url_analyzer_detects_punycode_and_homographs():
    analyzer = UrlStructureAnalyzer()
    findings, meta = analyzer.analyze("https://xn--e1afmkfd.xn--80akhbyknj4f/login", "https://xn--e1afmkfd.xn--80akhbyknj4f/login")
    names = {f.name for f in findings}
    assert "Punycode / Internationalized Domain (IDN)" in names


def test_url_analyzer_detects_url_shortener():
    analyzer = UrlStructureAnalyzer()
    findings, meta = analyzer.analyze("https://bit.ly/3xyzABC", "https://bit.ly/3xyzABC")
    names = {f.name for f in findings}
    assert "URL Shortening Service" in names


def test_url_analyzer_detects_brand_in_subdomain():
    analyzer = UrlStructureAnalyzer()
    findings, meta = analyzer.analyze("https://paypal.account-verify.attacker.net/login", "https://paypal.account-verify.attacker.net/login")
    names = {f.name for f in findings}
    assert "Brand Keyword in Subdomain" in names


def test_url_analyzer_detects_dangerous_file_download():
    analyzer = UrlStructureAnalyzer()
    findings, meta = analyzer.analyze("https://example.com/updates/installer.exe", "https://example.com/updates/installer.exe")
    names = {f.name for f in findings}
    assert "Potentially Dangerous File Download" in names
    assert meta.get("download_extension") == ".exe"


def test_url_analyzer_detects_open_redirect_parameters():
    analyzer = UrlStructureAnalyzer()
    findings, meta = analyzer.analyze("https://example.com/login?redirect=https://evil.org/phish", "https://example.com/login?redirect=https://evil.org/phish")
    names = {f.name for f in findings}
    assert "Open Redirect Query Parameter" in names


def test_url_analyzer_detects_double_percent_encoding_and_null_bytes():
    analyzer = UrlStructureAnalyzer()
    findings, _ = analyzer.analyze("https://example.com/view?file=%252e%252e%2fetc%00.txt", "https://example.com/view?file=%252e%252e%2fetc%00.txt")
    names = {f.name for f in findings}
    assert "Double Percent-Encoding Detected" in names
    assert "Null Byte Injection Token Detected" in names
