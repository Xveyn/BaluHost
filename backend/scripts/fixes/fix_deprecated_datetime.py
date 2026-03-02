#!/usr/bin/env python3
"""
Fix deprecated datetime.utcnow() calls (deprecated since Python 3.12).

Replaces all instances of datetime.utcnow() with datetime.now(timezone.utc).
Also ensures proper imports are present.

Usage:
    python scripts/fixes/fix_deprecated_datetime.py
"""

import re
from pathlib import Path

# Use variable to avoid self-modification
_DEPRECATED = "datetime." + "utcnow()"
_REPLACEMENT = "datetime.now(timezone.utc)"


def fix_file(file_path: Path) -> tuple[bool, str]:
    """
    Fix deprecated datetime.utcnow() in a single file.

    Returns:
        (changed, message)
    """
    content = file_path.read_text(encoding='utf-8')
    original = content

    if _DEPRECATED not in content:
        return False, "No deprecated calls found"

    count = content.count(_DEPRECATED)

    # Replace deprecated call with timezone-aware alternative
    content = content.replace(_DEPRECATED, _REPLACEMENT)

    # Ensure timezone import exists
    has_timezone_import = bool(re.search(r'from datetime import.*\btimezone\b', content))

    if not has_timezone_import:
        has_datetime_import = bool(re.search(r'from datetime import\s', content))

        if has_datetime_import:
            # Add timezone to existing 'from datetime import ...' line
            content = re.sub(
                r'(from datetime import [^;\n]+)',
                lambda m: m.group(1) + ', timezone' if 'timezone' not in m.group(1) else m.group(1),
                content,
                count=1
            )
        else:
            # Add new import line after existing imports
            lines = content.split('\n')
            insert_idx = 0
            for i, line in enumerate(lines):
                if line.startswith('import ') or line.startswith('from '):
                    insert_idx = i + 1
                elif line and not line.startswith('#') and not line.startswith('"""') and insert_idx > 0:
                    break
            lines.insert(insert_idx, 'from datetime import timezone')
            content = '\n'.join(lines)

    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True, f"Fixed {count} occurrence(s)"

    return False, "No changes needed"


def main():
    """Fix all Python files in backend."""
    backend_dir = Path(__file__).parent.parent.parent

    python_files = list(backend_dir.rglob('*.py'))

    # Exclude virtual environment, __pycache__, and alembic migrations
    python_files = [
        f for f in python_files
        if '.venv' not in str(f)
        and '__pycache__' not in str(f)
        and 'alembic/versions' not in str(f)
    ]

    print(f"[*] Scanning {len(python_files)} Python files...")
    print()

    changed_files = []

    for file_path in sorted(python_files):
        try:
            changed, message = fix_file(file_path)
            if changed:
                relative_path = file_path.relative_to(backend_dir)
                print(f"  [+] {relative_path}: {message}")
                changed_files.append(file_path)
        except Exception as e:
            print(f"  [-] Error processing {file_path}: {e}")

    print()
    print(f"[SUMMARY] Changed: {len(changed_files)} files")

    if not changed_files:
        print("[OK] No deprecated calls found!")


if __name__ == '__main__':
    main()
