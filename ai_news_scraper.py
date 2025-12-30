from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Callable, Iterable, Optional, List
import random
import requests
import feedparser
from bs4 import BeautifulSoup


# ----------------------------
# Logging (structured JSON)
# ----------------------------

class JsonFormatter (logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "time": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
        
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)
    
logger = logging.getLogger("ai_news_scraper")
handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger.addHandler(handler)
logger.setLevel(logging.INFO)


# ----------------------------
# Models
# ----------------------------

@dataclass(frozen=True)
class NewsItem:
    source: str 
    title: str 
    url: str 
    published_at: Optional[str] = None 
    
@dataclass(frozen=True)
class Source: 
    name: str 
    fetcher: Callable[[requests.Session, int, float], List[NewsItem]]
    

# ----------------------------
# HTTP helpers
# ----------------------------

DEFAULT_HEADERS = {
    # Identifique seu bot de forma honesta.
    "User-Agent": "AI-News-Scraper/1.0 (+https://example.com; contact: you@example.com)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def get_html(session: requests.Session, url: str, timeout_s: float, max_retries: int = 3) -> str:
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, headers=DEFAULT_HEADERS, timeout=timeout_s)
            if resp.status_code == 429:
                # backoff exponencial com jitter
                sleep_s = (2 ** attempt) + random.uniform(0.0, 0.8)
                logger.warning(f"rate_limited url={url} attempt={attempt} sleep_s={sleep_s:.2f}")
                time.sleep(sleep_s)
                continue
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            last_exc = e
            sleep_s = (2 ** attempt) + random.uniform(0.0, 0.5)
            logger.warning(f"http_retry url={url} attempt={attempt} err={type(e).__name__} sleep_s={sleep_s:.2f}")
            time.sleep(sleep_s)
    raise last_exc  # type: ignore

def parse_rss(url: str, limit: int) -> List[NewsItem]:
    feed = feedparser.parse(url) 
    items = []
    for entry in feed.entries[:limit]:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        published = entry.get("published") or entry.get("updated")
        
        items.append(NewsItem(source="", title=title, url=link, published_at=published))
    return items

def iso_or_none(text: str) -> Optional[str]:
    t = (text or "").strip()
    return t if t else None 

# ----------------------------
# RSS-based sources 
# ----------------------------

def fetch_openai_news(session: requests.Session, limit: int, timeout_s: float) -> List[NewsItem]:
    url =  "https://openai.com/news/rss.xml"
    raw = parse_rss(url, limit)
    return [NewsItem(source="openia", title=i.title, url=i.url, published_at=i.published_at) for i in raw] 

def fetch_arxiv_cs_ai(session: requests.Session, limit: int, timeout_s: float) -> List[NewsItem]:
    url = "https://export.arxiv.org/rss/cs.AI"
    raw = parse_rss(url, limit)
    return [NewsItem(source="arxiv_cs_ai", title=i.title, url=i.url, published_at=i.published_at) for i in raw]


# ----------------------------
# HTML-based sources 
# ----------------------------


def fetch_venturebeat_ai(session: requests.Session, limit: int, timeout_s: float) -> List[NewsItem]:
    feed_url = "http://feeds.venturebeat.com/VentureBeat"
    raw = parse_rss(feed_url, limit=50)
    
    items: List[NewsItem] = []    
    for it in raw: 
        if "/ai/" in it.url:
            items.append(
                NewsItem(
                    source="venturebeat_ai",
                    title=it.title,
                    url=it.url,
                    published_at=it.published_at,
                    ))
        if len(items) >= limit:
                break
        return items 
    
def fetch_techcrunch_ai(session: requests.Session, limit: int, timeout_s: float) -> List[NewsItem]:
    url = "https://techcrunch.com/category/artificial-intelligence/"
    html = get_html(session, url, timeout_s)
    soup = BeautifulSoup(html, "html.parser")
    
    items: List[NewsItem] = []    
    for a in soup.select("a.post-block__title__link, h2 a, h3 a"):
        title = a.get_text(strip=True)
        link = a.get("href")
        if not title or not isinstance(link, str) or not link.strip():
            continue
        link = link.strip()
        if link.startswith("https://techcrunch.com/"):
            items.append(NewsItem(source="techcrunch_ai", title=title, url=link))
        if len(items) >= limit:
            break
    return items 

