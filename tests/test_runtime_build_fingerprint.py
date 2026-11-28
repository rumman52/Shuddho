from pathlib import Path
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
