#!/usr/bin/env python3
"""
Fix deprecated datetime.now(timezone.utc) calls (Python 3.14+).

Replaces all instances of datetime.now(timezone.utc) with datetime.now(timezone.utc).
Also ensures proper imports are present.
"""

import re
from pathlib import Path


def fix_file(file_path: Path) -> tuple[bool, str]:
    """
    Fix datetime.now(timezone.utc) in a single file.

    Returns:
        (changed, message)
    """
    content = file_path.read_text(encoding='utf-8')
    original = content

    # Check if file uses datetime.now(timezone.utc)
    if 'datetime.now(timezone.utc)' not in content and 'datetime.datetime.now(timezone.utc)' not in content:
        return False, "No deprecated calls found"

    # Replace datetime.now(timezone.utc) -> datetime.now(timezone.utc)
    content = content.replace('datetime.now(timezone.utc)', 'datetime.now(timezone.utc)')

    # Replace datetime.datetime.now(timezone.utc) -> datetime.datetime.now(datetime.timezone.utc)
    content = content.replace('datetime.datetime.now(timezone.utc)', 'datetime.datetime.now(datetime.timezone.utc)')

    # Ensure timezone import
    if 'datetime.now(timezone.utc)' in content or 'datetime.now(datetime.timezone.utc)' in content:
        # Check if timezone is imported
        has_timezone_import = bool(re.search(r'from datetime import.*\btimezone\b', content))
        has_datetime_import = bool(re.search(r'from datetime import.*\bdatetime\b', content))
        has_import_datetime = bool(re.search(r'^import datetime', content, re.MULTILINE))

        if 'datetime.now(timezone.utc)' in content and not has_timezone_import:
            # Need to add timezone import
            if has_datetime_import:
                # Add timezone to existing from datetime import
                content = re.sub(
                    r'(from datetime import [^;\n]+)',
                    lambda m: m.group(1) + ', timezone' if 'timezone' not in m.group(1) else m.group(1),
                    content,
                    count=1
                )
            else:
                # Add new from datetime import
                lines = content.split('\n')
                insert_idx = 0
                for i, line in enumerate(lines):
                    if line.startswith('import ') or line.startswith('from '):
                        insert_idx = i + 1
                    elif line and not line.startswith('#'):
                        break

                lines.insert(insert_idx, 'from datetime import timezone')
                content = '\n'.join(lines)

    if content != original:
        file_path.write_text(content, encoding='utf-8')
        count = original.count('datetime.now(timezone.utc)') + original.count('datetime.datetime.now(timezone.utc)')
        return True, f"Fixed {count} occurrences"

    return False, "No changes needed"


def main():
    """Fix all Python files in backend."""
    backend_dir = Path(__file__).parent.parent

    # Find all Python files
    python_files = list(backend_dir.rglob('*.py'))

    # Exclude virtual environment and migrations
    python_files = [
        f for f in python_files
        if '.venv' not in str(f) and '__pycache__' not in str(f) and 'alembic/versions' not in str(f)
    ]

    print(f"[*] Scanning {len(python_files)} Python files...")
    print()

    changed_files = []
    unchanged_files = []

    for file_path in python_files:
        try:
            changed, message = fix_file(file_path)
            if changed:
                relative_path = file_path.relative_to(backend_dir)
                print(f"[+] {relative_path}: {message}")
                changed_files.append(file_path)
            else:
                unchanged_files.append(file_path)
        except Exception as e:
            print(f"[-] Error processing {file_path}: {e}")

    print()
    print(f"[SUMMARY]")
    print(f"   Changed: {len(changed_files)} files")
    print(f"   Unchanged: {len(unchanged_files)} files")

    if changed_files:
        print()
        print("[OK] All deprecated datetime.now(timezone.utc) calls have been fixed!")
        print("     Replaced with: datetime.now(timezone.utc)")
    else:
        print()
        print("[OK] No deprecated datetime.now(timezone.utc) calls found!")


if __name__ == '__main__':
    main()
