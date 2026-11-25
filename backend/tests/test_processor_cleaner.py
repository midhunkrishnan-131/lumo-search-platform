"""Tests for HTML cleaner."""

from bs4 import BeautifulSoup
from app.processor.cleaner import clean_html_soup, is_hidden_element


def test_cleaner_removes_scripts_and_styles():
    html = """
    <html>
        <head>
            <style>body { color: red; }</style>
            <script>console.log("evil");</script>
        </head>
        <body>
            <h1>Real Heading</h1>
            <script>alert("xss");</script>
            <noscript>Turn on JS</noscript>
            <p>Real Content</p>
        </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    cleaned = clean_html_soup(soup)

    assert cleaned.find("script") is None
    assert cleaned.find("style") is None
    assert cleaned.find("noscript") is None
    assert "Real Heading" in cleaned.get_text()
    assert "Real Content" in cleaned.get_text()


def test_cleaner_removes_nav_footer_aside_forms():
    html = """
    <div>
        <nav><a href="/home">Home</a><a href="/about">About</a></nav>
        <aside>Related links and ads</aside>
        <article>
            <p>Main article text that should be kept.</p>
        </article>
        <form action="/login"><input type="text"><button>Submit</button></form>
        <footer>Copyright 2026 LUMO Inc.</footer>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    cleaned = clean_html_soup(soup, remove_boilerplate=True)

    assert cleaned.find("nav") is None
    assert cleaned.find("footer") is None
    assert cleaned.find("aside") is None
    assert cleaned.find("form") is None
    assert cleaned.find("button") is None
    assert "Main article text that should be kept." in cleaned.get_text()
    assert "Copyright 2026" not in cleaned.get_text()


def test_cleaner_removes_hidden_elements_and_ads():
    html = """
    <div>
        <p hidden>Invisible text</p>
        <div style="display: none;">Inline hidden text</div>
        <div style="visibility: hidden">Visibility hidden</div>
        <div class="cookie-banner-wrap">We use cookies</div>
        <div id="advertisement-slot-1">Buy now</div>
        <p>Visible authentic content.</p>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    cleaned = clean_html_soup(soup, remove_boilerplate=True)

    text = cleaned.get_text()
    assert "Invisible text" not in text
    assert "Inline hidden text" not in text
    assert "Visibility hidden" not in text
    assert "We use cookies" not in text
    assert "Buy now" not in text
    assert "Visible authentic content." in text
