import os
import re
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

console = Console()


def validate_booth_id(booth_id: str) -> Tuple[bool, str]:
    pattern = r'^[A-Z]{1,3}-\d{3,4}$'
    if not re.match(pattern, booth_id):
        return False, "展位编号格式错误，应为 字母-数字 格式，如 A-001 或 AB-1001"
    return True, "格式正确"


def get_booth_zone(booth_id: str) -> str:
    match = re.match(r'^([A-Z]+)-', booth_id)
    if match:
        return match.group(1)
    return ""


def generate_navigation_points(booths: List[str]) -> List[Dict]:
    points = []
    for i, booth in enumerate(sorted(booths)):
        zone = get_booth_zone(booth)
        points.append({
            "id": f"nav-{i+1:03d}",
            "name": f"{booth} 导航点",
            "booth_id": booth,
            "zone": zone,
            "position": {"x": i * 5.0, "y": 0.0, "z": 0.0},
            "type": "booth" if i > 0 else "entrance"
        })
    return points


def compute_file_hash(file_path: Path) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def print_success(message: str):
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str):
    console.print(f"[red]✗[/red] {message}")


def print_warning(message: str):
    console.print(f"[yellow]![/yellow] {message}")


def print_info(message: str):
    console.print(f"[blue]ℹ[/blue] {message}")


def print_table(title: str, columns: List[str], rows: List[List[str]]):
    table = Table(title=title)
    for col in columns:
        table.add_column(col)
    for row in rows:
        table.add_row(*row)
    console.print(table)


def is_project_dir(path: str) -> bool:
    config_path = Path(path) / "scene.yaml"
    return config_path.exists()


def find_project_dir(start_path: str = ".") -> Optional[str]:
    current = Path(start_path).resolve()
    while True:
        if (current / "scene.yaml").exists():
            return str(current)
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None
