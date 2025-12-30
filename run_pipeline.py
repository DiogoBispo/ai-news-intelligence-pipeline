from __future__ import annotations

import argparse
import json
import logging
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse

import feedparser
import requests
from bs4 import BeautifulSoup


# ============================================================
# Logging
# ============================================================

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
log = logging.getLogger("ai_pipeline")


# ============================================================
# Config
# ============================================================

HEADERS = {
    "User-Agent": "AI-News-Pipeline/1.0 (+contact: you@example.com)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7",
}

DEFAULT_TIMEOUT_S = 12.0
DEFAULT_SLEEP_S = 0.6
DEFAULT_MAX_SUMMARY_CHARS = 320


# ============================================================
# Utilities
# ============================================================

def clip(text: str, max_chars: int) -> str:
    t = " ".join((text or "").split()).strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1].rstrip() + "…"


def fix_encoding(text: str) -> str:
    """
    Corrige casos comuns de texto UTF-8 interpretado como latin-1 (ex: 'Weâre').
    Só aplica se fizer sentido; se falhar, mantém original.
    """
    if not text:
        return text
    try:
        fixed = text.encode("latin1").decode("utf-8")
        # Heurística simples: só substitui se diminuir artefatos comuns
        if "â" in text and "â" not in fixed:
            return fixed
        return fixed if fixed != text else text
    except Exception:
        return text


def source_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def normalize_url(url: str) -> str:
    u = (url or "").strip()
    p = urlparse(u)

    netloc = (p.netloc or "").lower()
    path = p.path or ""
    if path.endswith("/") and path != "/":
        path = path[:-1]

    query = p.query
    if query:
        parts = [q for q in query.split("&") if not q.lower().startswith("utm_")]
        query = "&".join(parts)

    return urlunparse((p.scheme, netloc, path, "", query, ""))


def parse_rss(url: str) -> List[Dict[str, Any]]:
    feed = feedparser.parse(url)
    entries = getattr(feed, "entries", []) or []
    out: List[Dict[str, Any]] = []
    for e in entries:
        out.append({
            "title": (e.get("title") or "").strip(),
            "link": (e.get("link") or "").strip(),
            "summary": (e.get("summary") or "").strip() or (e.get("description") or "").strip() or (e.get("subtitle") or "").strip(),
            "published": e.get("published") or e.get("updated"),
        })
    return out


# ============================================================
# Step 2 — Summarize
# ============================================================

def build_openai_rss_summary_map(max_chars: int) -> Dict[str, str]:
    feed_url = "https://openai.com/news/rss.xml"
    mapping: Dict[str, str] = {}
    for e in parse_rss(feed_url):
        link = e.get("link") or ""
        summ = e.get("summary") or ""
        if link and summ:
            mapping[link] = clip(fix_encoding(summ), max_chars)
    return mapping


def fetch_html(url: str, timeout_s: float) -> Optional[str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout_s)
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


def summarize_item(
    item: Dict[str, Any],
    openai_summary_by_url: Dict[str, str],
    timeout_s: float,
    sleep_s: float,
    max_chars: int,
) -> Optional[str]:
    url = item.get("url") or ""
    if not isinstance(url, str) or not url.strip():
        return None

    src = (item.get("source") or "").lower()
    dom = source_domain(url)

    # OpenAI: usa RSS (evita 403)
    if src == "openai" or "openai.com" in dom:
        rss_summary = openai_summary_by_url.get(url)
        if rss_summary:
            return rss_summary

    html = fetch_html(url, timeout_s=timeout_s)
    time.sleep(sleep_s)

    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    # arXiv: abstract
    if "arxiv" in src or "arxiv.org" in dom:
        abs_txt = extract_arxiv_abstract(soup)
        return clip(fix_encoding(abs_txt or ""), max_chars) if abs_txt else None

    text = (
        extract_meta_description(soup)
        or extract_og_description(soup)
        or extract_first_paragraph(soup)
    )
    return clip(fix_encoding(text or ""), max_chars) if text else None


