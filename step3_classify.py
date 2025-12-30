from __future__ import annotations

import json
import logging
from typing import Any, Dict, List


logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
log = logging.getLogger("step3_classify")


# Taxonomia simples (você pode expandir depois)
TOPICS = {
    "research_papers": ["arxiv", "preprint", "benchmark", "dataset", "proof", "theorem", "algorithm"],
    "llm_agents_reasoning": ["llm", "agent", "agents", "reasoning", "chain-of-thought", "cot", "tool", "tools"],
    "security_safety": ["security", "safety", "prompt injection", "jailbreak", "hardening", "red team", "model spec"],
    "computer_vision": ["vision", "visual", "multimodal", "image", "video", "vlm", "ocr", "forgery"],
    "product_updates": ["release", "introducing", "launch", "update", "availability", "pricing", "api", "platform"],
    "policy_society": ["policy", "regulation", "law", "governance", "ethics", "election", "education", "literacy"],
    "business_market": ["funding", "acquisition", "ipo", "revenue", "enterprise", "partnership", "deal", "market"],
}


def classify(title: str, summary: str, source: str, url: str) -> List[str]:
    t = " ".join([title or "", summary or "", source or "", url or ""]).lower()

    tags: List[str] = []

    # regra forte: arXiv
    if "arxiv.org" in t or "arxiv" in (source or "").lower():
        tags.append("research_papers")

    for topic, keywords in TOPICS.items():
        if topic in tags:
            continue
        for kw in keywords:
            if kw in t:
                tags.append(topic)
                break

    if not tags:
        tags = ["general_ai_news"]

    return tags


def main() -> int:
    in_path = "ai_news_step2_with_summary.json"
    out_path = "ai_news_step3_classified.json"

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

    log.info("done out=%s total=%s", out_path, len(items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
