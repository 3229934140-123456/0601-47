import click
from datetime import datetime
from metaverse.config import SceneConfig
from metaverse.utils import (
    print_success,
    print_error,
    print_warning,
    print_info,
    print_table,
    is_project_dir,
)


@click.group()
@click.pass_context
def schedule_cli(ctx):
    """日程管理 - 安排直播时段"""
    pass


@schedule_cli.command("add")
@click.option("--title", "-t", required=True, help="直播标题")
@click.option("--start", "-s", required=True, help="开始时间 (YYYY-MM-DD HH:MM)")
@click.option("--end", "-e", required=True, help="结束时间 (YYYY-MM-DD HH:MM)")
@click.option("--speaker", help="主讲人")
@click.option("--booth", "-b", help="所属展位")
@click.option("--zone", "-z", help="所属展区")
@click.option("--type", "schedule_type", default="live",
              type=click.Choice(["live", "workshop", "keynote", "panel"]),
              help="活动类型")
@click.pass_context
def add_schedule(ctx, title, start, end, speaker, booth, zone, schedule_type):
    """添加直播/活动时段"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    try:
        start_dt = datetime.strptime(start, "%Y-%m-%d %H:%M")
        end_dt = datetime.strptime(end, "%Y-%m-%d %H:%M")
    except ValueError:
        print_error("时间格式错误，请使用 YYYY-MM-DD HH:MM 格式")
        raise click.Abort()

    if end_dt <= start_dt:
        print_error("结束时间必须晚于开始时间")
        raise click.Abort()

    config = SceneConfig(project_path)
    schedules = config.get("schedules", [])

    schedule_data = {
        "id": f"sch-{len(schedules)+1:04d}",
        "title": title,
        "start": start,
        "end": end,
        "speaker": speaker or "",
        "booth_id": booth or "",
        "zone": zone or "",
        "type": schedule_type,
        "status": "scheduled",
    }
    schedules.append(schedule_data)
    config.set("schedules", schedules)
    config.save()

    print_success(f"已添加日程: {title}")
    print_info(f"时间: {start} ~ {end}")
    if speaker:
        print_info(f"主讲人: {speaker}")


@schedule_cli.command("list")
@click.option("--zone", "-z", help="按展区过滤")
@click.option("--booth", "-b", help="按展位过滤")
@click.option("--type", "-t", "schedule_type",
              type=click.Choice(["live", "workshop", "keynote", "panel"]),
              help="按类型过滤")
@click.pass_context
def list_schedules(ctx, zone, booth, schedule_type):
    """列出所有日程安排"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    schedules = config.get("schedules", [])

    if zone:
        schedules = [s for s in schedules if s.get("zone") == zone]
    if booth:
        schedules = [s for s in schedules if s.get("booth_id") == booth]
    if schedule_type:
        schedules = [s for s in schedules if s.get("type") == schedule_type]

    if not schedules:
        print_warning("暂无日程安排")
        return

    schedules_sorted = sorted(schedules, key=lambda x: x.get("start", ""))
    rows = [
        [s["id"], s["title"], s["start"], s["end"],
         s.get("speaker", ""), s.get("type", ""), s.get("zone", "")]
        for s in schedules_sorted
    ]
    print_table(f"日程列表 ({len(schedules)} 场)",
                ["ID", "标题", "开始", "结束", "主讲人", "类型", "展区"], rows)


@schedule_cli.command("import")
@click.argument("file_path", type=click.Path(exists=True))
@click.pass_context
def import_schedules(ctx, file_path):
    """批量导入日程（JSON格式）"""
    import json
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data if isinstance(data, list) else data.get("schedules", [])
    config = SceneConfig(project_path)
    schedules = config.get("schedules", [])
    added = 0

    for item in items:
        schedule_data = {
            "id": f"sch-{len(schedules)+1:04d}",
            "title": item.get("title", ""),
            "start": item.get("start", ""),
            "end": item.get("end", ""),
            "speaker": item.get("speaker", ""),
            "booth_id": item.get("booth_id", ""),
            "zone": item.get("zone", ""),
            "type": item.get("type", "live"),
            "status": "scheduled",
        }
        schedules.append(schedule_data)
        added += 1

    config.set("schedules", schedules)
    config.save()
    print_success(f"批量导入 {added} 场日程")
