from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List


logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
log = logging.getLogger("step4_digest")


def main() -> int:
    in_path = "ai_news_step1_deduped.json"
    out_md = "ai_digest.md"
    out_json = "ai_digest.json"

    with open(in_path, "r", encoding="utf-8") as f:
        items: List[Dict[str, Any]] = json.load(f)

    # Agrupa por topic principal (primeiro da lista)
    buckets = defaultdict(list)
    for it in items:
        topics = it.get("topics") or ["general_ai_news"]
        main_topic = topics[0] if topics else "general_ai_news"
        buckets[main_topic].append(it)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: List[str] = []
    lines.append(f"# AI Digest — {now}\n")
    lines.append(f"Total de itens: **{len(items)}**\n")

    # Ordem “útil”
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

    def fmt_item(it: Dict[str, Any]) -> str:
        title = (it.get("title") or "").strip()
        url = (it.get("url") or "").strip()
        src = (it.get("source") or "").strip()
        pub = (it.get("published_at") or "")
        summary = (it.get("summary") or "")
        summary = summary.strip() if isinstance(summary, str) else ""
        if summary:
            return f"- **{title}** ({src}) — {pub}\n  - {summary}\n  - {url}\n"
        return f"- **{title}** ({src}) — {pub}\n  - {url}\n"

    for topic in topic_order:
        if topic not in buckets:
            continue
        lines.append(f"\n## {topic}\n")
        # limita para não ficar gigante (ajuste se quiser)
        for it in buckets[topic][:25]:
            lines.append(fmt_item(it))

    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # JSON final (pronto para integração com n8n/Telegram/etc.)
    digest = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "total_items": len(items),
        "items": items,
    }
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(digest, f, ensure_ascii=False, indent=2)

    log.info("done out_md=%s out_json=%s total=%s", out_md, out_json, len(items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
