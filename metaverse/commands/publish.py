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
    validate_booth_id,
    console,
)


@click.group()
@click.pass_context
def publish_cli(ctx):
    """发布管理 - 打包发布版本、回滚、版本对比"""
    pass


@publish_cli.command("build")
@click.option("--version", "-v", help="版本号，自动生成则留空")
@click.option("--note", "-n", help="发布说明")
@click.option("--dry-run", is_flag=True, help="只做预检，不实际打包发布")
@click.option("--skip-check", is_flag=True, help="跳过所有检查")
@click.option("--strict", is_flag=True, help="严格模式，发现任何问题都终止发布")
@click.pass_context
def build(ctx, version, note, dry_run, skip_check, strict):
    """打包发布版本（支持预检和 dry-run）"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)

    if not skip_check:
        print_info("开始发布预检...")
        issues = run_preflight_checks(project_path, config)

        error_count = sum(1 for i in issues if i["level"] == "error")
        warning_count = sum(1 for i in issues if i["level"] == "warning")

        if not issues:
            print_success("预检通过，未发现任何问题")
        else:
            print_warning(f"预检完成: 发现 {error_count} 个错误，{warning_count} 个警告")
            print_issue_table(issues)

            if strict and error_count > 0:
                print_error("严格模式下发现错误，终止发布")
                raise click.Abort()

            if not dry_run and not click.confirm("是否继续打包？", default=not error_count):
                raise click.Abort()

    if dry_run:
        print_info("Dry-run 模式，已完成预检，未执行打包")
        return

    if not version:
        history = config.get("publish_history", [])
        version = f"v1.0.{len(history)}"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    release_name = f"{version}_{timestamp}"
    release_dir = Path(project_path) / "releases" / release_name
    ensure_dir(release_dir)

    print_info("复制资源文件...")
    assets_src = Path(project_path) / "assets"
    if assets_src.exists():
        shutil.copytree(assets_src, release_dir / "assets", dirs_exist_ok=True)

    booths_src = Path(project_path) / "booths"
    if booths_src.exists():
        shutil.copytree(booths_src, release_dir / "booths", dirs_exist_ok=True)

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

    print_info("打包中...")
    zip_path = Path(project_path) / "releases" / f"{release_name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in release_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(release_dir)
                zf.write(file_path, arcname)

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


@publish_cli.command("check")
@click.option("--detail", "-d", is_flag=True, help="显示详细问题")
@click.pass_context
def preflight_check(ctx, detail):
    """发布前预检：检查展位、资源、日程等是否符合要求"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    issues = run_preflight_checks(project_path, config)

    error_count = sum(1 for i in issues if i["level"] == "error")
    warning_count = sum(1 for i in issues if i["level"] == "warning")

    if not issues:
        print_success("预检通过，未发现任何问题")
        return

    print_warning(f"发现 {error_count} 个错误，{warning_count} 个警告")
    print_issue_table(issues)


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

    assets_src = extract_dir / "assets"
    assets_dst = Path(project_path) / "assets"
    if assets_src.exists():
        if assets_dst.exists():
            shutil.rmtree(assets_dst)
        shutil.copytree(assets_src, assets_dst)

    shutil.rmtree(extract_dir)

    for h in history:
        if h["version"] == target["version"]:
            h["status"] = "active"
        else:
            h["status"] = "archived"
    config.set("publish_history", history)
    config.save()

    print_success(f"已回滚到版本 {target['version']}")
    print_info(f"发布时间: {target['timestamp']}")


@publish_cli.command("diff")
@click.argument("v1")
@click.argument("v2")
@click.option("--output", "-o", help="导出差异报告文件路径")
@click.option("--format", "-f", "fmt", default="json",
              type=click.Choice(["json", "html"]), help="报告格式")
@click.pass_context
def diff_versions(ctx, v1, v2, output, fmt):
    """对比两个版本的差异

    V1 旧版本号
    V2 新版本号
    """
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    history = config.get("publish_history", [])

    data_old = load_release_data(project_path, history, v1)
    data_new = load_release_data(project_path, history, v2)

    if not data_old or not data_new:
        raise click.Abort()

    diff = compute_diff(data_old, data_new, v1, v2)
    print_diff_summary(diff)

    if output:
        output_path = Path(output)
        if fmt == "json":
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(diff, f, ensure_ascii=False, indent=2)
        elif fmt == "html":
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(generate_diff_html(diff))
        print_success(f"差异报告已导出: {output_path}")


