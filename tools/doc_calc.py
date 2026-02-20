#!/usr/bin/env python3
"""
BaluHost LOC (Lines of Code) Calculator
Analyzes code across all project components and saves results to JSON.
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Tuple

# Define components and their paths
COMPONENTS = {
    "BaluHost Backend (FastAPI)": {
        "path": "backend",
        "extensions": [".py"],
        "exclude_dirs": ["__pycache__", "alembic", "dev-storage", "dev-tmp", 
                        "storage", "tmp", "tests", "benchmark_results", 
                        "dev-backups", ".pytest_cache", "baluhost_backend.egg-info",
                        ".venv", "venv", "env", ".env", "site-packages", "Lib"]
    },
    "BaluHost Frontend (React)": {
        "path": "client",
        "extensions": [".ts", ".tsx", ".js", ".jsx"],
        "exclude_dirs": ["node_modules", "dist", "build", ".vite", "coverage"]
    },
    "Android App": {
        "path": "android-app",
        "extensions": [".kt", ".java", ".xml"],
        "exclude_dirs": ["build", "gradle", ".gradle", ".idea", "generated"]
    },
    "TUI (Terminal UI)": {
        "path": "backend/baluhost_tui",
        "extensions": [".py"],
        "exclude_dirs": ["__pycache__"]
    },
    "BaluDesk Backend (C++)": {
        "path": "baludesk/backend",
        "extensions": [".cpp", ".h", ".hpp"],
        "exclude_dirs": ["build", "cmake-build-debug", "cmake-build-release"]
    },
    "BaluDesk Frontend (Electron)": {
        "path": "baludesk/frontend",
        "extensions": [".ts", ".tsx", ".js", ".jsx"],
        "exclude_dirs": ["node_modules", "dist", "build", "out"]
    },
    "Scripts & Tools": {
        "path": "scripts",
        "extensions": [".py", ".sh", ".ps1"],
        "exclude_dirs": []
    }
}


def count_lines(file_path: Path) -> Tuple[int, int, int]:
    """
    Count lines in a file.
    Returns: (total_lines, code_lines, comment_lines)
    """
    total_lines = 0
    code_lines = 0
    comment_lines = 0
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                total_lines += 1
                stripped = line.strip()
                
                if not stripped:
                    continue
                    
                # Check for comments
                if stripped.startswith('#') or stripped.startswith('//') or \
                   stripped.startswith('/*') or stripped.startswith('*') or \
                   stripped.startswith('<!--'):
                    comment_lines += 1
                else:
                    code_lines += 1
                    
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        
    return total_lines, code_lines, comment_lines


def analyze_component(name: str, config: Dict, base_path: Path) -> Dict:
    """Analyze a single component and return statistics."""
    component_path = base_path / config["path"]
    
    if not component_path.exists():
        print(f"Warning: {name} path not found: {component_path}")
        return {
            "name": name,
            "path": config["path"],
            "files": 0,
            "total_lines": 0,
            "code_lines": 0,
            "comment_lines": 0,
            "extensions": config["extensions"]
        }
    
    total_files = 0
    total_lines = 0
    code_lines = 0
    comment_lines = 0
    file_list = []
    
    for ext in config["extensions"]:
        for file_path in component_path.rglob(f"*{ext}"):
            # Skip excluded directories
            if any(excluded in file_path.parts for excluded in config["exclude_dirs"]):
                continue
                
            t, c, cm = count_lines(file_path)
            total_files += 1
            total_lines += t
            code_lines += c
            comment_lines += cm
            
            file_list.append({
                "file": str(file_path.relative_to(base_path)),
                "lines": t
            })
    
    # Sort files by line count
    file_list.sort(key=lambda x: x["lines"], reverse=True)
    
    return {
        "name": name,
        "path": config["path"],
        "files": total_files,
        "total_lines": total_lines,
        "code_lines": code_lines,
        "comment_lines": comment_lines,
        "blank_lines": total_lines - code_lines - comment_lines,
        "extensions": config["extensions"],
        "top_files": file_list[:10]  # Top 10 largest files
    }


def main():
    """Main execution function."""
    base_path = Path(__file__).parent.parent
    
    print("🔍 BaluHost LOC Analysis")
    print("=" * 60)
    
    results = {
        "project": "BaluHost",
        "timestamp": __import__('datetime').datetime.now().isoformat(),
        "base_path": str(base_path),
        "components": [],
        "totals": {
            "files": 0,
            "total_lines": 0,
            "code_lines": 0,
            "comment_lines": 0,
            "blank_lines": 0
        }
    }
    
    for name, config in COMPONENTS.items():
        print(f"\n📂 Analyzing: {name}")
        component_data = analyze_component(name, config, base_path)
        results["components"].append(component_data)
        
        # Update totals
        results["totals"]["files"] += component_data["files"]
        results["totals"]["total_lines"] += component_data["total_lines"]
        results["totals"]["code_lines"] += component_data["code_lines"]
        results["totals"]["comment_lines"] += component_data["comment_lines"]
        results["totals"]["blank_lines"] += component_data.get("blank_lines", 0)
        
        print(f"  ✓ Files: {component_data['files']:,}")
        print(f"  ✓ Total Lines: {component_data['total_lines']:,}")
        print(f"  ✓ Code Lines: {component_data['code_lines']:,}")
    
    # Save to JSON
    output_file = base_path / "documentation_loc.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 60)
    print("📊 TOTAL PROJECT STATISTICS")
    print("=" * 60)
    print(f"Total Files: {results['totals']['files']:,}")
    print(f"Total Lines: {results['totals']['total_lines']:,}")
    print(f"Code Lines: {results['totals']['code_lines']:,}")
    print(f"Comment Lines: {results['totals']['comment_lines']:,}")
    print(f"Blank Lines: {results['totals']['blank_lines']:,}")
    print(f"\n✅ Results saved to: {output_file}")


if __name__ == "__main__":
    main()
