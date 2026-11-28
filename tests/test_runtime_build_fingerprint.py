import os

import pytest

from services.coworker.runtime_identity import compute_build_digest


@pytest.fixture
def build(tmp_path):
    (tmp_path / 'pyproject.toml').write_text('[project]\nname="example"\n', encoding='utf-8')
    (tmp_path / 'uv.lock').write_text('version = 1\n', encoding='utf-8')
    return dict(root=tmp_path, source_revision='a'*40,
                distributions=[('Foo_Bar', '1.0'), ('Baz', '2.0')],
                python_implementation='CPython', python_version='3.11.9',
                platform_identity='linux-x86_64')


def test_deterministic_and_normalized(build):
    digest = compute_build_digest(**build)
    assert len(digest) == 64
    assert digest == compute_build_digest(**{**build, 'distributions': [('baz', '2.0'), ('foo-bar', '1.0')]})


@pytest.mark.parametrize('field,value', [('source_revision', 'b'*40), ('python_version', '3.11.10'),
                                       ('platform_identity', 'linux-aarch64'), ('python_implementation', 'PyPy'),
                                       ('distributions', [('Foo_Bar', '1.1'), ('Baz', '2.0')])])
def test_changes_bind_identity(build, field, value):
    assert compute_build_digest(**build) != compute_build_digest(**{**build, field: value})


@pytest.mark.parametrize('filename', ['pyproject.toml', 'uv.lock'])
def test_file_contents_bind_identity(build, filename):
    digest = compute_build_digest(**build)
    (build['root'] / filename).write_bytes(b'changed\n')
    assert compute_build_digest(**build) != digest


@pytest.mark.parametrize('kind', ['symlink', 'fifo', 'missing', 'directory'])
def test_nonregular_inputs_rejected(build, kind):
    lock = build['root'] / 'uv.lock'
    lock.unlink()
    if kind == 'symlink':
        lock.symlink_to(build['root'] / 'pyproject.toml')
    elif kind == 'fifo':
        os.mkfifo(lock)
    elif kind == 'directory':
        lock.mkdir()
    with pytest.raises(ValueError, match='build input|regular|symlink'):
        compute_build_digest(**build)


@pytest.mark.parametrize('inventory', [[('foo', '1'), ('Foo', '2')], [('foo', '')], [('foo\nbar', '1')]])
def test_ambiguous_distribution_metadata_rejected(build, inventory):
    with pytest.raises(ValueError, match='distribution'):
        compute_build_digest(**{**build, 'distributions': inventory})


def test_invalid_source_revision(build):
    with pytest.raises(ValueError, match='source revision'):
        compute_build_digest(**{**build, 'source_revision': 'main'})


def test_runtime_identity_changes_when_schema_model_queue_or_reviewed_skill_changes(build):
    from services.coworker.runtime_identity import build_runtime_identity, canonical_sha256

    # Synthetic settings implement only the runtime identity interface.
    class Settings:
        def __getattr__(self, name):
            if name.endswith('_enabled') or name == 'chat_provider_configured':
                return False
            raise AttributeError(name)
        source_revision = 'a'*40
        environment = 'staging'
        chat_provider = 'deepseek'
        deepseek_model = 'deepseek-flash'
        gemma_model = 'gemma-test'
        task_queue = 'shuddho-documents-v1'
        cohort_enforced = True
        cohort_account_ids = {'synthetic-owner-a'}
        cohort_max_users = 5

    class Repository:
        schema = '0073_worker_runtime_identity'
        skill = {'research': {'state': 'unselected'}}
        reads = 0
        def current_schema_revision(self):
            return self.schema
        def reviewed_skill_runtime_manifest(self):
            self.reads += 1
            return self.skill.copy()

    settings = Settings()
    repo = Repository()
    args = {k: v for k, v in build.items() if k != 'source_revision'}
    first = build_runtime_identity(settings, repo, **args)
    assert repo.reads == 1
    assert first['runtime_identity_sha256'] == canonical_sha256({k: v for k, v in first.items() if k != 'runtime_identity_sha256'})
    assert len(first['capabilities']) == 44
    assert 'synthetic-owner-a' not in repr(first)
    assert first['schema_version'] == 3
    for name, value in [('deepseek_model', 'other-model'), ('task_queue', 'other-queue'), ('suggestion_model_relevance_enabled', True), ('work_services_enabled', True)]:
        setattr(settings, name, value)
        assert first['runtime_identity_sha256'] != build_runtime_identity(settings, repo, **args)['runtime_identity_sha256']
        delattr(settings, name)
    repo.schema = 'other-revision'
    assert first['runtime_identity_sha256'] != build_runtime_identity(settings, repo, **args)['runtime_identity_sha256']
    repo.schema = '0073_worker_runtime_identity'
    repo.skill = {'research': {'state': 'selected'}}
    assert first['runtime_identity_sha256'] != build_runtime_identity(settings, repo, **args)['runtime_identity_sha256']
    settings.chat_provider = 'auto'
    with pytest.raises(ValueError, match='provider'):
        build_runtime_identity(settings, repo, **args)


def test_fleet_readiness_rejects_uncertain_stale_or_mismatched_workers():
    from services.coworker.runtime_identity import qualify_worker_inventory
    identity = dict(task_queue='queue', source_revision='a'*40, build_digest='b'*64,
                    schema_revision='0073_worker_runtime_identity', model_provider='deepseek',
                    model_id='deepseek-flash', runtime_identity_sha256='c'*64)
    worker = {**identity, 'state': 'running', 'heartbeat_fresh': True,
              'active_claim_count': 0, 'id': 'secret-worker-id', 'drained_at': None}
    result = qualify_worker_inventory(identity, [worker])
    assert result['worker_fleet_ready'] is True
    assert result['worker_inventory'] == [identity]
    assert 'secret-worker-id' not in repr(result)
    for delta in ({'build_digest': 'f'*64}, {'heartbeat_fresh': False}, {'state': 'lost'},
                  {'state': 'draining'}, {'state': 'starting'}, {'build_digest': None},
                  {'state': 'drained', 'drained_at': None}):
        assert not qualify_worker_inventory(identity, [worker, {**worker, **delta}])['worker_fleet_ready']
    assert not qualify_worker_inventory(identity, [])['worker_fleet_ready']
    assert qualify_worker_inventory(identity, [worker, {**worker, 'state': 'drained', 'drained_at': 'observed'}])['worker_fleet_ready']
    assert not qualify_worker_inventory(identity, [worker, {**worker, 'state': 'drained', 'drained_at': 'observed', 'active_claim_count': 1}])['worker_fleet_ready']
