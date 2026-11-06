"""Restore the verified original analyzer from local Git objects, keeping a backup."""
import ast
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_BLOB = '1cd749395a917ef1df6ab4806d590880ce18a4c1'


def repair(root=ROOT):
    # Git object ID identifies the original reviewed file, not a moving branch.
    result = subprocess.run(['git', 'cat-file', 'blob', ORIGINAL_BLOB], cwd=root,
                            check=True, capture_output=True)
    content = result.stdout
    header = f'blob {len(content)}\0'.encode()
    if hashlib.sha1(header + content).hexdigest() != ORIGINAL_BLOB:
        raise RuntimeError('Original analyzer integrity check failed')
    ast.parse(content.decode('utf-8-sig'))
    target = root / 'pose_exercise_analyzer.py'
    if target.exists():
        current = target.read_bytes()
        if current.replace(b'\r\n', b'\n') == content.replace(b'\r\n', b'\n'):
            print('Analyzer already matches the verified original; no changes made.')
            return
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
        backup = target.with_name(f'{target.name}.backup-{stamp}')
        backup.write_bytes(current)
        print(f'Preserved your previous analyzer: {backup}')
    temporary = target.with_suffix('.py.repairing')
    temporary.write_bytes(content)
    temporary.replace(target)
    print(f'Restored verified analyzer: {target}')

if __name__ == '__main__':
    repair()
