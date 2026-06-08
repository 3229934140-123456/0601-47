import click
import os
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
def asset_cli(ctx):
    """资源管理 - 上传模型海报、预览清单、检查缺失"""
    pass


@asset_cli.command("upload")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--type", "-t", "asset_type", required=True,
              type=click.Choice(["model", "poster", "logo", "video"]),
              help="资源类型")
@click.option("--booth", "-b", help="关联展位号")
@click.option("--name", "-n", help="资源名称")
@click.pass_context
def upload_asset(ctx, file_path, asset_type, booth, name):
    """上传资源文件（模型/海报等）

    FILE_PATH 资源文件路径
    """
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    src = Path(file_path)
    if not src.exists():
        print_error(f"文件不存在: {file_path}")
        raise click.Abort()

    type_dirs = {
        "model": "assets/models",
        "poster": "assets/posters",
        "logo": "assets/logos",
        "video": "assets/videos",
    }
    dest_dir = Path(project_path) / type_dirs[asset_type]
    ensure_dir(dest_dir)

    dest_file = dest_dir / (name or src.name)
    import shutil
    shutil.copy2(src, dest_file)

    file_hash = compute_file_hash(dest_file)
    file_size = dest_file.stat().st_size

    config = SceneConfig(project_path)
    assets = config.get("assets", [])
    asset_data = {
        "id": f"asset-{len(assets)+1:04d}",
        "name": name or src.stem,
        "type": asset_type,
        "filename": dest_file.name,
        "path": str(dest_file.relative_to(Path(project_path))),
        "size": file_size,
        "hash": file_hash,
        "booth_id": booth or "",
        "status": "uploaded",
    }
    assets.append(asset_data)
    config.set("assets", assets)

    if booth:
        booths = config.get("booths", [])
        for b in booths:
            if b["id"] == booth:
                if asset_type == "model":
                    b["model"] = asset_data["path"]
                elif asset_type == "poster":
                    b["poster"] = asset_data["path"]
                elif asset_type == "logo":
                    b["logo"] = asset_data["path"]
                break
        config.set("booths", booths)

    config.save()

    print_success(f"资源上传成功: {dest_file.name}")
    print_info(f"类型: {asset_type}")
    print_info(f"大小: {file_size / 1024:.2f} KB")
    if booth:
        print_info(f"关联展位: {booth}")


@asset_cli.command("list")
@click.option("--type", "-t", "asset_type",
              type=click.Choice(["model", "poster", "logo", "video"]),
              help="按类型过滤")
@click.option("--booth", "-b", help="按展位过滤")
@click.option("--zone", "-z", help="按展区过滤")
@click.option("--status", "-s", help="按状态过滤")
@click.pass_context
def list_assets(ctx, asset_type, booth, zone, status):
    """预览资源清单"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    assets = config.get("assets", [])
    booths = config.get("booths", [])

    if asset_type:
        assets = [a for a in assets if a["type"] == asset_type]
    if booth:
        assets = [a for a in assets if a.get("booth_id") == booth]
    if zone:
        zone_booth_ids = {b["id"] for b in booths if b.get("zone") == zone}
        assets = [a for a in assets if a.get("booth_id") in zone_booth_ids]
    if status:
        assets = [a for a in assets if a.get("status", "") == status]

    if not assets:
        print_warning("暂无资源")
        return

    rows = [
        [a["id"], a["name"], a["type"], a.get("booth_id", ""),
         f"{a['size']/1024:.1f}KB", a.get("status", "uploaded")]
        for a in assets
    ]
    print_table(f"资源清单 ({len(assets)} 个)",
                ["ID", "名称", "类型", "展位", "大小", "状态"], rows)


@asset_cli.command("set-status")
@click.argument("status")
@click.option("--ids", multiple=True, help="指定资源ID，多个用逗号分隔或多次指定")
@click.option("--type", "-t", "asset_type",
              type=click.Choice(["model", "poster", "logo", "video"]),
              help="按类型批量更新")
@click.option("--zone", "-z", help="按展区批量更新")
@click.option("--booth", "-b", help="按展位批量更新")
@click.pass_context
def set_status(ctx, status, ids, asset_type, zone, booth):
    """批量更新资源状态

    STATUS 状态值，如 confirmed、pending、draft
    """
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    assets = config.get("assets", [])
    booths = config.get("booths", [])

    target_ids = parse_ids(ids) if ids else set()
    zone_booth_ids = {b["id"] for b in booths if b.get("zone") == zone} if zone else None

    updated = 0
    for asset in assets:
        aid = asset.get("id", "")
        # 判断是否匹配筛选条件
        match = False
        if target_ids and aid in target_ids:
            match = True
        elif not target_ids:
            type_match = not asset_type or asset.get("type") == asset_type
            zone_match = not zone or asset.get("booth_id") in zone_booth_ids
            booth_match = not booth or asset.get("booth_id") == booth
            if type_match and zone_match and booth_match:
                match = True

        if match:
            asset["status"] = status
            updated += 1

    if updated == 0:
        print_warning("没有匹配的资源")
        return

    config.set("assets", assets)
    config.save()
    print_success(f"已更新 {updated} 个资源的状态为: {status}")


@asset_cli.command("check")
@click.option("--zone", "-z", help="按展区检查")
@click.pass_context
def check_missing(ctx, zone):
    """检查缺失文件"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    booths = config.get("booths", [])
    assets = config.get("assets", [])
    asset_paths = {a["path"] for a in assets}

    if zone:
        booths = [b for b in booths if b.get("zone") == zone]

    missing = []
    for booth in booths:
        booth_id = booth["id"]
        for field in ["model", "poster", "logo"]:
            path = booth.get(field, "")
            if path and path not in asset_paths:
                full_path = Path(project_path) / path
                if not full_path.exists():
                    missing.append({
                        "booth": booth_id,
                        "type": field,
                        "path": path,
                        "reason": "文件不存在"
                    })

    # 检查资源记录中的文件是否实际存在
    for asset in assets:
        full_path = Path(project_path) / asset["path"]
        if not full_path.exists():
            missing.append({
                "booth": asset.get("booth_id", ""),
                "type": asset["type"],
                "path": asset["path"],
                "reason": "记录存在但文件丢失"
            })

    if not missing:
        print_success("所有资源文件完整，无缺失")
        return

    print_warning(f"发现 {len(missing)} 个缺失/异常文件")
    rows = [[m["booth"], m["type"], m["path"], m["reason"]] for m in missing]
    print_table("缺失文件列表", ["展位", "类型", "路径", "原因"], rows)


