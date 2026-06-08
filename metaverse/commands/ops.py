import click
from pathlib import Path
from datetime import datetime, date
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
@click.option("--owner", "-O", help="按负责人筛选")
@click.option("--status", "-S", "status_label",
              type=click.Choice(["not-started", "in-progress", "review", "done", "blocked"]),
              help="按状态标签筛选")
@click.option("--deadline-before", help="截止时间早于此日期 (YYYY-MM-DD)")
@click.option("--deadline-after", help="截止时间晚于此日期 (YYYY-MM-DD)")
@click.option("--sort-by", "-s", default="risk",
              type=click.Choice(["risk", "booth", "asset", "avatar", "schedule", "deadline"]),
              help="排序方式")
@click.option("--include-all", is_flag=True, default=True, show_default=True,
              help="包含所有实际存在的展区（包括未配置的）")
@click.pass_context
def dashboard(ctx, zone, owner, status_label, deadline_before, deadline_after, sort_by, include_all):
    """运营看板：活动推进台，查看各展区完成率、风险、负责人、截止时间"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    zones_config = config.get("scene.zones", [])
    zone_info = config.get("scene.zone_info", {})
    all_booths = config.get("booths", [])
    all_assets = config.get("assets", [])
    all_avatars = config.get("avatars", [])
    all_schedules = config.get("schedules", [])

    # 动态收集所有展区：配置里的 + 实际展位里出现的
    booth_zones = {b.get("zone") for b in all_booths if b.get("zone")}
    all_zones = list(zones_config)
    for bz in sorted(booth_zones):
        if bz not in all_zones:
            all_zones.append(bz)

    if zone:
        all_zones = [z for z in all_zones if z == zone]
        if not all_zones:
            print_error(f"未找到展区: {zone}")
            raise click.Abort()

    # 计算每个展区的统计
    zone_stats = []
    for z in all_zones:
        info = zone_info.get(z, {})
        booths = [b for b in all_booths if b.get("zone") == z]
        booth_ids = {b["id"] for b in booths}
        assets = [a for a in all_assets if a.get("booth_id") in booth_ids]
        asset_paths = {a["path"] for a in assets}
        avatars = [a for a in all_avatars if a.get("booth_id") in booth_ids]
        schedules = [s for s in all_schedules if s.get("zone") == z or s.get("booth_id") in booth_ids]

        booth_count = len(booths)

        # 展位资料完成率
        booth_complete = sum(1 for b in booths if b.get("company") and b.get("contact"))
        booth_rate = int(booth_complete / booth_count * 100) if booth_count > 0 else 0

        # 资源完成率
        asset_complete = sum(
            1 for b in booths
            if b.get("model") and b["model"] in asset_paths
            and b.get("poster") and b["poster"] in asset_paths
        ) if booth_count > 0 else 0
        asset_rate = int(asset_complete / booth_count * 100) if booth_count > 0 else 0

        # 嘉宾头像完成率
        avatar_count = len(avatars)
        avatar_with_img = sum(1 for a in avatars if a.get("avatar"))
        avatar_rate = int(avatar_with_img / avatar_count * 100) if avatar_count > 0 else 100

        # 直播安排完成率
        schedule_booth_ids = {s.get("booth_id") for s in schedules if s.get("booth_id")}
        schedule_complete = sum(1 for b in booths if b["id"] in schedule_booth_ids) if booth_count > 0 else 0
        schedule_rate = int(schedule_complete / booth_count * 100) if booth_count > 0 else 0

        # 风险评分
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

        deadline = info.get("deadline")
        days_left = None
        if deadline:
            try:
                dl_date = datetime.strptime(deadline, "%Y-%m-%d").date()
                today = date.today()
                days_left = (dl_date - today).days
            except ValueError:
                pass

        zone_stats.append({
            "zone": z,
            "booth_count": booth_count,
            "booth_rate": booth_rate,
            "asset_rate": asset_rate,
            "avatar_rate": avatar_rate,
            "schedule_rate": schedule_rate,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "owner": info.get("owner", "-"),
            "status": info.get("status", "-"),
            "deadline": deadline or "-",
            "days_left": days_left,
        })

    # 应用筛选
    if owner:
        zone_stats = [s for s in zone_stats if owner.lower() in s["owner"].lower()]
    if status_label:
        zone_stats = [s for s in zone_stats if s["status"] == status_label]
    if deadline_before:
        try:
            dl_before = datetime.strptime(deadline_before, "%Y-%m-%d").date()
            zone_stats = [
                s for s in zone_stats
                if s["days_left"] is not None and (date.today() + __import__("datetime").timedelta(days=s["days_left"])) <= dl_before
            ]
        except ValueError:
            print_warning("截止时间筛选日期格式无效，已跳过")
    if deadline_after:
        try:
            dl_after = datetime.strptime(deadline_after, "%Y-%m-%d").date()
            zone_stats = [
                s for s in zone_stats
                if s["days_left"] is not None and (date.today() + __import__("datetime").timedelta(days=s["days_left"])) >= dl_after
            ]
        except ValueError:
            print_warning("截止时间筛选日期格式无效，已跳过")

    if not zone_stats:
        print_warning("没有匹配的展区")
        return

    # 排序
    if sort_by == "risk":
        zone_stats.sort(key=lambda x: x["risk_score"], reverse=True)
    elif sort_by == "deadline":
        zone_stats.sort(key=lambda x: (x["days_left"] is None, x["days_left"] if x["days_left"] is not None else 9999))
    else:
        rate_keys = {"booth": "booth_rate", "asset": "asset_rate", "avatar": "avatar_rate", "schedule": "schedule_rate"}
        zone_stats.sort(key=lambda x: x[rate_keys[sort_by]], reverse=True)

    console.rule("[bold magenta]运营看板 · 活动推进台[/bold magenta]")
    console.print()

    # 状态标签映射
    status_labels = {
        "not-started": "未启动",
        "in-progress": "进行中",
        "review": "待验收",
        "done": "已完成",
        "blocked": "阻塞",
        "-": "-",
    }
    status_colors = {
        "not-started": "grey",
        "in-progress": "cyan",
        "review": "yellow",
        "done": "green",
        "blocked": "red",
        "-": "white",
    }

    rows = []
    for stat in zone_stats:
        risk_colors = {"high": "red", "medium": "yellow", "low": "green"}
        risk_label = {"high": "高", "medium": "中", "low": "低"}
        risk_style = risk_colors[stat["risk_level"]]
        risk_txt = risk_label[stat["risk_level"]]

        status_text = status_labels.get(stat["status"], stat["status"])
        status_color = status_colors.get(stat["status"], "white")

        # 截止时间显示
        dl_text = stat["deadline"]
        if stat["days_left"] is not None:
            if stat["days_left"] < 0:
                dl_text = f"[red]{stat['deadline']} (已逾期{-stat['days_left']}天)[/red]"
            elif stat["days_left"] <= 3:
                dl_text = f"[yellow]{stat['deadline']} (剩{stat['days_left']}天)[/yellow]"
            else:
                dl_text = f"[green]{stat['deadline']} (剩{stat['days_left']}天)[/green]"

        rows.append([
            f"[bold]{stat['zone']}[/bold]",
            str(stat["booth_count"]),
            _rate_bar(stat["booth_rate"]),
            _rate_bar(stat["asset_rate"]),
            f"[{status_color}]{status_text}[/{status_color}]",
            stat["owner"],
            dl_text,
            f"[{risk_style}]{risk_txt} ({stat['risk_score']})[/{risk_style}]",
        ])

    print_table(
        "展区推进总览",
        ["展区", "展位", "资料完成", "资源完成", "状态", "负责人", "截止时间", "风险"],
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
        print_info(f"全场汇总: {len(zone_stats)} 个展区，{total_booths} 个展位")
        print_info(f"  资料: {avg_booth}% | 资源: {avg_asset}% | 头像: {int(avg_avatar_raw)}% | 直播: {avg_schedule}%")

    # 高风险提示
    high_risk = [s for s in zone_stats if s["risk_level"] == "high"]
    if high_risk:
        console.print()
        print_warning(f"⚠ 高风险展区 ({len(high_risk)} 个): {', '.join(s['zone'] for s in high_risk)}")
        print_info("建议优先推进上述展区的资源和资料补齐")

    # 即将到期提醒
    soon_due = [s for s in zone_stats if s["days_left"] is not None and 0 <= s["days_left"] <= 7]
    if soon_due:
        console.print()
        print_warning(f"⏰ 7天内到期 ({len(soon_due)} 个): {', '.join(s['zone'] for s in soon_due)}")

    # 逾期提醒
    overdue = [s for s in zone_stats if s["days_left"] is not None and s["days_left"] < 0]
    if overdue:
        console.print()
        print_error(f"🔥 已逾期 ({len(overdue)} 个): {', '.join(s['zone'] for s in overdue)}")


@ops_cli.command("set-zone-info")
@click.argument("zone")
@click.option("--owner", "-O", help="负责人")
@click.option("--deadline", "-D", help="截止日期 (YYYY-MM-DD)")
@click.option("--status", "-S", "status_label",
              type=click.Choice(["not-started", "in-progress", "review", "done", "blocked"]),
              help="状态标签")
@click.pass_context
def set_zone_info(ctx, zone, owner, deadline, status_label):
    """设置展区信息：负责人、截止时间、状态标签"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    if not owner and not deadline and not status_label:
        print_error("至少需要指定 --owner、--deadline 或 --status 中的一个")
        raise click.Abort()

    config = SceneConfig(project_path)
    zone_info = config.get("scene.zone_info", {})

    if zone not in zone_info:
        zone_info[zone] = {}

    if owner is not None:
        zone_info[zone]["owner"] = owner
    if deadline is not None:
        zone_info[zone]["deadline"] = deadline
    if status_label is not None:
        zone_info[zone]["status"] = status_label

    config.set("scene.zone_info", zone_info)
    config.save()

    status_labels = {
        "not-started": "未启动", "in-progress": "进行中",
        "review": "待验收", "done": "已完成", "blocked": "阻塞",
    }
    info = zone_info[zone]
    print_success(f"已更新展区 {zone} 的信息")
    if "owner" in info:
        print_info(f"  负责人: {info['owner']}")
    if "deadline" in info:
        print_info(f"  截止时间: {info['deadline']}")
    if "status" in info:
        print_info(f"  状态: {status_labels.get(info['status'], info['status'])}")


