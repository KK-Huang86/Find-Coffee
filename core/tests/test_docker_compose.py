from pathlib import Path

import pytest
import yaml

COMPOSE_PATH = Path(__file__).resolve().parents[2] / 'docker-compose.yml'


@pytest.fixture(scope='module')
def compose():
    return yaml.safe_load(COMPOSE_PATH.read_text())


def _env_to_dict(environment):
    """compose 的 environment 可寫成 list（KEY=VALUE）或 dict，統一轉成 dict。"""
    if isinstance(environment, dict):
        return {key: str(value) for key, value in environment.items()}
    return dict(item.split('=', 1) for item in environment)


class TestAppContainerDbConnection:
    @pytest.mark.parametrize('service', ['web', 'celery'])
    def test_connects_to_pgbouncer_host(self, compose, service):
        env = _env_to_dict(compose['services'][service]['environment'])
        assert env['DB_HOST'] == 'pgbouncer'

    @pytest.mark.parametrize('service', ['web', 'celery'])
    def test_db_port_pinned_to_pgbouncer_internal_port(self, compose, service):
        # .env 的 DB_PORT 供本機使用（5433），容器必須以 environment 覆蓋為 5432
        env = _env_to_dict(compose['services'][service]['environment'])
        assert env.get('DB_PORT') == '5432'

    @pytest.mark.parametrize('service', ['web', 'celery'])
    def test_env_file_still_loaded(self, compose, service):
        # environment 覆蓋 env_file 的前提是 .env 仍被載入；確保覆蓋關係存在
        assert '.env' in compose['services'][service]['env_file']


class TestDbHostPortMapping:
    def test_db_exposed_to_host_on_5433(self, compose):
        assert '5433:5432' in compose['services']['db']['ports']

    def test_db_not_exposed_on_host_5432(self, compose):
        # host 5432 可能被開發者本機其他 PostgreSQL 佔用
        host_ports = [str(mapping).split(':')[0] for mapping in compose['services']['db']['ports']]
        assert '5432' not in host_ports
