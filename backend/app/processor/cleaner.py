"""HTML cleaning utilities for removing boilerplate, noise, scripts, and advertising."""

from __future__ import annotations

import re
from bs4 import BeautifulSoup, Comment, Tag

# Elements that should always be removed completely
STRIP_TAGS = {
    "script",
    "style",
    "noscript",
    "template",
    "iframe",
    "canvas",
    "svg",
    "audio",
    "video",
    "form",
    "button",
    "input",
    "select",
    "textarea",
    "dialog",
}

# Structural boilerplate elements (nav, footer, aside)
BOILERPLATE_TAGS = {
    "nav",
    "footer",
    "aside",
}

# Regex for noisy class/id names (ads, cookie banners, tracking, social share)
NOISE_PATTERN = re.compile(
    r"(?i)(cookie[-_]?banner|gdpr|consent|advertisement|sponsor|promo[-_]?box|social[-_]?share|share[-_]?buttons|popup[-_]?modal)"
)


def is_hidden_element(tag: Tag) -> bool:
    """Check whether a tag is visually hidden via attributes or inline styles."""
    if tag.has_attr("hidden"):
        return True
    if tag.get("aria-hidden") == "true":
        return True

    style = tag.get("style", "")
    if isinstance(style, str) and style:
        lower_style = style.lower().replace(" ", "")
        if "display:none" in lower_style or "visibility:hidden" in lower_style or "opacity:0" in lower_style:
            return True

    return False


def clean_html_soup(soup: BeautifulSoup, remove_boilerplate: bool = True) -> BeautifulSoup:
    """Clean a BeautifulSoup document tree in-place by removing noisy elements.

    Args:
        soup: BeautifulSoup parse tree.
        remove_boilerplate: When True, removes nav, footer, aside, and known noise widgets.

    Returns:
        The cleaned BeautifulSoup object.
    """
    # 1. Remove comments
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()

    # 2. Decompose strictly unwanted tags
    for tag_name in STRIP_TAGS:
        for element in soup.find_all(tag_name):
            element.decompose()

    # 3. Remove boilerplate tags (nav, footer, aside) if requested
    if remove_boilerplate:
        for tag_name in BOILERPLATE_TAGS:
            for element in soup.find_all(tag_name):
                element.decompose()

    # 4. Remove hidden elements and noise widgets
    for element in list(soup.find_all(True)):
        if not isinstance(element, Tag):
            continue

        # Check hidden status
        if is_hidden_element(element):
            element.decompose()
            continue

        # Check noise class or id
        if remove_boilerplate:
            class_list = element.get("class", [])
            classes_str = " ".join(class_list) if isinstance(class_list, list) else str(class_list)
            elem_id = str(element.get("id", ""))
            role = str(element.get("role", "")).lower()

            if role in {"banner", "contentinfo", "dialog", "alertdialog"}:
                element.decompose()
                continue

            if (classes_str and NOISE_PATTERN.search(classes_str)) or (elem_id and NOISE_PATTERN.search(elem_id)):
                element.decompose()

    return soup
