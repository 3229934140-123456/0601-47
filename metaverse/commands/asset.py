import click
import os
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
@click.pass_context
def list_assets(ctx, asset_type, booth, zone):
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

    if not assets:
        print_warning("暂无资源")
        return

    rows = [
        [a["id"], a["name"], a["type"], a.get("booth_id", ""),
         f"{a['size']/1024:.1f}KB", a["status"]]
        for a in assets
    ]
    print_table(f"资源清单 ({len(assets)} 个)",
                ["ID", "名称", "类型", "展位", "大小", "状态"], rows)


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