@asset_cli.command("export-status")
@click.option("--output", "-o", help="输出文件路径")
@click.option("--zone", "-z", help="按展区过滤")
@click.option("--type", "-t", "asset_type",
              type=click.Choice(["model", "poster", "logo", "video"]),
              help="按类型过滤")
@click.option("--format", "-f", "fmt", default="csv",
              type=click.Choice(["csv", "json"]), help="输出格式")
@click.pass_context
def export_status(ctx, output, zone, asset_type, fmt):
    """导出资源状态清单，发给展区负责人确认"""
    import csv as csv_module
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    assets = config.get("assets", [])
    booths = config.get("booths", [])

    if zone:
        zone_booth_ids = {b["id"] for b in booths if b.get("zone") == zone}
        assets = [a for a in assets if a.get("booth_id") in zone_booth_ids]
    if asset_type:
        assets = [a for a in assets if a["type"] == asset_type]

    if not output:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = fmt
        output = f"asset_status_{timestamp}.{ext}"

    output_path = Path(output)

    if fmt == "csv":
        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv_module.DictWriter(
                f, fieldnames=["id", "name", "type", "booth_id", "filename", "status"],
                extrasaction="ignore"
            )
            writer.writeheader()
            for a in assets:
                writer.writerow(a)

    elif fmt == "json":
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "total": len(assets),
                "assets": assets,
            }, f, ensure_ascii=False, indent=2)

    print_success(f"已导出 {len(assets)} 个资源的状态清单: {output_path}")


@asset_cli.command("import-status")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--format", "-f", "fmt", default="auto",
              type=click.Choice(["auto", "csv", "json"]), help="文件格式")
@click.option("--status-field", default="status", help="状态字段名")
@click.option("--id-field", default="id", help="ID字段名")
@click.pass_context
def import_status(ctx, file_path, fmt, status_field, id_field):
    """从 CSV/JSON 批量导入资源状态变更

    FILE_PATH 状态文件路径
    """
    import csv as csv_module
    import json as json_module
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
            data = json_module.load(f)
            items = data if isinstance(data, list) else data.get("assets", [])
            for item in items:
                rid = item.get(id_field, "").strip()
                status = item.get(status_field, "").strip()
                if rid and status:
                    status_updates[rid] = status

    config = SceneConfig(project_path)
    assets = config.get("assets", [])

    updated = 0
    not_found = []
    for asset in assets:
        aid = asset.get("id", "")
        if aid in status_updates:
            asset["status"] = status_updates[aid]
            updated += 1

    not_found = [rid for rid in status_updates if not any(a.get("id") == rid for a in assets)]

    config.set("assets", assets)
    config.save()

    print_success(f"已更新 {updated} 个资源的状态")
    if not_found:
        print_warning(f"未找到的资源ID ({len(not_found)} 个): {', '.join(not_found[:5])}")
        if len(not_found) > 5:
            print_warning(f"  ... 另有 {len(not_found)-5} 个未显示")
