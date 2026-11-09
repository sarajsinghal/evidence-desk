from __future__ import annotations
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from urllib.parse import urlparse
import re
from .providers import SearchHit, canonical_url


OFFICIAL_HINTS = (".gov", ".edu", ".int", "who.int", "un.org", "data.worldbank.org", "oecd.org")
NEWS_HINTS = ("reuters.com", "apnews.com", "bbc.com", "theguardian.com", "nytimes.com")


def classify_source(url: str) -> tuple[str, str]:
    host = urlparse(url).netloc.lower()
    if any(h in host for h in OFFICIAL_HINTS):
        return "Institutional / primary-leaning", "Domain hint only; verify the publisher and underlying evidence."
    if any(h in host for h in NEWS_HINTS):
        return "News publisher", "Publisher label is a heuristic, not an authority score."
    return "Unclassified", "Authority has not been independently assessed."


def normalize_sources(hits: list[SearchHit]) -> list[dict]:
    groups: dict[str, list[SearchHit]] = defaultdict(list)
    for hit in hits:
        if hit.url.startswith(("http://", "https://")):
            groups[canonical_url(hit.url)].append(hit)
    sources = []
    for key, items in groups.items():
        first = items[0]
        kind, note = classify_source(first.url)
        snippets = list(dict.fromkeys(x.snippet.strip() for x in items if x.snippet.strip()))
        contents = [x.raw_content.strip() for x in items if x.raw_content and x.raw_content.strip()]
        sources.append({"url": first.url, "canonical_url": key, "title": next((x.title for x in items if x.title), "Untitled"),
                        "published_date": next((x.published_date for x in items if x.published_date), None),
                        "snippet": "\n\n".join(snippets), "content": "\n\n".join(contents),
                        "providers": sorted({x.provider for x in items}), "source_type": kind,
                        "authority_note": note, "match_count": len(items)})
    return sources


def candidate_claims(sources: list[dict], limit: int = 12) -> list[dict]:
    """Extract sentence candidates by punctuation; bilingual-neutral, intentionally conservative."""
    candidates = []
    seen: set[str] = set()
    for source in sources:
        # Search excerpts are better claim candidates than long page dumps, which
        # often contain navigation text, tables, and broken sentence fragments.
        text = source.get("snippet") or source.get("content", "")
        for sentence in re.split(r"(?<=[.!?।])\s+|\n+", text):
            clean = re.sub(r"\s+", " ", sentence).strip(" \t\r\n-•")
            if len(clean) < 45 or len(clean) > 420:
                continue
            key = re.sub(r"\W+", " ", clean.lower()).strip()
            if key and key not in seen:
                seen.add(key)
                candidates.append({"claim": clean, "source_urls": [source["url"]], "status": "Needs human review",
                                   "reason": "Sentence candidate from retrieved text; no semantic verification was performed."})
                if len(candidates) >= limit:
                    return candidates
    return candidates


def build_report(question: str, sources: list[dict], claims: list[dict], provider_status: dict) -> dict:
    return {"question": question, "created_at": datetime.now(timezone.utc).isoformat(), "provider_status": provider_status,
            "sources": sources, "claims": claims,
            "summary": f"Retrieved {len(sources)} unique source(s). Automated claim candidates require human review; search snippets do not establish truth."}


def to_markdown(report: dict) -> str:
    lines = ["# Research evidence report", "", f"**Question:** {report['question']}", "",
             f"**Generated:** {report['created_at']}", "", f"> {report['summary']}", "", "## Provider status", ""]
    for name, status in report["provider_status"].items():
        lines.append(f"- **{name}:** {status}")
    lines += ["", "## Evidence sources", ""]
    for n, s in enumerate(report["sources"], 1):
        lines += [f"### [{n}] [{s['title']}]({s['url']})", f"- Provider(s): {', '.join(s['providers'])}",
                  f"- Published: {s['published_date'] or 'Not provided'}", f"- Source type: {s['source_type']}",
                  f"- Authority note: {s['authority_note']}", "", s["snippet"] or "No snippet returned.", ""]
    lines += ["## Candidate claims — human review required", ""]
    for c in report["claims"]:
        refs = ", ".join(f"[{i+1}]({u})" for i, u in enumerate(c["source_urls"]))
        lines.append(f"- **{c['status']}:** {c['claim']} {refs}")
    if not report["claims"]:
        lines.append("No sufficiently long sentence candidates were found in returned excerpts.")
    return "\n".join(lines)
