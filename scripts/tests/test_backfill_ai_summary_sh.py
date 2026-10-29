import os
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'backfill_ai_summary.sh'
REPO_ROOT = SCRIPT.parents[1]


@pytest.fixture
def fake_docker(tmp_path):
    """以假的 docker 指令記錄收到的參數與工作目錄，不真的呼叫 docker"""
    log = tmp_path / 'docker_args.txt'
    docker = tmp_path / 'docker'
    docker.write_text(f'#!/usr/bin/env bash\necho "$PWD" > "{log}"\nprintf "%s\\n" "$@" >> "{log}"\n')
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    return tmp_path, log


def _run(fake_docker, *args, cwd=None, env_extra=None):
    bin_dir, log = fake_docker
    env = {**os.environ, 'PATH': f'{bin_dir}:{os.environ["PATH"]}', **(env_extra or {})}
    result = subprocess.run(['bash', str(SCRIPT), *args], cwd=cwd or bin_dir, env=env, capture_output=True, text=True)
    lines = log.read_text().splitlines() if log.exists() else []
    return result, lines


def test_script_is_executable():
    assert os.access(SCRIPT, os.X_OK)


def test_runs_command_in_web_container_from_repo_root(fake_docker):
    """從任意目錄執行都會切到 repo 根目錄，並在 web container 內執行 command"""
    result, lines = _run(fake_docker)

    assert result.returncode == 0
    assert Path(lines[0]).resolve() == REPO_ROOT
    assert lines[1:] == [
        'compose', 'exec', '-T', 'web',
        'uv', 'run', '--no-sync', 'python', 'manage.py', 'backfill_ai_summary',
    ]


def test_passes_arguments_through_unchanged(fake_docker):
    """參數原樣傳給 command（含有空白的參數不被拆開）"""
    _, lines = _run(fake_docker, '--dry-run', '--limit', '20', '--note', 'a b')

    assert lines[-5:] == ['--dry-run', '--limit', '20', '--note', 'a b']


def test_service_name_overridable(fake_docker):
    """可用 BACKFILL_SERVICE 環境變數指定 compose service"""
    _, lines = _run(fake_docker, env_extra={'BACKFILL_SERVICE': 'celery'})

    assert lines[4] == 'celery'


def test_propagates_failure_exit_code(fake_docker, tmp_path):
    """command 失敗時 script 以非 0 結束"""
    bin_dir, _ = fake_docker
    (bin_dir / 'docker').write_text('#!/usr/bin/env bash\nexit 3\n')

    result, _ = _run(fake_docker)

    assert result.returncode == 3
