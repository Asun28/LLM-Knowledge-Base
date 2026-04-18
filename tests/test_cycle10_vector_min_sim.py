from kb.query.embeddings import _vec_db_path
from kb.query.engine import search_pages


class FakeVectorIndex:
    def __init__(self, hits):
        self.hits = hits

    def query(self, _vec, limit):
        return self.hits[:limit]


def _enable_fake_vector_index(tmp_wiki, monkeypatch, hits):
    vec_path = _vec_db_path(tmp_wiki)
    vec_path.parent.mkdir(parents=True, exist_ok=True)
    vec_path.touch()

    monkeypatch.setattr("kb.query.embeddings.embed_texts", lambda _texts: [[0.1, 0.2]])
    monkeypatch.setattr(
        "kb.query.embeddings.get_vector_index",
        lambda _path: FakeVectorIndex(hits),
    )


def test_search_pages_filters_low_cosine_vector_hits(tmp_wiki, create_wiki_page, monkeypatch):
    create_wiki_page(
        "concepts/page-high",
        title="High Alpha",
        content="unrelated alpha body",
        wiki_dir=tmp_wiki,
    )
    create_wiki_page(
        "concepts/page-low",
        title="Low Beta",
        content="unrelated beta body",
        wiki_dir=tmp_wiki,
    )
    _enable_fake_vector_index(
        tmp_wiki,
        monkeypatch,
        [("concepts/page-high", 1.0), ("concepts/page-low", 3.0)],
    )

    results = search_pages("test query", max_results=10, wiki_dir=tmp_wiki)

    assert [result["id"] for result in results] == ["concepts/page-high"]


def test_search_pages_returns_empty_when_bm25_empty_and_all_vec_below_threshold(
    tmp_wiki, create_wiki_page, monkeypatch
):
    create_wiki_page(
        "concepts/page-a",
        title="Alpha",
        content="unrelated alpha body",
        wiki_dir=tmp_wiki,
    )
    create_wiki_page(
        "concepts/page-b",
        title="Beta",
        content="unrelated beta body",
        wiki_dir=tmp_wiki,
    )
    _enable_fake_vector_index(
        tmp_wiki,
        monkeypatch,
        [("concepts/page-a", 3.0), ("concepts/page-b", 4.0)],
    )

    results = search_pages("noise query", max_results=10, wiki_dir=tmp_wiki)

    assert results == []
