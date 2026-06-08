import click
from pathlib import Path
from metaverse.config import SceneConfig
from metaverse.utils import (
    print_success,
    print_error,
    print_warning,
    print_info,
    print_table,
    is_project_dir,
    console,
)


@click.group()
@click.pass_context
def zone_cli(ctx):
    """展区管理 - 展区负责人视图，一站式查看/验收展区内容"""
    pass


@zone_cli.command("overview")
@click.argument("zone")
@click.pass_context
def zone_overview(ctx, zone):
    """查看指定展区的一站式概览

    ZONE 展区编号，如 A
    """
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    booths = [b for b in config.get("booths", []) if b.get("zone") == zone]
    booth_ids = {b["id"] for b in booths}
    assets = [a for a in config.get("assets", []) if a.get("booth_id") in booth_ids]
    avatars = [a for a in config.get("avatars", []) if a.get("booth_id") in booth_ids]
    schedules = [s for s in config.get("schedules", []) if s.get("zone") == zone or s.get("booth_id") in booth_ids]

    console.rule(f"[bold cyan]展区 {zone} 概览[/bold cyan]")
    console.print()

    # 基本统计
    console.print(f"[bold]展位总数:[/bold] {len(booths)} 个")
    console.print(f"[bold]资源总数:[/bold] {len(assets)} 个")
    console.print(f"[bold]嘉宾总数:[/bold] {len(avatars)} 人")
    console.print(f"[bold]直播场次:[/bold] {len(schedules)} 场")
    console.print()

    # 展位列表
    if booths:
        rows = [[b["id"], b.get("company", ""), b.get("contact", "")] for b in sorted(booths, key=lambda x: x["id"])]
        print_table(f"展位列表 ({len(booths)} 个)", ["展位号", "公司", "联系人"], rows)

    # 资源统计
    asset_by_type = {}
    for a in assets:
        t = a["type"]
        asset_by_type[t] = asset_by_type.get(t, 0) + 1
    if asset_by_type:
        rows = [[t, str(c)] for t, c in sorted(asset_by_type.items())]
        print_table("资源类型统计", ["类型", "数量"], rows)

    # 嘉宾列表
    if avatars:
        rows = [[a["name"], a.get("title", ""), a.get("booth_id", ""),
                 "✓" if a.get("avatar") else "✗"] for a in avatars]
        print_table(f"嘉宾列表 ({len(avatars)} 人)", ["姓名", "头衔", "展位", "头像"], rows)

    # 直播日程
    if schedules:
        schedules_sorted = sorted(schedules, key=lambda x: x.get("start", ""))
        rows = [[s["title"], s["start"], s["end"], s.get("speaker", ""), s.get("type", "")]
                for s in schedules_sorted]
        print_table(f"直播日程 ({len(schedules)} 场)", ["标题", "开始", "结束", "主讲人", "类型"], rows)


@zone_cli.command("check")
@click.argument("zone")
@click.option("--detail", "-d", is_flag=True, help="显示详细缺失项")
@click.pass_context
def zone_check(ctx, zone, detail):
    """检查展区缺失项，用于活动前验收

    ZONE 展区编号，如 A
    """
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    booths = [b for b in config.get("booths", []) if b.get("zone") == zone]
    booth_ids = {b["id"] for b in booths}
    assets = [a for a in config.get("assets", []) if a.get("booth_id") in booth_ids]
    asset_paths = {a["path"] for a in assets}
    avatars = [a for a in config.get("avatars", []) if a.get("booth_id") in booth_ids]
    schedules = [s for s in config.get("schedules", []) if s.get("zone") == zone or s.get("booth_id") in booth_ids]

    missing_model = []
    missing_poster = []
    missing_logo = []
    missing_company = []
    missing_contact = []
    missing_avatar_img = []
    booths_without_schedule = []

    for booth in booths:
        bid = booth["id"]
        if not booth.get("model") or booth["model"] not in asset_paths:
            missing_model.append(bid)
        if not booth.get("poster") or booth["poster"] not in asset_paths:
            missing_poster.append(bid)
        if not booth.get("logo") or booth["logo"] not in asset_paths:
            missing_logo.append(bid)
        if not booth.get("company"):
            missing_company.append(bid)
        if not booth.get("contact"):
            missing_contact.append(bid)

    schedule_booths = {s.get("booth_id") for s in schedules if s.get("booth_id")}
    for booth in booths:
        if booth["id"] not in schedule_booths:
            booths_without_schedule.append(booth["id"])

    for avatar in avatars:
        if not avatar.get("avatar"):
            missing_avatar_img.append(avatar["name"])

    console.rule(f"[bold yellow]展区 {zone} 缺失项检查[/bold yellow]")
    console.print()

    checks = [
        ("展商资料-公司名称", missing_company, "warning"),
        ("展商资料-联系人", missing_contact, "warning"),
        ("3D模型", missing_model, "error"),
        ("海报", missing_poster, "error"),
        ("Logo", missing_logo, "warning"),
        ("嘉宾头像", missing_avatar_img, "warning"),
        ("展位无直播安排", booths_without_schedule, "info"),
    ]

    summary_rows = []
    for name, items, level in checks:
        count = len(items)
        status = "✓" if count == 0 else f"{count} 项缺失"
        style = "green" if count == 0 else ("red" if level == "error" else "yellow")
        summary_rows.append([name, f"[{style}]{status}[/{style}]"])
    print_table("验收检查清单", ["检查项", "状态"], summary_rows)

    if detail:
        console.print()
        if missing_model:
            print_warning(f"缺模型的展位: {', '.join(missing_model)}")
        if missing_poster:
            print_warning(f"缺海报的展位: {', '.join(missing_poster)}")
        if missing_logo:
            print_warning(f"缺Logo的展位: {', '.join(missing_logo)}")
        if missing_company:
            print_warning(f"缺公司名称的展位: {', '.join(missing_company)}")
        if missing_contact:
            print_warning(f"缺联系人的展位: {', '.join(missing_contact)}")
        if missing_avatar_img:
            print_warning(f"缺头像的嘉宾: {', '.join(missing_avatar_img)}")
        if booths_without_schedule:
            print_info(f"无直播安排的展位: {', '.join(booths_without_schedule)}")

    total_issues = sum(len(items) for _, items, _ in checks)
    console.print()
    if total_issues == 0:
        print_success(f"展区 {zone} 验收通过，所有检查项均已完成！")
    else:
        print_warning(f"展区 {zone} 共发现 {total_issues} 项待完善内容")


@zone_cli.command("list")
@click.pass_context
def list_zones(ctx):
    """列出所有展区及统计摘要"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    zones = config.get("scene.zones", [])
    booths = config.get("booths", [])
    assets = config.get("assets", [])
    avatars = config.get("avatars", [])
    schedules = config.get("schedules", [])

    rows = []
    for z in zones:
        zone_booths = [b for b in booths if b.get("zone") == z]
        zone_booth_ids = {b["id"] for b in zone_booths}
        zone_assets = [a for a in assets if a.get("booth_id") in zone_booth_ids]
        zone_avatars = [a for a in avatars if a.get("booth_id") in zone_booth_ids]
        zone_schedules = [s for s in schedules if s.get("zone") == z or s.get("booth_id") in zone_booth_ids]
        rows.append([z, str(len(zone_booths)), str(len(zone_assets)),
                     str(len(zone_avatars)), str(len(zone_schedules))])

    print_table("展区列表", ["展区", "展位", "资源", "嘉宾", "直播"], rows)