def run_preflight_checks(project_path: str, config: SceneConfig) -> list:
    """执行完整的发布前预检，返回问题列表"""
    issues = []

    booths = config.get("booths", [])
    assets = config.get("assets", [])
    avatars = config.get("avatars", [])
    schedules = config.get("schedules", [])
    zones = config.get("scene.zones", [])

    # 1. 展位编号校验
    for booth in booths:
        bid = booth.get("id", "")
        valid, msg = validate_booth_id(bid)
        if not valid:
            issues.append({
                "category": "展位",
                "level": "error",
                "item": bid,
                "message": f"展位编号格式错误: {msg}"
            })

    # 2. 展商资料必填项
    required_fields = ["company", "contact"]
    for booth in booths:
        bid = booth.get("id", "unknown")
        for field in required_fields:
            if not booth.get(field):
                issues.append({
                    "category": "展商资料",
                    "level": "warning",
                    "item": bid,
                    "message": f"缺少必填项: {field}"
                })

    # 3. 资源类型匹配 & 文件存在性
    asset_paths = {a["path"] for a in assets}
    valid_extensions = {
        "model": [".glb", ".gltf", ".fbx", ".obj"],
        "poster": [".png", ".jpg", ".jpeg", ".webp"],
        "logo": [".png", ".jpg", ".jpeg", ".svg", ".webp"],
        "video": [".mp4", ".webm", ".mov"],
    }

    for asset in assets:
        aid = asset.get("id", "")
        atype = asset.get("type", "")
        apath = asset.get("path", "")
        full_path = Path(project_path) / apath

        if not full_path.exists():
            issues.append({
                "category": "资源",
                "level": "error",
                "item": aid,
                "message": f"文件不存在: {apath}"
            })
        elif atype in valid_extensions:
            ext = full_path.suffix.lower()
            if ext not in valid_extensions[atype]:
                issues.append({
                    "category": "资源",
                    "level": "warning",
                    "item": aid,
                    "message": f"文件扩展名 {ext} 与类型 {atype} 可能不匹配"
                })

    # 展位关联的资源是否存在
    for booth in booths:
        bid = booth.get("id", "")
        for res_field in ["model", "poster", "logo"]:
            res_path = booth.get(res_field, "")
            if res_path and res_path not in asset_paths:
                issues.append({
                    "category": "资源关联",
                    "level": "warning",
                    "item": bid,
                    "message": f"{res_field} 路径未在资源清单中登记"
                })

    # 4. 直播时间冲突
    from datetime import datetime as dt
    schedule_times = []
    for s in schedules:
        try:
            start = dt.strptime(s["start"], "%Y-%m-%d %H:%M")
            end = dt.strptime(s["end"], "%Y-%m-%d %H:%M")
            schedule_times.append((start, end, s.get("title", ""), s.get("zone", ""), s.get("booth_id", "")))
        except (ValueError, KeyError):
            issues.append({
                "category": "日程",
                "level": "error",
                "item": s.get("id", s.get("title", "unknown")),
                "message": "时间格式错误"
            })

    schedule_times.sort(key=lambda x: x[0])
    for i in range(len(schedule_times)):
        for j in range(i + 1, len(schedule_times)):
            s1_start, s1_end, s1_title, s1_zone, s1_booth = schedule_times[i]
            s2_start, s2_end, s2_title, s2_zone, s2_booth = schedule_times[j]
            # 同一展区/展位的时间才算冲突
            same_scope = (s1_zone and s2_zone and s1_zone == s2_zone) or \
                         (s1_booth and s2_booth and s1_booth == s2_booth)
            if same_scope and s2_start < s1_end:
                issues.append({
                    "category": "日程",
                    "level": "error",
                    "item": f"{s1_title} vs {s2_title}",
                    "message": f"时间冲突 ({s1_zone or s1_booth})"
                })

    # 5. 展区完整性检查
    booth_zones = {b.get("zone") for b in booths if b.get("zone")}
    for zone in zones:
        if zone not in booth_zones:
            issues.append({
                "category": "展区",
                "level": "warning",
                "item": zone,
                "message": "展区配置存在但暂无展位"
            })

    # 6. 嘉宾与展位关联
    booth_ids = {b["id"] for b in booths}
    for avatar in avatars:
        if avatar.get("booth_id") and avatar["booth_id"] not in booth_ids:
            issues.append({
                "category": "嘉宾",
                "level": "warning",
                "item": avatar.get("name", ""),
                "message": f"关联展位 {avatar['booth_id']} 不存在"
            })

    return issues