def step2_summarize(in_path: str, out_path: str, timeout_s: float, sleep_s: float, max_chars: int) -> None:
    openai_map = build_openai_rss_summary_map(max_chars)
    log.info("step2 openai_rss_loaded items=%s", len(openai_map))

    with open(in_path, "r", encoding="utf-8") as f:
        items: List[Dict[str, Any]] = json.load(f)

    enriched: List[Dict[str, Any]] = []
    for idx, it in enumerate(items, start=1):
        title = fix_encoding((it.get("title") or "").strip())
        it["title"] = title

        log.info("step2 summarizing %s/%s title=%s", idx, len(items), title[:90])
        summary = summarize_item(it, openai_map, timeout_s, sleep_s, max_chars)

        out = dict(it)
        out["summary"] = summary
        enriched.append(out)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)


# ============================================================
# Step 3 — Classify (rule-based)
# ============================================================

TOPICS = {
    "research_papers": ["arxiv", "preprint", "benchmark", "dataset", "theorem", "algorithm"],
    "llm_agents_reasoning": ["llm", "agent", "agents", "reasoning", "chain-of-thought", "tool", "tools", "codex"],
    "security_safety": ["security", "safety", "prompt injection", "jailbreak", "red team", "preparedness"],
    "computer_vision": ["vision", "visual", "multimodal", "image", "video", "vlm", "ocr", "forgery"],
    "product_updates": ["release", "introducing", "launch", "update", "availability", "pricing", "api", "platform"],
    "policy_society": ["policy", "regulation", "law", "governance", "ethics", "education", "literacy"],
    "business_market": ["funding", "acquisition", "ipo", "revenue", "enterprise", "partnership", "deal", "market"],
}


def classify(title: str, summary: str, source: str, url: str) -> List[str]:
    t = " ".join([title or "", summary or "", source or "", url or ""]).lower()
    tags: List[str] = []

    if "arxiv.org" in t or "arxiv" in (source or "").lower():
        tags.append("research_papers")

    for topic, keywords in TOPICS.items():
        if topic in tags:
            continue
        for kw in keywords:
            if kw in t:
                tags.append(topic)
                break

    return tags or ["general_ai_news"]


def step3_classify(in_path: str, out_path: str) -> None:
    with open(in_path, "r", encoding="utf-8") as f:
        items: List[Dict[str, Any]] = json.load(f)

    for it in items:
        it["topics"] = classify(
            title=str(it.get("title") or ""),
            summary=str(it.get("summary") or ""),
            source=str(it.get("source") or ""),
            url=str(it.get("url") or ""),
        )

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


# ============================================================
# Step 1 — Dedupe
# ============================================================

SOURCE_PRIORITY = {
    "openai": 1,
    "deepmind_google_blog": 2,
    "arxiv_cs_ai": 3,
    "techcrunch_ai": 4,
    "verge_ai": 5,
    "venturebeat_ai": 6,
}


def score(item: Dict[str, Any]) -> tuple:
    src = (item.get("source") or "").strip()
    prio = SOURCE_PRIORITY.get(src, 999)
    has_summary = 0 if not item.get("summary") else 1
    title_len = len((item.get("title") or "").strip())
    return (prio, -has_summary, -title_len)


def step1_dedupe(in_path: str, out_path: str) -> None:
    with open(in_path, "r", encoding="utf-8") as f:
        items: List[Dict[str, Any]] = json.load(f)

    best_by_url: Dict[str, Dict[str, Any]] = {}
    for it in items:
        url = it.get("url") or ""
        if not isinstance(url, str) or not url.strip():
            continue

        norm = normalize_url(url)
        it["url_normalized"] = norm

        if norm not in best_by_url or score(it) < score(best_by_url[norm]):
            best_by_url[norm] = it

    deduped = list(best_by_url.values())

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(deduped, f, ensure_ascii=False, indent=2)

    log.info("step1 dedupe before=%s after=%s", len(items), len(deduped))


