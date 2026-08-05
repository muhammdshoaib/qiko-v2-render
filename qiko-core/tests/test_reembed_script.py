"""The re-embed tool is an operational script that rewrites production vectors, so its safety
properties (dry run writes nothing, tenant scoping holds, text is never touched, re-runs are
idempotent) are worth pinning down."""
import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.models import Base, Passage

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "reembed_passages.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("reembed_passages", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["reembed_passages"] = module
    spec.loader.exec_module(module)
    return module


async def _seed(url: str) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker.begin() as session:
        for index in range(3):
            session.add(Passage(id=f"p{index}", tenant_id="acme", agent_id="a1", doc_id="d1",
                                text=f"chunk {index}", embedding=[0.0, 0.0]))  # stale, wrong dim
        session.add(Passage(id="p9", tenant_id="other", agent_id="a1", doc_id="d1",
                            text="other tenant", embedding=[0.0, 0.0]))
    await engine.dispose()


async def _dims(url: str) -> dict[str, int]:
    engine = create_async_engine(url)
    sessionmaker = async_sessionmaker(engine)
    async with sessionmaker() as session:
        rows = (await session.execute(select(Passage))).scalars().all()
        out = {row.id: len(row.embedding or []) for row in rows}
        texts = {row.id: row.text for row in rows}
    await engine.dispose()
    return out, texts


@pytest.fixture
def script_env(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path / 'reembed.db'}"
    monkeypatch.setattr(get_settings(), "database_url", url)
    asyncio.run(_seed(url))
    return _load_script(), url


def test_dry_run_reports_but_writes_nothing(script_env, capsys):
    module, url = script_env
    argv = module.argparse.Namespace(apply=False, tenant=None, batch_size=10)
    assert asyncio.run(module._run(argv)) == 0
    assert "DRY RUN" in capsys.readouterr().out
    dims, _ = asyncio.run(_dims(url))
    assert set(dims.values()) == {2}  # untouched


def test_apply_rebuilds_only_the_named_tenant_and_never_touches_text(script_env):
    module, url = script_env
    before_dims, before_texts = asyncio.run(_dims(url))
    argv = module.argparse.Namespace(apply=True, tenant="acme", batch_size=2)
    assert asyncio.run(module._run(argv)) == 0

    dims, texts = asyncio.run(_dims(url))
    expected = get_settings().embeddings_dim
    assert dims["p0"] == dims["p1"] == dims["p2"] == expected
    assert dims["p9"] == 2, "the other tenant's vectors must not be rewritten"
    assert texts == before_texts, "passage text must never change"
    assert before_dims["p0"] == 2


def test_apply_is_idempotent(script_env, capsys):
    module, url = script_env
    argv = module.argparse.Namespace(apply=True, tenant="acme", batch_size=10)
    asyncio.run(module._run(argv))
    capsys.readouterr()
    asyncio.run(module._run(argv))
    assert "0 rewritten" in capsys.readouterr().out