def print_issue_table(issues):
    """以表格形式输出问题清单"""
    rows = []
    for issue in issues:
        level_mark = "✗" if issue["level"] == "error" else "!"
        level_style = "red" if issue["level"] == "error" else "yellow"
        rows.append([
            f"[{level_style}]{level_mark}[/{level_style}]",
            issue["category"],
            issue["item"],
            issue["message"]
        ])
    print_table("问题清单", ["级别", "分类", "对象", "说明"], rows)


def load_release_data(project_path: str, history: list, version: str) -> dict:
    """加载指定版本的发布数据"""
    target = None
    for h in history:
        if h["version"] == version:
            target = h
            break
    if not target:
        print_error(f"未找到版本: {version}")
        return None

    zip_path = Path(project_path) / target["path"]
    if not zip_path.exists():
        print_error(f"发布包不存在: {zip_path}")
        return None

    import tempfile
    tmp_dir = Path(tempfile.mkdtemp())
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(tmp_dir)

    with open(tmp_dir / "release.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    shutil.rmtree(tmp_dir)
    return data


def compute_diff(old: dict, new: dict, v_old: str, v_new: str) -> dict:
    """计算两个版本的差异"""
    diff = {
        "versions": {"old": v_old, "new": v_new},
        "summary": {},
        "details": {},
    }

    categories = {
        "booths": "展位",
        "assets": "资源",
        "avatars": "嘉宾",
        "schedules": "日程",
    }

    for key, label in categories.items():
        old_items = old.get(key, [])
        new_items = new.get(key, [])
        old_ids = {item["id"] for item in old_items} if old_items else set()
        new_ids = {item["id"] for item in new_items} if new_items else set()

        added = new_ids - old_ids
        removed = old_ids - new_ids
        common = old_ids & new_ids

        changed = []
        old_map = {item["id"]: item for item in old_items}
        new_map = {item["id"]: item for item in new_items}
        for cid in common:
            if old_map[cid] != new_map[cid]:
                changed.append(cid)

        diff["summary"][label] = {
            "old_count": len(old_items),
            "new_count": len(new_items),
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
        }

        diff["details"][label] = {
            "added": sorted(list(added)),
            "removed": sorted(list(removed)),
            "changed": sorted(changed),
        }

    return diff


def print_diff_summary(diff: dict):
    """打印差异摘要"""
    v_old = diff["versions"]["old"]
    v_new = diff["versions"]["new"]
    console.rule(f"[bold cyan]版本对比: {v_old} → {v_new}[/bold cyan]")
    console.print()

    rows = []
    for label, data in diff["summary"].items():
        rows.append([
            label,
            str(data["old_count"]),
            str(data["new_count"]),
            f"[green]+{data['added']}[/green]",
            f"[red]-{data['removed']}[/red]",
            f"[yellow]~{data['changed']}[/yellow]",
        ])

    print_table("变化统计", ["类别", "旧版数量", "新版数量", "新增", "删除", "变更"], rows)


def generate_diff_html(diff: dict) -> str:
    """生成HTML格式差异报告"""
    v_old = diff["versions"]["old"]
    v_new = diff["versions"]["new"]

    html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>版本差异报告 - {v_old} vs {v_new}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
        .added {{ color: green; background: #e8f5e9; }}
        .removed {{ color: red; background: #ffebee; }}
        .changed {{ color: #f57c00; background: #fff3e0; }}
        .summary {{ background: #e3f2fd; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
    </style>
</head>
<body>
    <h1>版本差异报告</h1>
    <p>对比: <b>{v_old}</b> → <b>{v_new}</b></p>
    <div class="summary">
"""

    for label, data in diff["summary"].items():
        html += f"""
        <p><b>{label}:</b> 旧版 {data['old_count']} → 新版 {data['new_count']}
        <span class="added">新增 {data['added']}</span>,
        <span class="removed">删除 {data['removed']}</span>,
        <span class="changed">变更 {data['changed']}</span></p>
"""

    html += "</div>"

    for label, details in diff["details"].items():
        html += f"<h2>{label} 明细</h2>"
        if details["added"]:
            html += f"<h3 class='added'>新增 ({len(details['added'])})</h3><ul>"
            for item in details["added"]:
                html += f"<li class='added'>{item}</li>"
            html += "</ul>"
        if details["removed"]:
            html += f"<h3 class='removed'>删除 ({len(details['removed'])})</h3><ul>"
            for item in details["removed"]:
                html += f"<li class='removed'>{item}</li>"
            html += "</ul>"
        if details["changed"]:
            html += f"<h3 class='changed'>变更 ({len(details['changed'])})</h3><ul>"
            for item in details["changed"]:
                html += f"<li class='changed'>{item}</li>"
            html += "</ul>"

    html += "</body></html>"
    return html