@ops_cli.command("list-zones")
@click.option("--owner", "-O", help="按负责人筛选")
@click.option("--status", "-S", "status_label",
              type=click.Choice(["not-started", "in-progress", "review", "done", "blocked"]),
              help="按状态筛选")
@click.pass_context
def list_zones(ctx, owner, status_label):
    """列出所有展区及配置信息"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    zones_config = config.get("scene.zones", [])
    zone_info = config.get("scene.zone_info", {})
    all_booths = config.get("booths", [])

    # 动态收集所有展区
    booth_zones = {b.get("zone") for b in all_booths if b.get("zone")}
    all_zones = list(zones_config)
    for bz in sorted(booth_zones):
        if bz not in all_zones:
            all_zones.append(bz)

    status_labels = {
        "not-started": "未启动", "in-progress": "进行中",
        "review": "待验收", "done": "已完成", "blocked": "阻塞",
    }

    rows = []
    for z in all_zones:
        info = zone_info.get(z, {})
        booth_count = sum(1 for b in all_booths if b.get("zone") == z)
        status_text = status_labels.get(info.get("status", "-"), info.get("status", "-"))
        rows.append([
            z,
            str(booth_count),
            info.get("owner", "-"),
            info.get("deadline", "-"),
            status_text,
        ])

    # 筛选
    if owner:
        rows = [r for r in rows if owner.lower() in r[2].lower()]
    if status_label:
        status_text = status_labels.get(status_label, status_label)
        rows = [r for r in rows if r[4] == status_text]

    if not rows:
        print_warning("没有匹配的展区")
        return

    print_table(
        f"展区列表 ({len(rows)} 个)",
        ["展区", "展位", "负责人", "截止时间", "状态"],
        rows,
    )


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
