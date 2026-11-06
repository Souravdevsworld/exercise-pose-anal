import ast
from pathlib import Path
import subprocess
import pytest
from preflight import check_sources
from scripts.repair_analyzer import repair

ROOT = Path(__file__).resolve().parents[1]


def test_actual_sources_and_reference_are_valid():
    check_sources()


def test_broken_analyzer_fails_before_serving(tmp_path):
    (tmp_path / 'pose_exercise_analyzer.py').write_text('result = dict(log=)')
    with pytest.raises(RuntimeError, match='pose_exercise_analyzer.py:1'):
        check_sources(tmp_path)


def test_repair_preserves_broken_file(tmp_path):
    subprocess.run(['git','init',str(tmp_path)], check=True, capture_output=True)
    content = (ROOT / 'pose_exercise_analyzer.py').read_bytes()
    subprocess.run(['git','hash-object','-w','--stdin'], input=content, cwd=tmp_path,
                   check=True, capture_output=True)
    target = tmp_path / 'pose_exercise_analyzer.py'
    broken = b'result = dict(log=)\n'
    target.write_bytes(broken)
    repair(tmp_path)
    assert target.read_bytes() == content
    assert next(tmp_path.glob('*.backup-*')).read_bytes() == broken
    ast.parse(target.read_text())
    repair(tmp_path)
    assert len(list(tmp_path.glob('*.backup-*'))) == 1
