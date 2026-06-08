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
def ops_cli(ctx):
    """运营协同 - 运营看板、进度跟踪、风险预警"""
    pass


@ops_cli.command("dashboard")
@click.option("--zone", "-z", help="查看指定展区，默认全场")
@click.option("--sort-by", "-s", default="risk",
              type=click.Choice(["risk", "booth", "asset", "avatar", "schedule"]),
              help="排序方式")
@click.pass_context
def dashboard(ctx, zone, sort_by):
    """运营看板：查看各展区完成率和发布风险"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    config = SceneConfig(project_path)
    zones = config.get("scene.zones", [])
    all_booths = config.get("booths", [])
    all_assets = config.get("assets", [])
    all_avatars = config.get("avatars", [])
    all_schedules = config.get("schedules", [])

    if zone:
        zones = [z for z in zones if z == zone]
        if not zones:
            print_error(f"未找到展区: {zone}")
            raise click.Abort()

    zone_stats = []
    for z in zones:
        booths = [b for b in all_booths if b.get("zone") == z]
        booth_ids = {b["id"] for b in booths}
        assets = [a for a in all_assets if a.get("booth_id") in booth_ids]
        asset_paths = {a["path"] for a in assets}
        avatars = [a for a in all_avatars if a.get("booth_id") in booth_ids]
        schedules = [s for s in all_schedules if s.get("zone") == z or s.get("booth_id") in booth_ids]

        booth_count = len(booths)
        if booth_count == 0:
            zone_stats.append({
                "zone": z,
                "booth_count": 0,
                "booth_rate": 0,
                "asset_rate": 0,
                "avatar_rate": 0,
                "schedule_rate": 0,
                "risk_score": 100,
                "risk_level": "high",
            })
            continue

        # 展位资料完成率（公司+联系人齐全的展位比例）
        booth_complete = sum(1 for b in booths if b.get("company") and b.get("contact"))
        booth_rate = int(booth_complete / booth_count * 100)

        # 资源完成率（模型+海报都有的展位比例）
        asset_complete = sum(
            1 for b in booths
            if b.get("model") and b["model"] in asset_paths
            and b.get("poster") and b["poster"] in asset_paths
        )
        asset_rate = int(asset_complete / booth_count * 100)

        # 嘉宾头像完成率
        avatar_count = len(avatars)
        avatar_with_img = sum(1 for a in avatars if a.get("avatar"))
        avatar_rate = int(avatar_with_img / avatar_count * 100) if avatar_count > 0 else 100

        # 直播安排完成率（有直播安排的展位比例）
        schedule_booth_ids = {s.get("booth_id") for s in schedules if s.get("booth_id")}
        schedule_complete = sum(1 for b in booths if b["id"] in schedule_booth_ids)
        schedule_rate = int(schedule_complete / booth_count * 100) if booth_count > 0 else 0

        # 风险评分（越低越好，基于各完成率加权）
        risk_score = int(
            (100 - booth_rate) * 0.2 +
            (100 - asset_rate) * 0.4 +
            (100 - avatar_rate) * 0.2 +
            (100 - schedule_rate) * 0.2
        )

        if risk_score >= 50:
            risk_level = "high"
        elif risk_score >= 25:
            risk_level = "medium"
        else:
            risk_level = "low"

        zone_stats.append({
            "zone": z,
            "booth_count": booth_count,
            "booth_rate": booth_rate,
            "asset_rate": asset_rate,
            "avatar_rate": avatar_rate,
            "schedule_rate": schedule_rate,
            "risk_score": risk_score,
            "risk_level": risk_level,
        })

    # 排序
    sort_keys = {
        "risk": "risk_score",
        "booth": "booth_rate",
        "asset": "asset_rate",
        "avatar": "avatar_rate",
        "schedule": "schedule_rate",
    }
    reverse = sort_by != "risk"
    zone_stats.sort(key=lambda x: x[sort_keys[sort_by]], reverse=reverse)

    console.rule("[bold magenta]运营看板[/bold magenta]")
    console.print()

    rows = []
    for stat in zone_stats:
        risk_colors = {"high": "red", "medium": "yellow", "low": "green"}
        risk_labels = {"high": "高风险", "medium": "中风险", "low": "低风险"}
        risk_style = risk_colors[stat["risk_level"]]
        risk_label = risk_labels[stat["risk_level"]]

        rows.append([
            f"[bold]{stat['zone']}[/bold]",
            str(stat["booth_count"]),
            _rate_bar(stat["booth_rate"]),
            _rate_bar(stat["asset_rate"]),
            _rate_bar(stat["avatar_rate"]),
            _rate_bar(stat["schedule_rate"]),
            f"[{risk_style}]{risk_label} ({stat['risk_score']})[/{risk_style}]",
        ])

    print_table(
        "展区完成率与风险总览",
        ["展区", "展位", "资料完成", "资源完成", "头像完成", "直播安排", "风险等级"],
        rows,
    )

    # 全场汇总
    total_booths = sum(s["booth_count"] for s in zone_stats)
    if total_booths > 0:
        avg_booth = int(sum(s["booth_rate"] * s["booth_count"] for s in zone_stats) / total_booths)
        avg_asset = int(sum(s["asset_rate"] * s["booth_count"] for s in zone_stats) / total_booths)
        avg_avatar_raw = sum(s["avatar_rate"] * s["booth_count"] for s in zone_stats) / total_booths
        avg_schedule = int(sum(s["schedule_rate"] * s["booth_count"] for s in zone_stats) / total_booths)

        console.print()
        print_info(f"全场汇总: {len(zones)} 个展区，{total_booths} 个展位")
        print_info(f"  资料完成率: {avg_booth}% | 资源完成率: {avg_asset}% | 头像完成率: {int(avg_avatar_raw)}% | 直播完成率: {avg_schedule}%")

    # 高风险提示
    high_risk = [s for s in zone_stats if s["risk_level"] == "high"]
    if high_risk:
        console.print()
        print_warning(f"⚠ 高风险展区 ({len(high_risk)} 个): {', '.join(s['zone'] for s in high_risk)}")
        print_info("建议优先推进上述展区的资源和资料补齐")


def _rate_bar(rate: int) -> str:
    """生成进度条样式的完成率展示"""
    filled = int(rate / 10)
    bar = "█" * filled + "░" * (10 - filled)
    if rate >= 80:
        color = "green"
    elif rate >= 50:
        color = "yellow"
    else:
        color = "red"
    return f"[{color}]{bar} {rate}%[/{color}]"
