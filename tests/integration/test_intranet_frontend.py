from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_intranet_mode_serves_spa_without_masking_api_404(tmp_path, fake_registry):
    data_root = tmp_path / "data"
    frontend_dist = tmp_path / "frontend-dist"
    (frontend_dist / "assets").mkdir(parents=True)
    (frontend_dist / "index.html").write_text("<div id=\"root\">app</div>", encoding="utf-8")
    (frontend_dist / "assets" / "app.js").write_text("console.log('app')", encoding="utf-8")
    settings = Settings(
        data_root=data_root,
        raw_root=data_root / "raw",
        staging_root=data_root / "staging",
        hierarchical_index_root=data_root / "indexes-hierarchical",
        fixture_root=data_root / "fixtures",
        metadata_database_url=(
            f"sqlite+aiosqlite:///{(data_root / 'metadata' / 'knowledge.db').as_posix()}"
        ),
        serve_frontend=True,
        frontend_dist_dir=frontend_dist,
        llm_base_url="",
        llm_api_key="",
        llm_model="",
        web_search_enabled=False,
    )

    with TestClient(create_app(settings, tree_index_registry=fake_registry)) as client:
        assert client.get("/").text == '<div id="root">app</div>'
        assert client.get("/knowledge").text == '<div id="root">app</div>'
        assert client.get("/assets/app.js").text == "console.log('app')"

        api_not_found = client.get("/api/v1/not-a-route")
        assert api_not_found.status_code == 404
        assert api_not_found.json()["code"] == "NOT_FOUND"
