"""Fast, model-free checks shared by server startup and the launcher."""
import ast
from pathlib import Path
from reference_comparison import load_profile

ROOT = Path(__file__).resolve().parent


def check_sources(root=ROOT):
    for name in ('pose_exercise_analyzer.py', 'reference_comparison.py', 'server.py', 'session_report.py'):
        path = root / name
        try:
            ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
        except SyntaxError as exc:
            raise RuntimeError(
                f'{name}:{exc.lineno}: {exc.msg}. '
                'If the analyzer was edited accidentally, run python scripts/repair_analyzer.py.'
            ) from exc
    load_profile(root / 'reference' / 'pushup_profile.json')
