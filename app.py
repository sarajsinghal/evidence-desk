from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from research_lab.engine import (
    build_report,
    candidate_claims,
    normalize_sources,
    to_markdown,
)
from research_lab.providers import (
    SearchHit,
    ProviderError,
    parallel_search,
    tavily_search,
)
from research_lab.storage import get_report, recent_runs, save_report

st.set_page_config(
    page_title="Evidence Desk | Project 11",
    page_icon="◈",
    layout="wide",
)

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');

.stApp {
    background: #f4f7f7 !important;
    color: #182b33 !important;
    font-family: 'DM Sans', sans-serif;
}

.block-container {
    padding-top: 2rem;
    max-width: 1350px;
    padding-left: 2.2rem;
    padding-right: 2.2rem;
}

h1, h2, h3 {
    font-family: 'Manrope', sans-serif;
    letter-spacing: -.035em;
}

.hero {
    padding: 1.5rem 1.7rem;
    background: linear-gradient(115deg, #10343a, #17645b);
    border-radius: 18px;
    color: #f0fbf7;
    margin-bottom: 1rem;
}

.hero h1 {
    font-size: 2.4rem;
    margin: 0;
    color: #ffffff !important;
}

.hero p {
    color: #ffffff !important;
    font-size: 1.1rem;
    margin: .6rem 0 0;
}

.eyebrow {
    font-size: .75rem;
    letter-spacing: .16em;
    text-transform: uppercase;
    color: #8bd4b8;
    font-weight: 700;
}

.metric {
    padding: 1.05rem 1.2rem;
    background: #ffffff;
    border: 1px solid #e0e9e6;
    border-radius: 14px;
}

.metric b {
    font: 700 1.65rem Manrope;
    color: #17645b;
}

.metric span {
    display: block;
    color: #627379;
    font-size: .86rem;
    margin-top: .25rem;
}

.notice {
    padding: .8rem 1rem;
    border-left: 4px solid #d49a42;
    background: #fff8e9;
    border-radius: 7px;
    color: #604b22;
}

div[data-testid="stTabs"] button {
    font-weight: 700;
    color: #4c6168 !important;
}

div[data-testid="stTabs"] button[aria-selected="true"] {
    color: #a72d43 !important;
}

a {
    color: #147568 !important;
}

/* Keep the question field readable in either browser theme. */
div[data-testid="stTextArea"] textarea {
    background: #ffffff !important;
    color: #182b33 !important;
    border: 1px solid #b9cbc6 !important;
    caret-color: #17645b !important;
}

div[data-testid="stTextArea"] textarea::placeholder {
    color: #718187 !important;
    opacity: 1;
}

/* Light sidebar with readable labels. */
div[data-testid="stSidebar"] {
    min-width: 19rem !important;
    width: 19rem !important;
    background: #ffffff !important;
    border-right: 1px solid #dce7e4;
}

div[data-testid="stSidebar"] * {
    color: #20343b;
}

div[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
    color: #52676d !important;
}

div[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
div[data-testid="stSidebar"] label,
div[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
    overflow-wrap: anywhere;
}

div[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
    line-height: 1.45;
}

div[data-testid="stAlert"] p {
    color: #26383e !important;
}

div[data-testid="stMarkdownContainer"] p,
div[data-testid="stMarkdownContainer"] li {
    color: #26383e;
}

div[data-testid="stExpander"] summary {
    color: #26383e !important;
}

/* Strong contrast for the main action button. */
button[kind="primary"],
button[kind="primary"] * {
    color: #ffffff !important;
    background-color: #b8344a !important;
    border-color: #b8344a !important;
}

@media (max-width: 700px) {
    .block-container {
        padding-left: 1rem;
        padding-right: 1rem;
    }

    .hero h1 {
        font-size: 1.8rem;
    }

    div[data-testid="stSidebar"] {
        min-width: unset !important;
        width: unset !important;
    }
}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="hero">
    <div class="eyebrow">PROJECT 11 · RESEARCH SYSTEMS</div>
    <h1>Evidence Desk</h1>
    <p>Two independent web search providers. Transparent source trails. Human-led conclusions.</p>
</div>
""",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### Research controls")

    demo = st.toggle(
        "Demo mode",
        value=not bool(
            os.getenv("PARALLEL_API_KEY") or os.getenv("TAVILY_API_KEY")
        ),
        help="Runs a local sample without network calls or API keys.",
    )

    pkey = os.getenv("PARALLEL_API_KEY", "")
    tkey = os.getenv("TAVILY_API_KEY", "")

    st.markdown("**Search providers**")
    st.caption(f"Parallel {'✓ Ready' if pkey else '○ Add API key'}")
    st.caption(f"Tavily {'✓ Ready' if tkey else '○ Add API key'}")

    limit = st.slider("Results per provider", 3, 15, 8)
    depth = st.selectbox("Tavily search depth", ["basic", "advanced"])
    timeout = st.slider("Provider timeout (seconds)", 5, 60, 25)

    st.caption(
        "API keys are read from environment variables or .env "
        "and never stored in research history."
    )

tab_research, tab_history, tab_about = st.tabs(
    ["Research", "History", "Method & limits"]
)

with tab_research:
    question = st.text_area(
        "Research question",
        placeholder="Ask in English or Hindi… / अंग्रेज़ी या हिंदी में प्रश्न पूछें…",
        height=105,
    )

    run = st.button(
        "Run evidence search",
        type="primary",
        disabled=not question.strip(),
    )

    if run:
        statuses: dict[str, str] = {}
        hits: list[SearchHit] = []

        if demo:
            hits = [
                SearchHit(
                    "Parallel",
                    "https://www.who.int/news-room/fact-sheets/detail/"
                    "climate-change-and-health",
                    "Climate change and health",
                    "Climate change is already impacting health in a myriad "
                    "of ways, including by leading to death and illness from "
                    "increasingly frequent extreme weather events.",
                    "2023-10-12",
                ),
                SearchHit(
                    "Tavily",
                    "https://www.who.int/news-room/fact-sheets/detail/"
                    "climate-change-and-health?utm_source=demo",
                    "Climate change and health",
                    "Climate change is already impacting health in a myriad "
                    "of ways, including by leading to death and illness from "
                    "increasingly frequent extreme weather events.",
                    "2023-10-12",
                ),
                SearchHit(
                    "Tavily",
                    "https://www.ipcc.ch/report/ar6/wg2/",
                    "Climate Change 2022: Impacts, Adaptation and Vulnerability",
                    "Climate change has caused substantial damages, and "
                    "increasingly irreversible losses, in terrestrial, "
                    "freshwater and coastal and open ocean marine ecosystems.",
                ),
            ]
            statuses = {
                "Parallel": "Demo fixture",
                "Tavily": "Demo fixture",
            }
        else:
            if pkey:
                try:
                    got = parallel_search(pkey, question, limit, timeout)
                    hits.extend(got)
                    statuses["Parallel"] = f"Success · {len(got)} result(s)"
                except ProviderError as exc:
                    statuses["Parallel"] = f"Unavailable · {exc}"
            else:
                statuses["Parallel"] = (
                    "Unavailable · PARALLEL_API_KEY is not configured"
                )

            if tkey:
                try:
                    got = tavily_search(
                        tkey,
                        question,
                        limit,
                        depth,
                        timeout,
                    )
                    hits.extend(got)
                    statuses["Tavily"] = f"Success · {len(got)} result(s)"
                except ProviderError as exc:
                    statuses["Tavily"] = f"Unavailable · {exc}"
            else:
                statuses["Tavily"] = (
                    "Unavailable · TAVILY_API_KEY is not configured"
                )

        sources = normalize_sources(hits)
        claims = candidate_claims(sources)
        report = build_report(question.strip(), sources, claims, statuses)
        report["mode"] = "demo" if demo else "live"
        report["id"] = save_report(
            report,
            ROOT / "data" / "research.sqlite",
        )
        st.session_state["current_report"] = report

    report = st.session_state.get("current_report")

    if report:
        st.markdown(f"#### Evidence brief · {report['question']}")

        c1, c2, c3 = st.columns(3)
        metrics = [
            (c1, len(report["sources"]), "Unique sources"),
            (c2, len(report["claims"]), "Candidate claims"),
            (
                c3,
                "Demo" if report.get("mode") == "demo" else "Live",
                "Run mode",
            ),
        ]

        for col, value, label in metrics:
            col.markdown(
                f'<div class="metric"><b>{value}</b><span>{label}</span></div>',
                unsafe_allow_html=True,
            )

        st.markdown(
            f'<div class="notice">{report["summary"]}</div>',
            unsafe_allow_html=True,
        )

        with st.expander("Provider status", expanded=True):
            for name, status in report["provider_status"].items():
                st.write(f"**{name}:** {status}")

        st.markdown("### Candidate claims")

        if not report["claims"]:
            st.info(
                "No sentence candidates found. Search excerpts can be too short "
                "or fragmentary."
            )

        if not report["sources"]:
            st.warning(
                "No search results were returned. Check that at least one "
                "search API key is configured, or turn on Demo mode to preview "
                "the lab."
            )

        for claim in report["claims"]:
            with st.container(border=True):
                st.markdown(
                    f"**{claim['status']}** · {claim['claim']}"
                )
                st.caption(claim["reason"])

                for url in claim["source_urls"]:
                    st.markdown(f"[Open source]({url})")

        st.markdown(f"### Sources · {len(report['sources'])}")

        for i, source in enumerate(report["sources"], 1):
            with st.expander(
                f"[{i}] {source['title']} · "
                f"{', '.join(source['providers'])}"
            ):
                st.markdown(
                    f"**URL:** [{source['url']}]({source['url']})"
                )
                st.write(
                    f"Publication date: "
                    f"{source['published_date'] or 'Not provided'}"
                )
                st.write(f"Source type: {source['source_type']}")
                st.caption(source["authority_note"])
                st.text(
                    source["content"]
                    or source["snippet"]
                    or "No page excerpt returned."
                )

        markdown_report = to_markdown(report)
        d1, d2, d3 = st.columns(3)

        d1.download_button(
            "Download Markdown",
            markdown_report,
            file_name="research-report.md",
            mime="text/markdown",
        )

        d2.download_button(
            "Download JSON",
            json.dumps(report, ensure_ascii=False, indent=2),
            file_name="research-report.json",
            mime="application/json",
        )

        flat_sources = [
            {
                "title": source["title"],
                "url": source["url"],
                "published_date": source["published_date"],
                "providers": ";".join(source["providers"]),
                "source_type": source["source_type"],
                "snippet": source["snippet"],
            }
            for source in report["sources"]
        ]

        d3.download_button(
            "Download sources CSV",
            pd.DataFrame(flat_sources).to_csv(index=False),
            file_name="research-sources.csv",
            mime="text/csv",
        )

with tab_history:
    st.markdown("### Local research history")
    rows = recent_runs(ROOT / "data" / "research.sqlite")

    if not rows:
        st.info("Research runs will appear here after the first search.")

    for row in rows:
        with st.expander(
            f"#{row['id']} · {row['question']} · {row['created_at'][:16]}"
        ):
            saved = get_report(
                row["id"],
                ROOT / "data" / "research.sqlite",
            )
            st.markdown(to_markdown(saved))
            st.download_button(
                "Export saved JSON",
                json.dumps(saved, ensure_ascii=False, indent=2),
                file_name=f"research-{row['id']}.json",
                key=f"json-{row['id']}",
            )

with tab_about:
    st.markdown("### How this lab handles evidence")

    st.write(
        "Parallel Search and Tavily Search run independently. Results are "
        "grouped by canonical URL; provider overlap is shown as provenance, "
        "not counted as independent confirmation. The system preserves "
        "titles, URLs, dates when available, snippets, provider names, and "
        "Tavily raw content when returned."
    )

    st.write(
        "Candidate claims come from sentence-boundary heuristics only. "
        "Every candidate is marked **Needs human review**. There is no LLM "
        "or model API integration."
    )

    st.write(
        "Source labels use simple domain hints and are not credibility scores. "
        "A domain ending in .gov or appearing in a known-publisher list is "
        "not proof that an individual claim is accurate. Check the underlying "
        "page, date, authorship, and primary evidence."
    )

    st.markdown("### Data and privacy")
    st.write(
        "Research questions and returned results are sent to whichever "
        "configured search provider you run. Results are saved in local "
        "SQLite history. This MVP has no document upload feature and never "
        "uploads user documents. Keep `.env`, database files, and backups "
        "out of public repositories."
    )

    st.markdown("### Architecture")
    st.code(
        """Question (English / Hindi)
   ├── Parallel Search API ──┐
   └── Tavily Search API ────┤
                             ▼
                Normalize + deduplicate
                             ▼
              Candidate sentence heuristics
                             ▼
       Human review · cited report · SQLite · exports
            (No LLM or model API calls)""",
        language="text",
    )

    st.markdown("### Known limitations")
    st.write(
        "Search coverage and freshness vary by provider. Search responses "
        "may omit dates or full content. Deduplication is URL based and may "
        "miss syndicated copies or alternate URLs. Sentence extraction is "
        "not semantic claim extraction. Evidence agreement/conflict is not "
        "automatically decided. Treat the report as a research starting "
        "point, never as a fact certification."
    )