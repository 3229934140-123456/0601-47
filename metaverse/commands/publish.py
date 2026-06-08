import click
import shutil
import json
import zipfile
from datetime import datetime
from pathlib import Path
from metaverse.config import SceneConfig
from metaverse.utils import (
    print_success,
    print_error,
    print_warning,
    print_info,
    print_table,
    ensure_dir,
    is_project_dir,
    console,
)


@click.group()
@click.pass_context
def publish_cli(ctx):
    """发布管理 - 打包发布版本、回滚上一次发布"""
    pass


@publish_cli.command("build")
@click.option("--version", "-v", help="版本号，自动生成则留空")
@click.option("--note", "-n", help="发布说明")
@click.option("--skip-check", is_flag=True, help="跳过资源完整性检查")
@click.pass_context
def build(ctx, version, note, skip_check):
    """打包发布版本"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)

    if not skip_check:
        print_info("检查资源完整性...")
        missing = _check_resources(project_path, config)
        if missing:
            print_warning(f"发现 {len(missing)} 个缺失资源，请确认后使用 --skip-check 跳过")
            if not click.confirm("是否继续打包？", default=False):
                raise click.Abort()

    if not version:
        history = config.get("publish_history", [])
        version = f"v1.0.{len(history)}"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    release_name = f"{version}_{timestamp}"
    release_dir = Path(project_path) / "releases" / release_name
    ensure_dir(release_dir)

    # 复制资源文件
    print_info("复制资源文件...")
    assets_src = Path(project_path) / "assets"
    if assets_src.exists():
        shutil.copytree(assets_src, release_dir / "assets", dirs_exist_ok=True)

    # 复制展位数据
    booths_src = Path(project_path) / "booths"
    if booths_src.exists():
        shutil.copytree(booths_src, release_dir / "booths", dirs_exist_ok=True)

    # 生成发布配置
    release_config = {
        "version": version,
        "timestamp": timestamp,
        "note": note or "",
        "scene": config.get("scene", {}),
        "booths": config.get("booths", []),
        "assets": config.get("assets", []),
        "avatars": config.get("avatars", []),
        "schedules": config.get("schedules", []),
        "stats": {
            "booth_count": len(config.get("booths", [])),
            "asset_count": len(config.get("assets", [])),
            "avatar_count": len(config.get("avatars", [])),
            "schedule_count": len(config.get("schedules", [])),
        },
    }

    with open(release_dir / "release.json", "w", encoding="utf-8") as f:
        json.dump(release_config, f, ensure_ascii=False, indent=2)

    # 打包成 zip
    print_info("打包中...")
    zip_path = Path(project_path) / "releases" / f"{release_name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in release_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(release_dir)
                zf.write(file_path, arcname)

    # 更新发布历史
    history = config.get("publish_history", [])
    history.append({
        "version": version,
        "timestamp": timestamp,
        "note": note or "",
        "path": str(zip_path.relative_to(Path(project_path))),
        "status": "active",
    })
    if len(history) > 1:
        history[-2]["status"] = "archived"

    config.set("publish_history", history)
    config.set("scene.status", "published")
    config.save()

    print_success(f"版本 {version} 发布成功")
    print_info(f"发布包: {zip_path}")
    print_info(f"展位: {release_config['stats']['booth_count']} 个")
    print_info(f"资源: {release_config['stats']['asset_count']} 个")


@publish_cli.command("list")
@click.pass_context
def list_publish(ctx):
    """列出发布历史"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    history = config.get("publish_history", [])

    if not history:
        print_warning("暂无发布记录")
        return

    rows = [
        [h["version"], h["timestamp"], h.get("note", ""), h.get("status", "")]
        for h in reversed(history)
    ]
    print_table("发布历史", ["版本", "时间", "说明", "状态"], rows)


@publish_cli.command("rollback")
@click.option("--version", "-v", help="回滚到指定版本，默认回滚到上一版本")
@click.pass_context
def rollback(ctx, version):
    """回滚到上一次发布"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    history = config.get("publish_history", [])

    if len(history) < 2:
        print_error("发布历史不足，无法回滚")
        raise click.Abort()

    if version:
        target = None
        for h in history:
            if h["version"] == version:
                target = h
                break
        if not target:
            print_error(f"未找到版本: {version}")
            raise click.Abort()
    else:
        target = history[-2]

    # 恢复配置
    release_zip = Path(project_path) / target["path"]
    if not release_zip.exists():
        print_error(f"发布包不存在: {release_zip}")
        raise click.Abort()

    extract_dir = Path(project_path) / "releases" / "_rollback_tmp"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)

    with zipfile.ZipFile(release_zip, "r") as zf:
        zf.extractall(extract_dir)

    with open(extract_dir / "release.json", "r", encoding="utf-8") as f:
        release_data = json.load(f)

    config.set("scene", release_data["scene"])
    config.set("booths", release_data["booths"])
    config.set("assets", release_data["assets"])
    config.set("avatars", release_data["avatars"])
    config.set("schedules", release_data["schedules"])
    config.save()

    # 恢复资源文件
    assets_src = extract_dir / "assets"
    assets_dst = Path(project_path) / "assets"
    if assets_src.exists():
        if assets_dst.exists():
            shutil.rmtree(assets_dst)
        shutil.copytree(assets_src, assets_dst)

    shutil.rmtree(extract_dir)

    # 更新历史状态
    for h in history:
        if h["version"] == target["version"]:
            h["status"] = "active"
        else:
            h["status"] = "archived"
    config.set("publish_history", history)
    config.save()

    print_success(f"已回滚到版本 {target['version']}")
    print_info(f"发布时间: {target['timestamp']}")


def _check_resources(project_path: str, config: SceneConfig) -> list:
    """检查资源完整性，返回缺失列表"""
    missing = []
    assets = config.get("assets", [])
    for asset in assets:
        full_path = Path(project_path) / asset["path"]
        if not full_path.exists():
            missing.append({"path": asset["path"], "reason": "文件不存在"})
    return missing