def fetch_verge_ai(session: requests.Session, limit: int, timeout_s: float) -> List[NewsItem]:
    url = "https://www.theverge.com/ai-artificial-intelligence"
    html = get_html(session, url, timeout_s)
    soup = BeautifulSoup(html, "html.parser")
    
    items: List[NewsItem] = []    
    for a in soup.select("h2 a, h3 a"):
        title = a.get_text(strip=True)
        link = a.get("href")
        if not title or not isinstance(link, str) or not link.strip():
            continue
        link = link.strip()
        if link.startswith("/"):
            link = "https://www.theverge.com" + link 
        if link.startswith("https://www.theverge.com/"):
            items.append(NewsItem(source="verge_ai", title=title, url=link))
        if len(items) >= limit:
            break
    return items

def fetch_deepmind_google_blog(session: requests.Session, limit: int, timeout_s: float) -> List[NewsItem]:
    url = "https://deepmind.google/blog/"
    html = get_html(session, url, timeout_s)
    soup = BeautifulSoup(html, "html.parser")

    items: List[NewsItem] = []
    
    for a in soup.select("a[href^='/blog/']"):
        href = a.get("href")
        if not isinstance(href, str):
            continue
        href = href.strip()
        if href.startswith("/blog/page"):
            continue
        full = "https://deepmind.google" + href 
        
        title = None 
        container = a.parent
        for _ in range(4):
            if container is None:
                break
            h3 = container.find("h3")
            if h3:
                title = h3.get_text(strip=True)
                break 
            container = container.parent
        if title:
            items.append(NewsItem(source="deepmind_google_blog", title=title, url=full))

        if len(items) >= limit:
            break

    return items
            
def fetch_techreview_ai(session: requests.Session, limit: int, timeout_s: float) -> List[NewsItem]:
    url = "https://www.technologyreview.com/artificial-intelligence/"
    html = get_html(session, url, timeout_s)
    soup = BeautifulSoup(html, "html.parser")
    
    items: List[NewsItem] = []
    for a in soup.select("h2 a, h3 a"):
        title = a.get_text(strip=True)
        link = a.get("href", "").strip()
        if not title or not link:
            continue
        if link.startswith("/"):
            link = "https://www.technologyreview.com" + link
        if link.startswith("https://www.technologyreview.com/"):
            items.append(NewsItem(source="techreview_ai", title=title, url=link))
        if len(items) >= limit:
            break
    return items

# ----------------------------
# Orchestration
# ----------------------------

SOURCES: List[Source] = [
    Source(name="openai_news_rss", fetcher=fetch_openai_news),
    Source(name="arxiv_cs_ai_rss", fetcher=fetch_arxiv_cs_ai),
    Source(name="venturebeat_ai_html", fetcher=fetch_venturebeat_ai),
    Source(name="techcrunch_ai_html", fetcher=fetch_techcrunch_ai),
    Source(name="verge_ai_html", fetcher=fetch_verge_ai),
    Source(name="deepmind_google_blog_html", fetcher=fetch_deepmind_google_blog),
    Source(name="techreview_ai_html", fetcher=fetch_techreview_ai),
    
]

def run(limit_per_source: int, timeout_s: float, sleep_s: float) -> List[NewsItem]:
    results: List[NewsItem] = []
    with requests.Session() as session:
        for src in SOURCES:
            started = time.time()
            try:
                logger.info(f"source_start name={src.name}")
                items = src.fetcher(session, limit_per_source, timeout_s) or []
                #items = src.fetcher(session, limit_per_source, timeout_s)
                results.extend(items)
                elapsed_ms = int((time.time() - started) * 1000)
                logger.info(f"source_ok name={src.name} items={len(items)} elapsed_ms={elapsed_ms}")
            except Exception as e:
                elapsed_ms = int((time.time() - started) * 1000)
                logger.error(f"source_error name={src.name=} elapsed_ms={elapsed_ms} err={type(e).__name__}: {e}")
            time.sleep(sleep_s)
        return results 
    
def main() -> int:
    parser = argparse.ArgumentParser(description="AI news scraper (RSS/HTML headlines)")
    parser.add_argument("--limit-per-source", type=int, default=10)
    parser.add_argument("--timeout-s", type=float, default=12.0)
    parser.add_argument("--sleep-s", type=float, default=1.0)
    parser.add_argument("--out", type=str, default="ai_news.json")
    args = parser.parse_args()
    
    logger.info("run_start")
    items = run(args.limit_per_source, args.timeout_s, args.sleep_s)
    
    payload = [asdict(i) for i in items]
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    
    logger.info(f"run_done total_items={len(items)} out={args.out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
    