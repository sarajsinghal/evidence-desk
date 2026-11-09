import json
from unittest.mock import Mock, patch

import pytest

from research_lab.engine import candidate_claims, normalize_sources, to_markdown
from research_lab.providers import ProviderError, parallel_search, tavily_search, canonical_url
from research_lab.storage import get_report, recent_runs, save_report
from research_lab.gemini import analyze_evidence


@patch("research_lab.providers.requests.post")
def test_parallel_contract_and_normalization(mock_post):
    mock_post.return_value = Mock(ok=True, json=lambda: {"results": [{"url": "https://example.org/a", "title": "Example", "publish_date": "2025-01-02", "excerpts": ["A sufficiently detailed sentence about a public research finding, including enough words for candidate extraction."]}]})
    hits = parallel_search("secret", "question", 4)
    assert hits[0].published_date == "2025-01-02"
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.parallel.ai/v1/search"
    assert kwargs["headers"]["x-api-key"] == "secret"
    assert kwargs["json"]["objective"] == "question"
    assert kwargs["json"]["advanced_settings"]["max_results"] == 4
    sources = normalize_sources(hits)
    assert sources[0]["providers"] == ["Parallel"]
    assert candidate_claims(sources)[0]["status"] == "Needs human review"


@patch("research_lab.providers.requests.post")
def test_tavily_contract_and_raw_content(mock_post):
    mock_post.return_value = Mock(ok=True, json=lambda: {"results": [{"url": "https://example.org/a", "title": "T", "content": "summary", "raw_content": "full article", "published_date": "2024-03-01", "score": 0.8}]})
    hits = tavily_search("secret", "question", 5, "advanced")
    assert hits[0].raw_content == "full article"
    _, kwargs = mock_post.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer secret"
    assert kwargs["json"]["search_depth"] == "advanced"
    assert kwargs["json"]["include_raw_content"] is True


def test_deduplicate_tracking_query_but_preserve_provider_provenance():
    hits = [
        __import__("research_lab.providers", fromlist=["SearchHit"]).SearchHit("Parallel", "https://www.example.org/x?utm_source=a", "A", "one"),
        __import__("research_lab.providers", fromlist=["SearchHit"]).SearchHit("Tavily", "https://example.org/x?utm_source=b", "A", "two"),
    ]
    sources = normalize_sources(hits)
    assert len(sources) == 1
    assert sources[0]["providers"] == ["Parallel", "Tavily"]
    assert canonical_url("https://www.example.org/x?utm_source=b") == "https://example.org/x"


@patch("research_lab.providers.requests.post")
def test_provider_errors_do_not_become_fake_results(mock_post):
    response = Mock(ok=False, status_code=401, text="unauthorized")
    mock_post.return_value = response
    with pytest.raises(ProviderError) as err:
        parallel_search("bad", "question", retries=0)
    assert err.value.provider == "Parallel"
    assert err.value.status_code == 401


def test_markdown_and_history_are_local_and_readable(tmp_path):
    report = {"question": "प्रश्न?", "created_at": "now", "provider_status": {"Parallel": "demo"}, "sources": [], "claims": [], "summary": "Human review required."}
    path = tmp_path / "runs.sqlite"
    run_id = save_report(report, path)
    assert get_report(run_id, path)["question"] == "प्रश्न?"
    assert recent_runs(path)[0]["id"] == run_id
    assert "## Evidence sources" in to_markdown(report)


@patch("research_lab.gemini.requests.post")
def test_gemini_synthesis_requires_and_maps_source_citations(mock_post):
    payload = {"summary":"Summary", "findings":[{"claim":"A claim", "status":"supported", "source_ids":[1], "rationale":"Excerpt supports it."}], "gaps":[]}
    mock_post.return_value = Mock(ok=True, json=lambda: {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]})
    result = analyze_evidence("secret", "question", [{"title":"T", "url":"https://example.org", "snippet":"Evidence"}])
    assert result["findings"][0]["source_urls"] == ["https://example.org"]
    args, kwargs = mock_post.call_args
    assert "generateContent" in args[0]
    assert kwargs["params"] == {"key":"secret"}


@patch("research_lab.gemini.requests.post")
def test_gemini_invalid_source_id_is_downgraded(mock_post):
    payload = {"summary":"S", "findings":[{"claim":"C", "status":"supported", "source_ids":[9], "rationale":"x"}], "gaps":[]}
    mock_post.return_value = Mock(ok=True, json=lambda: {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]})
    result = analyze_evidence("secret", "question", [{"title":"T", "url":"https://example.org", "snippet":"Evidence"}])
    assert result["findings"][0]["status"] == "needs human review"
    assert result["findings"][0]["source_urls"] == []


@patch("research_lab.gemini.time.sleep")
@patch("research_lab.gemini.requests.post")
def test_gemini_retries_temporary_503_then_succeeds(mock_post, _sleep):
    ok = Mock(ok=True, json=lambda: {"candidates": [{"content": {"parts": [{"text": '{"summary":"ok","findings":[],"gaps":[]}'}]}}]})
    mock_post.side_effect = [Mock(status_code=503), ok]
    result = analyze_evidence("secret", "question", [], retries=1)
    assert result["summary"] == "ok"
    assert mock_post.call_count == 2