# ============================================================
# Step 4 — Digest
# ============================================================

def parse_date_safe(published_at: Any) -> Optional[datetime]:
    if not published_at or not isinstance(published_at, str):
        return None
    # Melhor esforço: tenta converter strings comuns de RSS
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    ):
        try:
            return datetime.strptime(published_at, fmt)
        except Exception:
            continue
    return None


def step4_digest(in_path: str, out_md: str, out_json: str) -> None:
    with open(in_path, "r", encoding="utf-8") as f:
        items: List[Dict[str, Any]] = json.load(f)

    buckets = defaultdict(list)
    for it in items:
        topics = it.get("topics") or ["general_ai_news"]
        main_topic = topics[0] if topics else "general_ai_news"
        buckets[main_topic].append(it)

    topic_order = [
        "product_updates",
        "security_safety",
        "llm_agents_reasoning",
        "computer_vision",
        "research_papers",
        "business_market",
        "policy_society",
        "general_ai_news",
    ]

    def sort_key(it: Dict[str, Any]) -> tuple:
        dt = parse_date_safe(it.get("published_at"))
        # Ordena por data desc; sem data vai pro final
        return (0 if dt else 1, -(dt.timestamp()) if dt else 0, (it.get("title") or ""))

    for topic in buckets:
        buckets[topic].sort(key=sort_key)

    now_local = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: List[str] = []
    lines.append(f"# AI Digest — {now_local}\n")
    lines.append(f"Total de itens: **{len(items)}**\n")

    def fmt_item(it: Dict[str, Any]) -> str:
        title = fix_encoding((it.get("title") or "").strip())
        url = (it.get("url") or "").strip()
        src = (it.get("source") or "").strip()
        pub = (it.get("published_at") or "")
        summary = it.get("summary") or ""
        summary = fix_encoding(summary.strip()) if isinstance(summary, str) else ""

        if summary:
            return f"- **{title}** ({src}) — {pub}\n  - {summary}\n  - {url}\n"
        return f"- **{title}** ({src}) — {pub}\n  - {url}\n"

    for topic in topic_order:
        if topic not in buckets:
            continue
        lines.append(f"\n## {topic}\n")
        for it in buckets[topic][:25]:
            lines.append(fmt_item(it))

    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    digest = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "total_items": len(items),
        "items": items,
    }
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(digest, f, ensure_ascii=False, indent=2)

    log.info("step4 digest out_md=%s out_json=%s total=%s", out_md, out_json, len(items))


# ============================================================
# Main
# ============================================================

def main() -> int:
    parser = argparse.ArgumentParser(description="Run AI News pipeline end-to-end")
    parser.add_argument("--in", dest="in_path", default="ai_news.json")
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--sleep-s", type=float, default=DEFAULT_SLEEP_S)
    parser.add_argument("--max-summary-chars", type=int, default=DEFAULT_MAX_SUMMARY_CHARS)
    args = parser.parse_args()

    step2_out = "ai_news_step2_with_summary.json"
    step3_out = "ai_news_step3_classified.json"
    step1_out = "ai_news_step1_deduped.json"
    digest_md = "ai_digest.md"
    digest_json = "ai_digest.json"

    log.info("pipeline_start in=%s", args.in_path)

    step2_summarize(args.in_path, step2_out, args.timeout_s, args.sleep_s, args.max_summary_chars)
    log.info("step2_done out=%s", step2_out)

    step3_classify(step2_out, step3_out)
    log.info("step3_done out=%s", step3_out)

    step1_dedupe(step3_out, step1_out)
    log.info("step1_done out=%s", step1_out)

    step4_digest(step1_out, digest_md, digest_json)
    log.info("step4_done out_md=%s out_json=%s", digest_md, digest_json)

    log.info("pipeline_done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
