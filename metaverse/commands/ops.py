import click
import json
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


@ops_cli.command("reminder")
@click.option("--owner", "-O", help="只看指定负责人的催办")
@click.option("--output", "-o", help="导出催办清单（支持 .md/.csv/.json）")
@click.option("--by-owner", is_flag=True, help="按负责人分组展示")
@click.option("--urgency",
              type=click.Choice(["all", "overdue", "today", "soon"]),
              default="all", help="按紧急程度筛选: all(全部) overdue(已逾期) today(今天到期) soon(3天内)")
@click.pass_context
def reminder(ctx, owner, output, by_owner, urgency):
    """催办清单：按负责人汇总缺项，支持按截止时间分组"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    zone_info = config.get("scene.zone_info", {})
    all_booths = config.get("booths", [])
    all_assets = config.get("assets", [])
    all_avatars = config.get("avatars", [])
    all_schedules = config.get("schedules", [])

    # 动态收集所有展区
    zones_config = config.get("scene.zones", [])
    booth_zones = {b.get("zone") for b in all_booths if b.get("zone")}
    all_zones = list(zones_config)
    for bz in sorted(booth_zones):
        if bz not in all_zones:
            all_zones.append(bz)

    # 计算每个展区的缺项明细
    today = date.today()
    from datetime import timedelta

    zone_details = []
    for z in all_zones:
        info = zone_info.get(z, {})
        booths = [b for b in all_booths if b.get("zone") == z]
        booth_ids = {b["id"] for b in booths}
        assets = [a for a in all_assets if a.get("booth_id") in booth_ids]
        asset_paths = {a["path"] for a in assets}
        avatars = [a for a in all_avatars if a.get("booth_id") in booth_ids]
        schedules = [s for s in all_schedules
                     if s.get("zone") == z or s.get("booth_id") in booth_ids]

        missing_items = []
        missing_detail = []

        for b in booths:
            bid = b["id"]
            company = b.get("company", bid)

            # 缺模型
            if not b.get("model") or b["model"] not in asset_paths:
                missing_items.append("模型")
                missing_detail.append({
                    "booth": bid,
                    "company": company,
                    "type": "模型文件",
                    "item": b.get("model", "未配置"),
                })

            # 缺海报
            if not b.get("poster") or b["poster"] not in asset_paths:
                missing_items.append("海报")
                missing_detail.append({
                    "booth": bid,
                    "company": company,
                    "type": "海报文件",
                    "item": b.get("poster", "未配置"),
                })

        # 缺嘉宾头像
        for a in avatars:
            if not a.get("avatar"):
                missing_items.append("嘉宾头像")
                missing_detail.append({
                    "booth": a.get("booth_id", ""),
                    "company": a.get("name", ""),
                    "type": "嘉宾头像",
                    "item": a.get("name", ""),
                })
                break  # 每个展区只算一次类别

        # 缺直播安排
        sched_booth_ids = {s.get("booth_id") for s in schedules if s.get("booth_id")}
        for b in booths:
            bid = b["id"]
            company = b.get("company", bid)
            if bid not in sched_booth_ids:
                missing_items.append("直播安排")
                missing_detail.append({
                    "booth": bid,
                    "company": company,
                    "type": "直播安排",
                    "item": "未安排",
                })
                break  # 每个展区只算一次类别

        # 计算截止时间和紧急度
        deadline_str = info.get("deadline", "")
        days_left = None
        urgency_level = "normal"
        if deadline_str:
            try:
                dl = datetime.strptime(deadline_str, "%Y-%m-%d").date()
                days_left = (dl - today).days
                if days_left < 0:
                    urgency_level = "overdue"
                elif days_left == 0:
                    urgency_level = "today"
                elif days_left <= 3:
                    urgency_level = "soon"
            except ValueError:
                pass

        zone_details.append({
            "zone": z,
            "owner": info.get("owner", "未分配"),
            "deadline": deadline_str,
            "days_left": days_left,
            "urgency": urgency_level,
            "booth_count": len(booths),
            "missing_categories": list(set(missing_items)),
            "missing_detail": missing_detail,
            "missing_count": len(set(missing_items)),
        })

    # 按紧急度筛选
    if urgency == "overdue":
        zone_details = [z for z in zone_details if z["urgency"] == "overdue"]
    elif urgency == "today":
        zone_details = [z for z in zone_details if z["urgency"] == "today"]
    elif urgency == "soon":
        zone_details = [z for z in zone_details if z["urgency"] in ("today", "soon", "overdue")]

    # 按负责人筛选
    if owner:
        zone_details = [z for z in zone_details if owner.lower() in z["owner"].lower()]

    if not zone_details:
        print_warning("没有匹配的催办项")
        return

    # 排序：按紧急度 + 截止时间
    urgency_order = {"overdue": 0, "today": 1, "soon": 2, "normal": 3}
    zone_details.sort(key=lambda x: (
        urgency_order.get(x["urgency"], 9),
        x["days_left"] if x["days_left"] is not None else 9999,
    ))

    # 按负责人分组
    if by_owner:
        _print_reminder_by_owner(zone_details)
    else:
        _print_reminder_by_urgency(zone_details)

    if output:
        _export_reminder(zone_details, output)


def _print_reminder_by_urgency(zone_details):
    """按紧急度分组输出催办清单"""
    groups = {
        "overdue": [],
        "today": [],
        "soon": [],
        "normal": [],
    }
    group_labels = {
        "overdue": ("🔥 已逾期", "red"),
        "today": ("⏰ 今天到期", "yellow"),
        "soon": ("📅 3天内到期", "cyan"),
        "normal": ("📌 其他", "white"),
    }
    for z in zone_details:
        groups[z["urgency"]].append(z)

    console.rule("[bold red]催办清单[/bold red]")
    console.print()

    total_missing = sum(len(z["missing_categories"]) for z in zone_details)
    print_info(f"共 {len(zone_details)} 个展区需跟进，{total_missing} 项缺项待处理")
    console.print()

    for key in ["overdue", "today", "soon", "normal"]:
        items = groups[key]
        if not items:
            continue
        label, color = group_labels[key]
        console.print(f"[bold {color}]{label} ({len(items)} 个展区)[/bold {color}]")

        rows = []
        for z in items:
            dl_text = z["deadline"]
            if z["days_left"] is not None:
                if z["days_left"] < 0:
                    dl_text = f"[red]{z['deadline']} (逾期{-z['days_left']}天)[/red]"
                elif z["days_left"] == 0:
                    dl_text = f"[yellow]{z['deadline']} (今天)[/yellow]"
                else:
                    dl_text = f"{z['deadline']} (剩{z['days_left']}天)"

            missing = "、".join(z["missing_categories"]) if z["missing_categories"] else "-"
            rows.append([
                z["zone"],
                z["owner"],
                dl_text,
                str(z["booth_count"]),
                missing,
            ])
        print_table("", ["展区", "负责人", "截止时间", "展位", "缺项类别"], rows)
        console.print()


def _print_reminder_by_owner(zone_details):
    """按负责人分组输出催办清单"""
    owner_groups = {}
    for z in zone_details:
        o = z["owner"]
        if o not in owner_groups:
            owner_groups[o] = []
        owner_groups[o].append(z)

    console.rule("[bold red]催办清单 · 按负责人[/bold red]")
    console.print()

    total_missing = sum(len(z["missing_categories"]) for z in zone_details)
    print_info(f"共 {len(owner_groups)} 位负责人，{len(zone_details)} 个展区需跟进")
    console.print()

    for owner in sorted(owner_groups.keys()):
        zones = owner_groups[owner]
        total = len(zones)
        missing_total = sum(len(z["missing_categories"]) for z in zones)

        console.print(f"[bold cyan]👤 {owner}[/bold cyan] "
                      f"({total} 个展区，{missing_total} 项缺项)")

        rows = []
        for z in sorted(zones, key=lambda x: x["zone"]):
            dl_text = z["deadline"]
            if z["days_left"] is not None:
                if z["days_left"] < 0:
                    dl_text = f"[red]逾期{-z['days_left']}天[/red]"
                elif z["days_left"] == 0:
                    dl_text = f"[yellow]今天[/yellow]"
                else:
                    dl_text = f"剩{z['days_left']}天"

            missing = "、".join(z["missing_categories"]) if z["missing_categories"] else "-"
            rows.append([
                z["zone"],
                dl_text,
                str(z["booth_count"]),
                missing,
            ])
        print_table("", ["展区", "截止时间", "展位", "缺项类别"], rows)
        console.print()


def _export_reminder(zone_details, output_path):
    """导出催办清单"""
    import csv as csv_module
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.suffix.lower() == ".md":
        content = _generate_reminder_markdown(zone_details)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    elif path.suffix.lower() == ".csv":
        rows = []
        for z in zone_details:
            if not z["missing_detail"]:
                rows.append({
                    "zone": z["zone"],
                    "owner": z["owner"],
                    "deadline": z["deadline"],
                    "days_left": z["days_left"] if z["days_left"] is not None else "",
                    "urgency": z["urgency"],
                    "booth": "",
                    "company": "",
                    "missing_type": "",
                    "item": "",
                })
            else:
                for d in z["missing_detail"]:
                    rows.append({
                        "zone": z["zone"],
                        "owner": z["owner"],
                        "deadline": z["deadline"],
                        "days_left": z["days_left"] if z["days_left"] is not None else "",
                        "urgency": z["urgency"],
                        "booth": d["booth"],
                        "company": d["company"],
                        "missing_type": d["type"],
                        "item": d["item"],
                    })
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv_module.DictWriter(
                f, fieldnames=["zone", "owner", "deadline", "days_left",
                               "urgency", "booth", "company", "missing_type", "item"]
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
    elif path.suffix.lower() == ".json":
        out = []
        for z in zone_details:
            out.append({
                "zone": z["zone"],
                "owner": z["owner"],
                "deadline": z["deadline"],
                "days_left": z["days_left"],
                "urgency": z["urgency"],
                "booth_count": z["booth_count"],
                "missing_categories": z["missing_categories"],
                "missing_detail": z["missing_detail"],
            })
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"total": len(out), "zones": out}, f, ensure_ascii=False, indent=2)

    print_success(f"催办清单已导出: {path}")


def _generate_reminder_markdown(zone_details):
    """生成催办清单 Markdown"""
    urgency_labels = {
        "overdue": "🔥 已逾期",
        "today": "⏰ 今天到期",
        "soon": "📅 3天内到期",
        "normal": "📌 其他",
    }

    md = "# 催办清单\n\n"
    md += f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    total_missing = sum(len(z["missing_categories"]) for z in zone_details)
    md += f"共 **{len(zone_details)}** 个展区需跟进，**{total_missing}** 项缺待处理。\n\n"

    # 按紧急度分组
    groups = {"overdue": [], "today": [], "soon": [], "normal": []}
    for z in zone_details:
        groups[z["urgency"]].append(z)

    for key in ["overdue", "today", "soon", "normal"]:
        items = groups[key]
        if not items:
            continue
        label = urgency_labels[key]
        md += f"## {label} ({len(items)} 个展区)\n\n"

        md += "| 展区 | 负责人 | 截止时间 | 展位 | 缺项类别 |\n"
        md += "|------|--------|----------|------|----------|\n"
        for z in items:
            dl = z["deadline"]
            if z["days_left"] is not None:
                if z["days_left"] < 0:
                    dl = f"{z['deadline']} (逾期{-z['days_left']}天)"
                elif z["days_left"] == 0:
                    dl = f"{z['deadline']} (今天)"
                else:
                    dl = f"{z['deadline']} (剩{z['days_left']}天)"
            missing = "、".join(z["missing_categories"]) if z["missing_categories"] else "-"
            md += f"| {z['zone']} | {z['owner']} | {dl} | {z['booth_count']} | {missing} |\n"
        md += "\n"

    # 明细部分
    md += "## 缺项明细\n\n"
    for z in zone_details:
        if not z["missing_detail"]:
            continue
        md += f"### {z['zone']} ({z['owner']})\n\n"
        md += "| 展位 | 公司 | 缺项类型 | 详情 |\n"
        md += "|------|------|----------|------|\n"
        for d in z["missing_detail"]:
            md += f"| {d['booth']} | {d['company']} | {d['type']} | {d['item']} |\n"
        md += "\n"

    return md


@ops_cli.command("daily-report")
@click.argument("current_issues", type=click.Path(exists=True))
@click.option("--prev", "-p", "prev_issues_path", type=click.Path(exists=True),
              help="上一份问题单，用于对比新增/已解决")
@click.option("--output", "-o", help="导出 Markdown 日报（默认直接在终端展示）")
@click.option("--by-owner", is_flag=True, help="按负责人分组展示")
@click.option("--zone", "-z", help="只看指定展区")
@click.option("--level", "-l", type=click.Choice(["error", "warning", "all"]),
              default="all", help="按问题级别筛选")
@click.pass_context
def daily_report(ctx, current_issues, prev_issues_path, output, by_owner, zone, level):
    """发布日报：对比两份问题单，统计新增/待处理/已确认/已豁免/已解决

    CURRENT_ISSUES 当前问题单文件路径
    """
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    # 加载问题单
    from metaverse.commands.publish import _load_prev_issues
    current = _load_prev_issues(current_issues)
    prev = _load_prev_issues(prev_issues_path) if prev_issues_path else {}

    current_ids = set(current.keys())
    prev_ids = set(prev.keys())

    # 分类
    new_ids = current_ids - prev_ids  # 新增
    resolved_ids = prev_ids - current_ids  # 已解决
    common_ids = current_ids & prev_ids  # 共有

    # 共有的里面再细分确认状态
    confirmed_ids = set()
    waived_ids = set()
    pending_ids = set()
    for iid in common_ids:
        issue = current[iid]
        if issue.get("waived"):
            waived_ids.add(iid)
        elif issue.get("confirmed"):
            confirmed_ids.add(iid)
        else:
            pending_ids.add(iid)

    # 新问题也算待处理
    all_pending_ids = pending_ids | new_ids

    # 按级别筛选
    if level != "all":
        def _filter_level(id_set):
            return {iid for iid in id_set
                    if current.get(iid, prev.get(iid, {})).get("level", "") == level}
        new_ids = _filter_level(new_ids)
        resolved_ids = {iid for iid in resolved_ids
                        if prev[iid].get("level", "") == level}
        confirmed_ids = _filter_level(confirmed_ids)
        waived_ids = _filter_level(waived_ids)
        pending_ids = _filter_level(pending_ids)
        all_pending_ids = _filter_level(all_pending_ids)

    # 按展区筛选
    if zone:
        def _filter_zone(id_set, source):
            return {iid for iid in id_set if source.get(iid, {}).get("zone", "") == zone}
        new_ids = _filter_zone(new_ids, current)
        resolved_ids = _filter_zone(resolved_ids, prev)
        confirmed_ids = _filter_zone(confirmed_ids, current)
        waived_ids = _filter_zone(waived_ids, current)
        pending_ids = _filter_zone(pending_ids, current)
        all_pending_ids = _filter_zone(all_pending_ids, current)

    # 统计汇总
    stats = {
        "total_current": len(current_ids),
        "new": len(new_ids),
        "pending": len(pending_ids),
        "confirmed": len(confirmed_ids),
        "waived": len(waived_ids),
        "resolved": len(resolved_ids),
    }

    # 按展区汇总
    by_zone_stats = {}
    for iid, issue in current.items():
        z = issue.get("zone", "未分配")
        if zone and z != zone:
            continue
        if level != "all" and issue.get("level", "") != level:
            continue
        if z not in by_zone_stats:
            by_zone_stats[z] = {
                "zone": z, "total": 0, "new": 0, "pending": 0,
                "confirmed": 0, "waived": 0, "by_owner": {}
            }
        by_zone_stats[z]["total"] += 1

        if iid in new_ids:
            by_zone_stats[z]["new"] += 1
        elif iid in confirmed_ids:
            by_zone_stats[z]["confirmed"] += 1
        elif iid in waived_ids:
            by_zone_stats[z]["waived"] += 1
        else:
            by_zone_stats[z]["pending"] += 1

        # 按负责人统计
        owner = issue.get("owner", "未分配")
        if owner not in by_zone_stats[z]["by_owner"]:
            by_zone_stats[z]["by_owner"][owner] = {
                "owner": owner, "total": 0, "new": 0, "pending": 0,
                "confirmed": 0, "waived": 0
            }
        by_zone_stats[z]["by_owner"][owner]["total"] += 1
        if iid in new_ids:
            by_zone_stats[z]["by_owner"][owner]["new"] += 1
        elif iid in confirmed_ids:
            by_zone_stats[z]["by_owner"][owner]["confirmed"] += 1
        elif iid in waived_ids:
            by_zone_stats[z]["by_owner"][owner]["waived"] += 1
        else:
            by_zone_stats[z]["by_owner"][owner]["pending"] += 1

    # 按负责人汇总（全局）
    by_owner_stats = {}
    for iid, issue in current.items():
        if zone and issue.get("zone", "") != zone:
            continue
        if level != "all" and issue.get("level", "") != level:
            continue
        owner = issue.get("owner", "未分配")
        if owner not in by_owner_stats:
            by_owner_stats[owner] = {
                "owner": owner, "total": 0, "new": 0, "pending": 0,
                "confirmed": 0, "waived": 0
            }
        by_owner_stats[owner]["total"] += 1
        if iid in new_ids:
            by_owner_stats[owner]["new"] += 1
        elif iid in confirmed_ids:
            by_owner_stats[owner]["confirmed"] += 1
        elif iid in waived_ids:
            by_owner_stats[owner]["waived"] += 1
        else:
            by_owner_stats[owner]["pending"] += 1

    # 输出
    if output and output.endswith(".md"):
        md = _generate_daily_report_markdown(
            stats, by_zone_stats, by_owner_stats,
            current, prev, zone, level, by_owner
        )
        with open(output, "w", encoding="utf-8") as f:
            f.write(md)
        print_success(f"日报已导出: {output}")
    else:
        _print_daily_report(stats, by_zone_stats, by_owner_stats, by_owner)


def _print_daily_report(stats, by_zone_stats, by_owner_stats, by_owner):
    """终端输出日报"""
    console.rule("[bold blue]📊 发布日报[/bold blue]")
    console.print()

    # 总览
    print_info(f"当前问题总数: {stats['total_current']}")
    print_info(f"  🆕 新增: {stats['new']} | ⏳ 待处理: {stats['pending']}")
    print_info(f"  ✅ 已确认: {stats['confirmed']} | 🚫 已豁免: {stats['waived']} | ✨ 已解决: {stats['resolved']}")
    console.print()

    if by_owner:
        # 按负责人
        console.print("[bold cyan]👤 按负责人汇总[/bold cyan]")
        rows = []
        for owner in sorted(by_owner_stats.keys()):
            s = by_owner_stats[owner]
            rows.append([
                owner, str(s["total"]),
                f"[yellow]{s['new']}[/yellow]",
                f"[white]{s['pending']}[/white]",
                f"[green]{s['confirmed']}[/green]",
                f"[dim]{s['waived']}[/dim]",
            ])
        print_table("", ["负责人", "总数", "新增", "待处理", "已确认", "已豁免"], rows)
    else:
        # 按展区
        console.print("[bold cyan]📍 按展区汇总[/bold cyan]")
        rows = []
        for z in sorted(by_zone_stats.keys()):
            s = by_zone_stats[z]
            rows.append([
                z, str(s["total"]),
                f"[yellow]{s['new']}[/yellow]",
                f"[white]{s['pending']}[/white]",
                f"[green]{s['confirmed']}[/green]",
                f"[dim]{s['waived']}[/dim]",
            ])
        print_table("", ["展区", "总数", "新增", "待处理", "已确认", "已豁免"], rows)
    console.print()


def _generate_daily_report_markdown(stats, by_zone_stats, by_owner_stats,
                                    current, prev, zone, level, by_owner):
    """生成 Markdown 格式日报"""
    today = datetime.now().strftime("%Y-%m-%d")
    md = f"# 发布日报 - {today}\n\n"
    md += "> 自动生成，用于每日发布进度同步\n\n"

    # 总览
    md += "## 📊 今日概览\n\n"
    md += f"| 指标 | 数量 |\n|------|------|\n"
    md += f"| 当前问题总数 | {stats['total_current']} |\n"
    md += f"| 🆕 新增问题 | {stats['new']} |\n"
    md += f"| ⏳ 待处理 | {stats['pending']} |\n"
    md += f"| ✅ 已确认 | {stats['confirmed']} |\n"
    md += f"| 🚫 已豁免 | {stats['waived']} |\n"
    md += f"| ✨ 已解决（相比上次） | {stats['resolved']} |\n"
    md += "\n"

    if by_owner:
        # 按负责人明细
        md += "## 👤 按负责人汇总\n\n"
        md += "| 负责人 | 总数 | 新增 | 待处理 | 已确认 | 已豁免 |\n"
        md += "|--------|------|------|--------|--------|--------|\n"
        for owner in sorted(by_owner_stats.keys()):
            s = by_owner_stats[owner]
            md += f"| {owner} | {s['total']} | {s['new']} | {s['pending']} | {s['confirmed']} | {s['waived']} |\n"
        md += "\n"
    else:
        # 按展区明细
        md += "## 📍 按展区汇总\n\n"
        md += "| 展区 | 总数 | 新增 | 待处理 | 已确认 | 已豁免 |\n"
        md += "|------|------|------|--------|--------|--------|\n"
        for z in sorted(by_zone_stats.keys()):
            s = by_zone_stats[z]
            md += f"| {z} | {s['total']} | {s['new']} | {s['pending']} | {s['confirmed']} | {s['waived']} |\n"
        md += "\n"

        # 展区下的负责人明细
        md += "## 📋 各展区负责人明细\n\n"
        for z in sorted(by_zone_stats.keys()):
            s = by_zone_stats[z]
            md += f"### 展区 {z} ({s['total']} 个问题)\n\n"
            md += "| 负责人 | 总数 | 新增 | 待处理 | 已确认 | 已豁免 |\n"
            md += "|--------|------|------|--------|--------|--------|\n"
            for owner in sorted(s["by_owner"].keys()):
                o = s["by_owner"][owner]
                md += f"| {owner} | {o['total']} | {o['new']} | {o['pending']} | {o['confirmed']} | {o['waived']} |\n"
            md += "\n"

    return md


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
