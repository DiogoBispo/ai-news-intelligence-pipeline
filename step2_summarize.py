from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests
import feedparser
from bs4 import BeautifulSoup


logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
log = logging.getLogger("step2_summarize")

HEADERS = {
    "User-Agent": "AI-News-Summarizer/1.0 (+contact: you@example.com)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7",
}
TIMEOUT_S = 12
SLEEP_S = 0.6
MAX_SUMMARY_CHARS = 320


def clip(text: str, max_chars: int = MAX_SUMMARY_CHARS) -> str:
    t = " ".join((text or "").split()).strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1].rstrip() + "…"


def fetch_html(url: str) -> Optional[str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT_S)
        r.raise_for_status()
        return r.text
    except Exception as e:
        log.warning("fetch_failed url=%s err=%s", url, e)
        return None


def extract_meta_description(soup: BeautifulSoup) -> Optional[str]:
    tag = soup.find("meta", attrs={"name": "description"})
    if tag and tag.get("content"):
        return str(tag["content"]).strip()
    return None


def extract_og_description(soup: BeautifulSoup) -> Optional[str]:
    tag = soup.find("meta", attrs={"property": "og:description"})
    if tag and tag.get("content"):
        return str(tag["content"]).strip()
    return None


def extract_first_paragraph(soup: BeautifulSoup) -> Optional[str]:
    for p in soup.find_all("p"):
        txt = p.get_text(" ", strip=True)
        if txt and len(txt) >= 80:
            return txt
    return None


def extract_arxiv_abstract(soup: BeautifulSoup) -> Optional[str]:
    block = soup.find("blockquote", class_="abstract")
    if not block:
        return None
    txt = block.get_text(" ", strip=True).replace("Abstract:", "").strip()
    return txt or None


def source_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def build_openai_rss_summary_map() -> Dict[str, str]:
    """
    OpenAI bloqueia fetch direto em /index/... com 403 em alguns ambientes.
    Solução limpa: usar o summary/description do RSS oficial.
    """
    feed_url = "https://openai.com/news/rss.xml"
    feed = feedparser.parse(feed_url)

    mapping: Dict[str, str] = {}
    for entry in getattr(feed, "entries", []) or []:
        link = (entry.get("link") or "").strip()
        if not link:
            continue

        # Em RSS, o resumo pode aparecer como summary/description/subtitle.
        summary = (
            (entry.get("summary") or "").strip()
            or (entry.get("description") or "").strip()
            or (entry.get("subtitle") or "").strip()
        )

        if summary:
            mapping[link] = clip(summary)

    return mapping


def summarize_item(
    item: Dict[str, Any],
    openai_summary_by_url: Dict[str, str],
) -> Optional[str]:
    url = item.get("url") or ""
    if not isinstance(url, str) or not url:
        return None

    src = (item.get("source") or "").lower()
    dom = source_domain(url)

    # 1) Fallback limpo para OpenAI: usa RSS summary
    if src == "openai" or "openai.com" in dom:
        rss_summary = openai_summary_by_url.get(url)
        if rss_summary:
            return rss_summary
        # se não encontrou no mapa, cai para tentativa de HTML (best-effort)

    html = fetch_html(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    # 2) Caso especial arXiv: pegar abstract
    if "arxiv" in src or "arxiv.org" in dom:
        abs_txt = extract_arxiv_abstract(soup)
        return clip(abs_txt) if abs_txt else None

    # 3) Estratégia geral: meta/og/primeiro parágrafo
    text = (
        extract_meta_description(soup)
        or extract_og_description(soup)
        or extract_first_paragraph(soup)
    )
    return clip(text) if text else None


def main() -> int:
    in_path = "ai_news.json"
    out_path = "ai_news_step2_with_summary.json"

    # Constrói o mapa OpenAI uma vez
    openai_summary_by_url = build_openai_rss_summary_map()
    log.info("openai_rss_loaded items=%s", len(openai_summary_by_url))

    with open(in_path, "r", encoding="utf-8") as f:
        items: List[Dict[str, Any]] = json.load(f)

    enriched: List[Dict[str, Any]] = []
    for idx, it in enumerate(items, start=1):
        title = (it.get("title") or "").strip()
        log.info("summarizing %s/%s title=%s", idx, len(items), title[:90])

        summary = summarize_item(it, openai_summary_by_url)

        out = dict(it)
        out["summary"] = summary
        enriched.append(out)

        time.sleep(SLEEP_S)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)

    log.info("done out=%s total=%s", out_path, len(enriched))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
