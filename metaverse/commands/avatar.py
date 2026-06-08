import click
import shutil
import json
from pathlib import Path
from metaverse.config import SceneConfig
from metaverse.utils import (
    print_success,
    print_error,
    print_warning,
    print_info,
    print_table,
    ensure_dir,
    compute_file_hash,
    is_project_dir,
    parse_ids,
)


@click.group()
@click.pass_context
def avatar_cli(ctx):
    """嘉宾管理 - 设置嘉宾头像和名牌"""
    pass


@avatar_cli.command("add")
@click.argument("name")
@click.option("--avatar", "-a", type=click.Path(exists=True), help="头像图片路径")
@click.option("--title", "-t", help="头衔/职位")
@click.option("--company", "-c", help="公司")
@click.option("--booth", "-b", help="所属展位")
@click.option("--nameplate", help="名牌文字")
@click.pass_context
def add_avatar(ctx, name, avatar, title, company, booth, nameplate):
    """添加嘉宾头像和名牌

    NAME 嘉宾姓名
    """
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    avatar_path = ""
    if avatar:
        src = Path(avatar)
        dest_dir = Path(project_path) / "assets" / "avatars"
        ensure_dir(dest_dir)
        dest_file = dest_dir / f"{name}{src.suffix}"
        shutil.copy2(src, dest_file)
        avatar_path = str(dest_file.relative_to(Path(project_path)))

    config = SceneConfig(project_path)
    avatars = config.get("avatars", [])

    avatar_data = {
        "id": f"guest-{len(avatars)+1:04d}",
        "name": name,
        "title": title or "",
        "company": company or "",
        "booth_id": booth or "",
        "avatar": avatar_path,
        "nameplate": nameplate or name,
    }
    avatars.append(avatar_data)
    config.set("avatars", avatars)
    config.save()

    print_success(f"嘉宾 {name} 添加成功")
    if avatar:
        print_info(f"头像: {avatar_path}")
    if nameplate:
        print_info(f"名牌: {nameplate}")


@avatar_cli.command("list")
@click.option("--booth", "-b", help="按展位过滤")
@click.option("--company", "-c", help="按公司过滤")
@click.option("--zone", "-z", help="按展区过滤")
@click.option("--status", "-s", help="按状态过滤")
@click.pass_context
def list_avatars(ctx, booth, company, zone, status):
    """列出所有嘉宾"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    avatars = config.get("avatars", [])
    booths = config.get("booths", [])

    if booth:
        avatars = [a for a in avatars if a.get("booth_id") == booth]
    if company:
        avatars = [a for a in avatars if company.lower() in a.get("company", "").lower()]
    if zone:
        zone_booth_ids = {b["id"] for b in booths if b.get("zone") == zone}
        avatars = [a for a in avatars if a.get("booth_id") in zone_booth_ids]
    if status:
        avatars = [a for a in avatars if a.get("status", "") == status]

    if not avatars:
        print_warning("暂无嘉宾数据")
        return

    rows = [
        [a["id"], a["name"], a.get("title", ""), a.get("company", ""),
         a.get("booth_id", ""), "✓" if a.get("avatar") else "✗",
         a.get("status", "active")]
        for a in avatars
    ]
    print_table(f"嘉宾列表 ({len(avatars)} 人)",
                ["ID", "姓名", "头衔", "公司", "展位", "头像", "状态"], rows)


@avatar_cli.command("set-status")
@click.argument("status")
@click.option("--ids", multiple=True, help="指定嘉宾ID")
@click.option("--zone", "-z", help="按展区批量更新")
@click.option("--booth", "-b", help="按展位批量更新")
@click.option("--company", "-c", help="按公司批量更新")
@click.pass_context
def set_status(ctx, status, ids, zone, booth, company):
    """批量更新嘉宾状态

    STATUS 状态值，如 confirmed、pending、draft
    """
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    avatars = config.get("avatars", [])
    booths = config.get("booths", [])

    target_ids = parse_ids(ids) if ids else set()
    zone_booth_ids = {b["id"] for b in booths if b.get("zone") == zone} if zone else None

    updated = 0
    for avatar in avatars:
        aid = avatar.get("id", "")
        match = False
        if target_ids and aid in target_ids:
            match = True
        elif not target_ids:
            zone_match = not zone or avatar.get("booth_id") in zone_booth_ids
            booth_match = not booth or avatar.get("booth_id") == booth
            company_match = not company or company.lower() in avatar.get("company", "").lower()
            if zone_match and booth_match and company_match:
                match = True

        if match:
            avatar["status"] = status
            updated += 1

    if updated == 0:
        print_warning("没有匹配的嘉宾")
        return

    config.set("avatars", avatars)
    config.save()
    print_success(f"已更新 {updated} 位嘉宾的状态为: {status}")


@avatar_cli.command("set-nameplate")
@click.argument("avatar_id")
@click.option("--text", "-t", required=True, help="名牌文字")
@click.pass_context
def set_nameplate(ctx, avatar_id, text):
    """设置嘉宾名牌文字"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    avatars = config.get("avatars", [])

    found = False
    for a in avatars:
        if a["id"] == avatar_id:
            a["nameplate"] = text
            found = True
            break

    if not found:
        print_error(f"未找到嘉宾: {avatar_id}")
        raise click.Abort()

    config.set("avatars", avatars)
    config.save()
    print_success(f"嘉宾 {avatar_id} 名牌已更新: {text}")


