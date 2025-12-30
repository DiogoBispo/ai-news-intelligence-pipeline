from __future__ import annotations

import json
import logging
from typing import Any, Dict, List
from urllib.parse import urlparse, urlunparse


logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
log = logging.getLogger("step1_dedupe")


# prioridade de fontes (ajuste como quiser)
SOURCE_PRIORITY = {
    "openai": 1,
    "deepmind_google_blog": 2,
    "arxiv_cs_ai": 3,
    "techcrunch_ai": 4,
    "verge_ai": 5,
    "venturebeat_ai": 6,
    # desconhecidas ficam no final
}


def normalize_url(url: str) -> str:
    u = url.strip()
    p = urlparse(u)

    # remove fragment (#...), normaliza netloc e path
    netloc = (p.netloc or "").lower()
    path = p.path or ""

    # remove trailing slash (exceto raiz)
    if path.endswith("/") and path != "/":
        path = path[:-1]

    # mantém query (às vezes identifica conteúdo), mas remove utm_* comuns
    # sem depender de libs: filtragem simples
    query = p.query
    if query:
        parts = [q for q in query.split("&") if not q.lower().startswith("utm_")]
        query = "&".join(parts)

    return urlunparse((p.scheme, netloc, path, "", query, ""))


def score(item: Dict[str, Any]) -> tuple:
    src = (item.get("source") or "").strip()
    prio = SOURCE_PRIORITY.get(src, 999)

    has_summary = 0 if not item.get("summary") else 1
    title_len = len((item.get("title") or "").strip())

    # Queremos: maior prioridade (menor número), ter summary, e título mais longo (heurística)
    # Como Python ordena crescente: usamos (prio, -has_summary, -title_len)
    return (prio, -has_summary, -title_len)


def main() -> int:
    in_path = "ai_news_step3_classified.json"
    out_path = "ai_news_step1_deduped.json"

    with open(in_path, "r", encoding="utf-8") as f:
        items: List[Dict[str, Any]] = json.load(f)

    best_by_url: Dict[str, Dict[str, Any]] = {}

    for it in items:
        url = it.get("url") or ""
        if not isinstance(url, str) or not url.strip():
            continue

        norm = normalize_url(url)
        it["url_normalized"] = norm

        if norm not in best_by_url:
            best_by_url[norm] = it
            continue

        # troca se o item atual for "melhor"
        if score(it) < score(best_by_url[norm]):
            best_by_url[norm] = it

    deduped = list(best_by_url.values())

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(deduped, f, ensure_ascii=False, indent=2)

    log.info("done out=%s before=%s after=%s", out_path, len(items), len(deduped))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
