"""The re-chunk tool rewrites production passages, so its safety properties are pinned.

The chunker bug left six passages between 50k and 149,579 characters. The text is already in the row,
so no re-upload is needed: this splits them in place.
"""
import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.models import Base, Passage

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "rechunk_oversized_passages.py"


def _load():
    spec = importlib.util.spec_from_file_location("rechunk_oversized_passages", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["rechunk_oversized_passages"] = module
    spec.loader.exec_module(module)
    return module


async def _seed(url: str) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker.begin() as session:
        # the production shape: one paragraph, no blank lines, far past the window
        session.add(Passage(id="big1", tenant_id="acme", agent_id="a1", doc_id="Tender.pdf",
                            text="clause " * 8_000, embedding=[0.1] * 4))
        session.add(Passage(id="small1", tenant_id="acme", agent_id="a1", doc_id="Tender.pdf",
                            text="a short and perfectly fine chunk", embedding=[0.2] * 4))
        session.add(Passage(id="big2", tenant_id="other", agent_id="a9", doc_id="Other.pdf",
                            text="text " * 6_000, embedding=[0.3] * 4))
    await engine.dispose()


async def _rows(url: str) -> list[tuple]:
    engine = create_async_engine(url)
    sessionmaker = async_sessionmaker(engine)
    async with sessionmaker() as session:
        rows = (await session.execute(select(
            Passage.id, Passage.tenant_id, Passage.agent_id, Passage.doc_id,
            func.length(Passage.text)))).all()
    await engine.dispose()
    return rows


@pytest.fixture
def db(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path / 'rechunk.db'}"
    monkeypatch.setattr(get_settings(), "database_url", url)
    asyncio.run(_seed(url))
    return _load(), url


def test_dry_run_reports_the_plan_and_writes_nothing(db, capsys):
    module, url = db
    assert module.main(["--threshold", "2000"]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "oversized passages: 2" in out
    assert {row[0] for row in asyncio.run(_rows(url))} == {"big1", "small1", "big2"}


def test_apply_replaces_only_the_oversized_rows(db):
    module, url = db
    assert module.main(["--apply", "--threshold", "2000"]) == 0
    rows = asyncio.run(_rows(url))
    ids = {row[0] for row in rows}
    assert "big1" not in ids and "big2" not in ids, "the oversized originals must be gone"
    assert "small1" in ids, "a passage that was already fine must be untouched"
    assert len(rows) > 50, "the oversized text became many chunks"
    assert max(row[4] for row in rows) <= 900, "every remaining passage is within the window"


def test_ownership_and_document_identity_are_preserved(db):
    """Citations key on doc_id, so a re-chunk must not change it, the tenant or the worker."""
    module, url = db
    module.main(["--apply", "--threshold", "2000"])
    rows = asyncio.run(_rows(url))
    for _pid, tenant, agent, doc_id, _size in rows:
        assert (tenant, agent, doc_id) in {("acme", "a1", "Tender.pdf"), ("other", "a9", "Other.pdf")}
    assert {row[1] for row in rows} == {"acme", "other"}, "no tenant lost its content"


def test_tenant_scoping_leaves_the_other_tenant_alone(db):
    module, url = db
    module.main(["--apply", "--tenant", "acme", "--threshold", "2000"])
    rows = asyncio.run(_rows(url))
    assert "big2" in {row[0] for row in rows}, "the other tenant must not be rewritten"
    assert "big1" not in {row[0] for row in rows}


def test_a_second_run_finds_nothing_and_changes_nothing(db, capsys):
    module, url = db
    module.main(["--apply", "--threshold", "2000"])
    before = sorted(asyncio.run(_rows(url)))
    capsys.readouterr()
    assert module.main(["--apply", "--threshold", "2000"]) == 0
    assert "nothing above the threshold" in capsys.readouterr().out
    assert sorted(asyncio.run(_rows(url))) == before


def test_child_ids_are_deterministic():
    """So a re-run cannot duplicate content, and an id can be traced back to what it came from."""
    module = _load()
    first = [module._part_id("big1", index) for index in range(3)]
    assert first == [module._part_id("big1", index) for index in range(3)]
    assert len(set(first)) == 3
    assert first != [module._part_id("big2", index) for index in range(3)]


def test_no_content_is_lost_across_the_replacement(db):
    module, url = db
    module.main(["--apply", "--threshold", "2000"])

    async def read_text() -> str:
        engine = create_async_engine(url)
        sessionmaker = async_sessionmaker(engine)
        async with sessionmaker() as session:
            texts = (await session.execute(
                select(Passage.text).where(Passage.doc_id == "Tender.pdf"))).scalars().all()
        await engine.dispose()
        return " ".join(texts)

    joined = asyncio.run(read_text())
    assert "clause" in joined
    assert "a short and perfectly fine chunk" in joined