@avatar_cli.command("import")
@click.argument("file_path", type=click.Path(exists=True))
@click.pass_context
def import_avatars(ctx, file_path):
    """批量导入嘉宾信息（JSON格式）"""
    import json
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    guests = data if isinstance(data, list) else data.get("guests", [])
    config = SceneConfig(project_path)
    avatars = config.get("avatars", [])
    added = 0

    for guest in guests:
        name = guest.get("name", "")
        if not name:
            continue
        avatar_data = {
            "id": f"guest-{len(avatars)+1:04d}",
            "name": name,
            "title": guest.get("title", ""),
            "company": guest.get("company", ""),
            "booth_id": guest.get("booth_id", ""),
            "avatar": guest.get("avatar", ""),
            "nameplate": guest.get("nameplate", name),
        }
        avatars.append(avatar_data)
        added += 1

    config.set("avatars", avatars)
    config.save()
    print_success(f"批量导入 {added} 位嘉宾")


@avatar_cli.command("export-status")
@click.option("--output", "-o", help="输出文件路径")
@click.option("--zone", "-z", help="按展区过滤")
@click.option("--booth", "-b", help="按展位过滤")
@click.option("--format", "-f", "fmt", default="csv",
              type=click.Choice(["csv", "json"]), help="输出格式")
@click.pass_context
def export_status(ctx, output, zone, booth, fmt):
    """导出嘉宾状态清单，发给展区负责人确认"""
    import csv as csv_module
    from datetime import datetime
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    avatars = config.get("avatars", [])
    booths = config.get("booths", [])

    if zone:
        zone_booth_ids = {b["id"] for b in booths if b.get("zone") == zone}
        avatars = [a for a in avatars if a.get("booth_id") in zone_booth_ids]
    if booth:
        avatars = [a for a in avatars if a.get("booth_id") == booth]

    if not output:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = f"avatar_status_{timestamp}.{fmt}"

    output_path = Path(output)

    if fmt == "csv":
        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv_module.DictWriter(
                f, fieldnames=["id", "name", "title", "company", "booth_id", "status"],
                extrasaction="ignore"
            )
            writer.writeheader()
            for a in avatars:
                writer.writerow(a)

    elif fmt == "json":
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "total": len(avatars),
                "avatars": avatars,
            }, f, ensure_ascii=False, indent=2)

    print_success(f"已导出 {len(avatars)} 位嘉宾的状态清单: {output_path}")


@avatar_cli.command("import-status")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--format", "-f", "fmt", default="auto",
              type=click.Choice(["auto", "csv", "json"]), help="文件格式")
@click.option("--status-field", default="status", help="状态字段名")
@click.option("--id-field", default="id", help="ID字段名")
@click.pass_context
def import_status(ctx, file_path, fmt, status_field, id_field):
    """从 CSV/JSON 批量导入嘉宾状态变更

    FILE_PATH 状态文件路径
    """
    import csv as csv_module
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    path = Path(file_path)
    if fmt == "auto":
        if path.suffix.lower() == ".csv":
            fmt = "csv"
        elif path.suffix.lower() == ".json":
            fmt = "json"
        else:
            print_error(f"无法自动识别格式: {path.suffix}")
            raise click.Abort()

    status_updates = {}
    if fmt == "csv":
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv_module.DictReader(f)
            for row in reader:
                rid = row.get(id_field, "").strip()
                status = row.get(status_field, "").strip()
                if rid and status:
                    status_updates[rid] = status
    elif fmt == "json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            items = data if isinstance(data, list) else data.get("avatars", [])
            for item in items:
                rid = item.get(id_field, "").strip()
                status = item.get(status_field, "").strip()
                if rid and status:
                    status_updates[rid] = status

    config = SceneConfig(project_path)
    avatars = config.get("avatars", [])

    updated = 0
    not_found = []
    for avatar in avatars:
        aid = avatar.get("id", "")
        if aid in status_updates:
            avatar["status"] = status_updates[aid]
            updated += 1

    not_found = [rid for rid in status_updates if not any(a.get("id") == rid for a in avatars)]

    config.set("avatars", avatars)
    config.save()

    print_success(f"已更新 {updated} 位嘉宾的状态")
    if not_found:
        print_warning(f"未找到的嘉宾ID ({len(not_found)} 个): {', '.join(not_found[:5])}")
        if len(not_found) > 5:
            print_warning(f"  ... 另有 {len(not_found)-5} 个未显示")
