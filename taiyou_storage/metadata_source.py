"""Conservative public book-page extraction for PRIVATE catalogue metadata review.

Only fetch the specified HTTPS book information URL, never chapters or other
linked resources. No redirects, authentication, cookies, challenge bypass,
fallback mirrors, or retries. Missing/uncertain fields are not invented.
"""
from __future__ import annotations

import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from bs4 import BeautifulSoup, Tag

from .core import normalized_title
from .metadata_repair import MetadataRepairError, _source_key, SOURCE_STATUS_ALIASES

MAX_HTML = 3 * 1024 * 1024
SITES = ("freewebnovel.com", "novelfull.com", "scribblehub.com")
BOOK_PATHS = {
    "freewebnovel.com": re.compile(r"^/novel/[a-z0-9]+(?:-[a-z0-9]+)*$", re.I),
    "novelfull.com": re.compile(r"^/[a-z0-9][a-z0-9-]*\.html$", re.I),
    "scribblehub.com": re.compile(r"^/series/[0-9]+/[a-z0-9][a-z0-9-]*/$", re.I),
}
STATUS = SOURCE_STATUS_ALIASES
INVALID_TITLE = {"just a moment", "access denied", "attention required", "verify you are human"}


class SourceUnavailable(ValueError):
    """One public source page could not be safely verified."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SourceUnavailable("Unexpected redirect; no redirect followed")


def checked_book_url(url: str) -> str:
    try:
        _source_key(url)
        p = urlsplit(url)
        port = p.port
    except (MetadataRepairError, ValueError) as exc:
        raise SourceUnavailable("Source URL is not a valid HTTPS book page") from exc
    host = (p.hostname or "").lower().removeprefix("www.")
    if host not in SITES or (port is not None and port != 443) or not BOOK_PATHS[host].fullmatch(p.path):
        raise SourceUnavailable("Unsupported or non-book source URL; skipped")
    return url


def public_book_html(url: str) -> str:
    """One bounded GET against an allow-listed book page only."""
    checked_book_url(url)
    req = Request(url, headers={
        "User-Agent": "TaiyouMetadataAudit/1.0 (single-public-book-page; no-chapters)",
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with build_opener(_NoRedirect()).open(req, timeout=18) as response:
            if response.status != 200 or response.headers.get("cf-mitigated", "").lower() == "challenge":
                raise SourceUnavailable("Source access challenge or unexpected response")
            if response.headers.get_content_type() not in ("text/html", "application/xhtml+xml"):
                raise SourceUnavailable("Source did not return HTML")
            body = response.read(MAX_HTML + 1)
            if len(body) > MAX_HTML:
                raise SourceUnavailable("Book page exceeds size limit")
    except HTTPError as exc:
        raise SourceUnavailable("Source returned HTTP " + str(exc.code)) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise SourceUnavailable("Source not reachable") from exc
    page = body.decode("utf-8-sig", errors="replace")
    head = BeautifulSoup(page[:250_000], "html.parser").title
    if head and any(marker in head.get_text(" ", strip=True).casefold() for marker in INVALID_TITLE):
        raise SourceUnavailable("Source returned an access challenge")
    return page


def _txt(node: Tag | None) -> str:
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""


def _same_name(first: str, second: str) -> bool:
    return bool(first and second and normalized_title(first) == normalized_title(second))


def _is_genre_anchor(anchor: Tag) -> bool:
    value = urlsplit(anchor.get("href") or "").path
    return bool(re.fullmatch(r"/genres?/[\w-]+/?", value, re.I))


def _clean_tags(anchors: list[Tag]) -> list[str]:
    tags, seen = [], set()
    for node in anchors:
        if not _is_genre_anchor(node):
            continue
        tag = _txt(node)
        key = tag.casefold()
        if tag and len(tag) <= 100 and key not in seen:
            tags.append(tag)
            seen.add(key)
    return tags[:50]


def _find_synopsis(heading: Tag) -> str:
    """Read only dedicated summary content before navigation/chapters."""
    parts = []
    for node in heading.next_siblings:
        if not isinstance(node, Tag):
            continue
        if node.name in ("h1", "h2", "h3", "h4", "h5", "nav", "aside", "footer"):
            break
        if node.select_one("a[href*='/chapter-'], a[href*='/chapter/']"):
            break
        copy = BeautifulSoup(str(node), "html.parser")
        for el in copy.select("script,style,nav,button,footer,aside"):
            el.decompose()
        value = _txt(copy)
        if value:
            parts.append(value)
        if sum(map(len, parts)) > 24000:
            break
    text = " ".join(parts)
    text = re.split(r"\b(?:See all|See more|Hide|Chapter list|Read first|Add to Library)\b",
                    text, maxsplit=1, flags=re.I)[0].strip()
    return text[:24000] if 45 <= len(text) <= 24000 else ""


def _book_summary(soup: BeautifulSoup, *, selector: str = "") -> str:
    for heading in soup.select("h2,h3,h4,h5"):
        if _txt(heading).casefold().strip(": ") in ("summary", "synopsis", "description"):
            description = _find_synopsis(heading)
            if description:
                return description
    for node in soup.select(selector or "[itemprop='description'], .novel-summary, #novel-summary"):
        if not node.select_one("a[href*='chapter']"):
            value = _txt(node)
            if 45 <= len(value) <= 24000:
                return value
    return ""


def _freewebnovel(soup: BeautifulSoup, title: str, author: str) -> dict:
    heading = next((h for h in soup.select("h1") if _same_name(_txt(h), title)), None)
    if heading is None:
        raise SourceUnavailable("Novel heading does not match catalogue title")
    all_nodes = soup.find_all(True)
    locations = {id(node): i for i, node in enumerate(all_nodes)}
    end = locations[id(heading)]
    author_links = [
        x for x in soup.select("a[href*='/author/']")
        if locations[id(x)] < end and _same_name(_txt(x), author)
    ]
    if not author_links:
        raise SourceUnavailable("Novel author could not be confirmed from its source page")
    start = locations[id(author_links[-1])]
    if end - start > 170:
        raise SourceUnavailable("Novel metadata header is ambiguous")
    header = all_nodes[start:end]
    genre = _clean_tags([node for node in header if node.name == "a"])
    status = ""
    for node in header:
        if node.name == "a":
            href = urlsplit(node.get("href") or "").path.casefold()
            value = _txt(node).casefold()
            if href.startswith(("/sort/completed", "/completed-novel")) or value == "completed":
                status = "Completed"
            elif value in STATUS:
                # The verified book's status link may point to a site-wide
                # listing (for example /latest-release for "OnGoing").
                status = STATUS[value]
    synopsis = _book_summary(soup)
    result = {}
    if synopsis:
        result["description"] = synopsis
    if genre:
        result["sourceTags"] = genre
    if status:
        result["status"] = status
    return result


def _novelfull(soup: BeautifulSoup, title: str, author: str) -> dict:
    # The book's metadata panel precedes chapter lists and recommendations.
    titles = [h for h in soup.select("h1,h2,h3") if _same_name(_txt(h), title)]
    if not titles:
        raise SourceUnavailable("Novel heading does not match catalogue title")
    containers = soup.select(".book, .novel-info, .novel-detail, .info, .book-info")
    info = next((div for div in containers if any(_same_name(_txt(h), title)
                for h in div.select("h1,h2,h3")) and len(div.select("a[href*='/chapter']")) < 4), None)
    if info is None:
        # Some templates use an info-meta list directly after the H3 title.
        info = next((div for div in soup.select(".info-meta, .book-meta")
                     if author.casefold() in _txt(div).casefold()), None)
    if info is None:  # fail closed on unknown layout
        raise SourceUnavailable("Unrecognised NovelFull book information panel")
    text = _txt(info)
    if normalized_title(author) not in normalized_title(text):
        raise SourceUnavailable("Novel author does not match the book information panel")
    genres = []
    status = ""
    for node in info.select("li,p,div"):
        # Avoid outer containers and site navigation; only short labelled rows.
        if len(node.select("li,p,div")) > 0:
            continue
        label = _txt(node)
        if len(label) > 650:
            continue
        if re.match(r"^genres?\s*:", label, re.I):
            genres.extend(_clean_tags(node.select("a[href]")))
        elif re.match(r"^status\s*:", label, re.I):
            status = STATUS.get(label.split(":", 1)[-1].strip().casefold(), status)
    if not genres:
        genre_container = next((x for x in info.select(".genres,.genre")
                                if len(x.select("a")) <= 35), None)
        if genre_container:
            genres = _clean_tags(genre_container.select("a[href]"))
    synopsis = ""
    for node in soup.select(".desc-text, #tab-description, [itemprop='description'], .desc"):
        if len(node.select("a[href*='chapter']")) < 1:
            value = _txt(node)
            if 45 <= len(value) <= 24000:
                synopsis = value
                break
    result = {}
    if synopsis:
        result["description"] = synopsis
    if genres:
        result["sourceTags"] = genres
    if status:
        result["status"] = status
    return result


def _scribblehub(soup: BeautifulSoup, title: str, author: str) -> dict:
    # Scribble Hub's book page is frequently gated or moved. Never guess a
    # status from chapter count or a genre from a sidebar/related series.
    heading = next((x for x in soup.select("h1,h2") if _same_name(_txt(x), title)), None)
    if heading is None:
        raise SourceUnavailable("Scribble Hub title not verified")
    series = soup.select_one(".fic-title, .fic-header, .fic-info, #fic")
    if series is None or normalized_title(author) not in normalized_title(_txt(series)):
        raise SourceUnavailable("Scribble Hub book/author could not be confirmed")
    genres = _clean_tags(series.select("a[href]"))
    synopsis_node = soup.select_one(".fic-description, .fic_desc, [itemprop='description']")
    synopsis = _txt(synopsis_node)
    status = ""
    for text in series.stripped_strings:
        if str(text).strip().casefold() in STATUS:
            status = STATUS[str(text).strip().casefold()]
    return {
        **({"description": synopsis[:24000]} if 45 <= len(synopsis) <= 24000 else {}),
        **({"sourceTags": genres} if genres else {}),
        **({"status": status} if status else {}),
    }


def verified_metadata(page: str, url: str, title: str, author: str) -> dict:
    """Return only source-proven fields; unverified page/identity raises."""
    checked_book_url(url)
    if not title or not author:
        raise SourceUnavailable("Catalogue identity has missing title or author")
    soup = BeautifulSoup(page, "html.parser")
    for node in soup.select("script,style,iframe,noscript"):
        node.decompose()
    head = soup.title
    if head and any(marker in _txt(head).casefold() for marker in INVALID_TITLE):
        raise SourceUnavailable("Access challenge returned instead of a novel page")
    host = (urlsplit(url).hostname or "").removeprefix("www.").lower()
    parser = {
        "freewebnovel.com": _freewebnovel,
        "novelfull.com": _novelfull,
        "scribblehub.com": _scribblehub,
    }[host]
    return parser(soup, title, author)
