import click
from pathlib import Path
from metaverse.config import SceneConfig
from metaverse.utils import (
    console,
    print_success,
    print_error,
    print_info,
    print_warning,
    print_table,
    ensure_dir,
    is_project_dir,
    generate_navigation_points,
)


@click.group()
@click.pass_context
def scene_cli(ctx):
    """场景管理 - 创建场景项目、配置欢迎语、生成导航点"""
    pass


@scene_cli.command()
@click.argument("name")
@click.option("--theme", "-t", default="default", help="场景主题")
@click.option("--zones", "-z", multiple=True, help="展区列表，如 -z A -z B")
@click.option("--output-dir", "-o", default=".", help="项目输出目录")
@click.pass_context
def init(ctx, name, theme, zones, output_dir):
    """创建新的场景项目

    NAME 为场景名称
    """
    project_path = Path(output_dir) / name
    if project_path.exists():
        print_error(f"项目 {name} 已存在")
        raise click.Abort()

    ensure_dir(project_path)
    ensure_dir(project_path / "assets")
    ensure_dir(project_path / "assets" / "models")
    ensure_dir(project_path / "assets" / "posters")
    ensure_dir(project_path / "assets" / "avatars")
    ensure_dir(project_path / "booths")
    ensure_dir(project_path / "schedules")
    ensure_dir(project_path / "releases")
    ensure_dir(project_path / "reports")

    config = SceneConfig(str(project_path))
    config.set("scene.name", name)
    config.set("scene.theme", theme)
    config.set("scene.zones", list(zones) if zones else ["A", "B", "C"])
    config.set("scene.welcome_message", f"欢迎来到{name}虚拟展厅！")
    config.set("scene.navigation_points", [])
    config.set("scene.status", "draft")
    config.set("booths", [])
    config.set("assets", [])
    config.set("avatars", [])
    config.set("schedules", [])
    config.set("publish_history", [])
    config.save()

    print_success(f"场景项目 '{name}' 创建成功")
    print_info(f"项目路径: {project_path.resolve()}")
    print_info(f"主题: {theme}")
    if zones:
        print_info(f"展区: {', '.join(zones)}")


@scene_cli.command()
@click.option("--message", "-m", required=True, help="入口欢迎语")
@click.pass_context
def welcome(ctx, message):
    """配置入口欢迎语"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    config.set("scene.welcome_message", message)
    config.save()
    print_success(f"欢迎语已更新: {message}")


@scene_cli.command("gen-nav")
@click.option("--zone", "-z", help="指定展区过滤，如 -z A")
@click.pass_context
def gen_nav(ctx, zone):
    """生成空间导航点"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    booths = config.get("booths", [])

    if zone:
        booths = [b for b in booths if b.get("zone") == zone]

    booth_ids = [b["id"] for b in booths]
    nav_points = generate_navigation_points(booth_ids)

    config.set("scene.navigation_points", nav_points)
    config.save()

    print_success(f"已生成 {len(nav_points)} 个导航点")
    rows = [[p["id"], p["name"], p["zone"], f"({p['position']['x']}, {p['position']['y']}, {p['position']['z']}"] for p in nav_points]
    print_table("导航点列表", ["ID", "名称", "展区", "位置"], rows)


@scene_cli.command()
@click.pass_context
def info(ctx):
    """查看场景信息"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    scene = config.get("scene", {})
    booths = config.get("booths", [])
    assets = config.get("assets", [])
    avatars = config.get("avatars", [])
    schedules = config.get("schedules", [])

    console.print(f"[bold]场景名称:[/bold] {scene.get('name', 'N/A')}")
    console.print(f"[bold]主题:[/bold] {scene.get('theme', 'N/A')}")
    console.print(f"[bold]状态:[/bold] {scene.get('status', 'N/A')}")
    console.print(f"[bold]展区:[/bold] {', '.join(scene.get('zones', []))}")
    console.print(f"[bold]欢迎语:[/bold] {scene.get('welcome_message', 'N/A')}")
    console.print(f"[bold]导航点数量:[/bold] {len(scene.get('navigation_points', []))}")
    console.print(f"[bold]展位数量:[/bold] {len(booths)}")
    console.print(f"[bold]资源数量:[/bold] {len(assets)}")
    console.print(f"[bold]嘉宾数量:[/bold] {len(avatars)}")
    console.print(f"[bold]直播场次:[/bold] {len(schedules)}")
