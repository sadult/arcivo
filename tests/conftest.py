from __future__ import annotations

import pytest

from arcivo.context import AppContext
from arcivo.core.paths import AppPaths
from arcivo.sample_data import generate
from arcivo.telegram.fake import FakeGateway


@pytest.fixture
def paths(tmp_path):
    return AppPaths(config_dir=tmp_path / "config", data_dir=tmp_path / "data", portable=True).ensure()


@pytest.fixture
def records():
    return generate(600, seed=3)


@pytest.fixture
def gateway(records):
    return FakeGateway(records)


@pytest.fixture
def ctx(paths, gateway):
    c = AppContext(paths, gateway=gateway, configure_logging=False)
    c.config.settings.sync.request_delay_s = 0
    c.deleter.batch_delay = 0
    yield c
    c.db.close()


@pytest.fixture
async def synced(ctx):
    await ctx.sync.sync("initial")
    return ctx
