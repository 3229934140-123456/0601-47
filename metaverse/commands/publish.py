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
@click.option("--report", "report_path", help="导出预检问题单到文件")
@click.option("--report-format", "report_fmt", default="json",
              type=click.Choice(["json", "csv"]), help="问题单格式")
@click.pass_context
def build(ctx, version, note, dry_run, skip_check, strict, report_path, report_fmt):
    """打包发布版本（支持预检和 dry-run）"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    issues = []

    if not skip_check:
        print_info("开始发布预检...")
        issues = run_preflight_checks(project_path, config)

        error_count = sum(1 for i in issues if i["level"] == "error")
        warning_count = sum(1 for i in issues if i["level"] == "warning")

        if not issues:
            print_success("预检通过，未发现任何问题")
        else:
            print_warning(f"预检完成: 发现 {error_count} 个错误，{warning_count} 个警告")
            print_issue_summary(issues)

            if strict and error_count > 0:
                print_error("严格模式下发现错误，终止发布")
                _export_issues(issues, report_path, report_fmt) if report_path else None
                raise click.Abort()

            if not dry_run and not click.confirm("是否继续打包？", default=not error_count):
                raise click.Abort()

        if report_path:
            _export_issues(issues, report_path, report_fmt)

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
@click.option("--group-by", "-g", "group_by", default="none",
              type=click.Choice(["none", "level", "zone", "category"]),
              help="分组方式")
@click.option("--zone", "-z", help="只看指定展区的问题")
@click.option("--level", "-l", "level_filter",
              type=click.Choice(["error", "warning"]),
              help="只看指定级别的问题")
@click.option("--output", "-o", help="导出问题单到文件")
@click.option("--format", "-f", "fmt", default="json",
              type=click.Choice(["json", "csv"]), help="导出格式")
@click.pass_context
def preflight_check(ctx, group_by, zone, level_filter, output, fmt):
    """发布前预检：检查展位、资源、日程等是否符合要求"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    issues = run_preflight_checks(project_path, config)

    if zone:
        issues = [i for i in issues if i.get("zone") == zone]
    if level_filter:
        issues = [i for i in issues if i["level"] == level_filter]

    error_count = sum(1 for i in issues if i["level"] == "error")
    warning_count = sum(1 for i in issues if i["level"] == "warning")

    if not issues:
        print_success("预检通过，未发现任何问题")
        return

    print_warning(f"发现 {error_count} 个错误，{warning_count} 个警告")

    if group_by == "none":
        print_issue_table(issues)
    elif group_by == "level":
        _print_issues_by_level(issues)
    elif group_by == "zone":
        _print_issues_by_zone(issues)
    elif group_by == "category":
        _print_issues_by_category(issues)

    if output:
        _export_issues(issues, output, fmt)


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
@click.option("--detail", "-d", is_flag=True, help="显示字段级变更详情")
@click.option("--output", "-o", help="导出差异报告文件路径")
@click.option("--format", "-f", "fmt", default="json",
              type=click.Choice(["json", "html"]), help="报告格式")
@click.pass_context
def diff_versions(ctx, v1, v2, detail, output, fmt):
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

    diff = compute_diff(data_old, data_new, v1, v2, with_field_detail=detail)
    print_diff_summary(diff)

    if detail:
        print_diff_field_details(diff)

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

    booth_zone_map = {b["id"]: b.get("zone", "") for b in booths}
    asset_booth_map = {a["id"]: a.get("booth_id", "") for a in assets}
    avatar_booth_map = {a.get("id", ""): a.get("booth_id", "") for a in avatars}

    def _get_zone_by_booth(bid):
        return booth_zone_map.get(bid, "")

    def _get_zone_by_asset(aid):
        bid = asset_booth_map.get(aid, "")
        return booth_zone_map.get(bid, "")

    def _issue(category, level, item, message, zone=""):
        issues.append({
            "category": category,
            "level": level,
            "item": item,
            "message": message,
            "zone": zone,
        })

    # 1. 展位编号校验
    for booth in booths:
        bid = booth.get("id", "")
        zone = booth.get("zone", "")
        valid, msg = validate_booth_id(bid)
        if not valid:
            _issue("展位", "error", bid, f"展位编号格式错误: {msg}", zone)

    # 2. 展商资料必填项
    required_fields = ["company", "contact"]
    for booth in booths:
        bid = booth.get("id", "unknown")
        zone = booth.get("zone", "")
        for field in required_fields:
            if not booth.get(field):
                _issue("展商资料", "warning", bid, f"缺少必填项: {field}", zone)

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
        zone = _get_zone_by_asset(aid)
        full_path = Path(project_path) / apath

        if not full_path.exists():
            _issue("资源", "error", aid, f"文件不存在: {apath}", zone)
        elif atype in valid_extensions:
            ext = full_path.suffix.lower()
            if ext not in valid_extensions[atype]:
                _issue("资源", "warning", aid, f"文件扩展名 {ext} 与类型 {atype} 可能不匹配", zone)

    # 展位关联的资源是否存在
    for booth in booths:
        bid = booth.get("id", "")
        zone = booth.get("zone", "")
        for res_field in ["model", "poster", "logo"]:
            res_path = booth.get(res_field, "")
            if res_path and res_path not in asset_paths:
                _issue("资源关联", "warning", bid, f"{res_field} 路径未在资源清单中登记", zone)

    # 4. 直播时间冲突
    from datetime import datetime as dt
    schedule_times = []
    for s in schedules:
        try:
            start = dt.strptime(s["start"], "%Y-%m-%d %H:%M")
            end = dt.strptime(s["end"], "%Y-%m-%d %H:%M")
            schedule_times.append((start, end, s.get("title", ""), s.get("zone", ""), s.get("booth_id", "")))
        except (ValueError, KeyError):
            sid = s.get("id", s.get("title", "unknown"))
            zone = s.get("zone", "") or _get_zone_by_booth(s.get("booth_id", ""))
            _issue("日程", "error", sid, "时间格式错误", zone)

    schedule_times.sort(key=lambda x: x[0])
    for i in range(len(schedule_times)):
        for j in range(i + 1, len(schedule_times)):
            s1_start, s1_end, s1_title, s1_zone, s1_booth = schedule_times[i]
            s2_start, s2_end, s2_title, s2_zone, s2_booth = schedule_times[j]
            same_scope = (s1_zone and s2_zone and s1_zone == s2_zone) or \
                         (s1_booth and s2_booth and s1_booth == s2_booth)
            if same_scope and s2_start < s1_end:
                zone = s1_zone or _get_zone_by_booth(s1_booth)
                _issue("日程", "error", f"{s1_title} vs {s2_title}",
                       f"时间冲突 ({s1_zone or s1_booth})", zone)

    # 5. 展区完整性检查
    booth_zones = {b.get("zone") for b in booths if b.get("zone")}
    for zone in zones:
        if zone not in booth_zones:
            _issue("展区", "warning", zone, "展区配置存在但暂无展位", zone)

    # 6. 嘉宾与展位关联
    booth_ids = {b["id"] for b in booths}
    for avatar in avatars:
        if avatar.get("booth_id") and avatar["booth_id"] not in booth_ids:
            zone = _get_zone_by_booth(avatar.get("booth_id", ""))
            _issue("嘉宾", "warning", avatar.get("name", ""),
                   f"关联展位 {avatar['booth_id']} 不存在", zone)

    return issues


def print_issue_table(issues):
    """以表格形式输出问题清单"""
    rows = []
    for issue in issues:
        level_mark = "✗" if issue["level"] == "error" else "!"
        level_style = "red" if issue["level"] == "error" else "yellow"
        rows.append([
            f"[{level_style}]{level_mark}[/{level_style}]",
            issue.get("zone", ""),
            issue["category"],
            issue["item"],
            issue["message"]
        ])
    print_table("问题清单", ["级别", "展区", "分类", "对象", "说明"], rows)


def print_issue_summary(issues):
    """输出问题摘要（按分类和级别统计）"""
    from collections import defaultdict
    by_category = defaultdict(lambda: {"error": 0, "warning": 0})
    by_zone = defaultdict(lambda: {"error": 0, "warning": 0})

    for issue in issues:
        cat = issue["category"]
        lvl = issue["level"]
        zone = issue.get("zone", "未分类")
        by_category[cat][lvl] += 1
        by_zone[zone][lvl] += 1

    # 按分类统计
    rows = []
    for cat, counts in sorted(by_category.items()):
        rows.append([
            cat,
            f"[red]{counts['error']}[/red]",
            f"[yellow]{counts['warning']}[/yellow]",
            str(counts["error"] + counts["warning"])
        ])
    print_table("问题分类统计", ["分类", "错误", "警告", "总计"], rows)


def _print_issues_by_level(issues):
    """按严重程度分组展示问题"""
    errors = [i for i in issues if i["level"] == "error"]
    warnings = [i for i in issues if i["level"] == "warning"]

    if errors:
        console.print(f"\n[bold red]❌ 错误 ({len(errors)} 项)[/bold red]")
        rows = [[i.get("zone", ""), i["category"], i["item"], i["message"]] for i in errors]
        print_table("", ["展区", "分类", "对象", "说明"], rows)

    if warnings:
        console.print(f"\n[bold yellow]⚠ 警告 ({len(warnings)} 项)[/bold yellow]")
        rows = [[i.get("zone", ""), i["category"], i["item"], i["message"]] for i in warnings]
        print_table("", ["展区", "分类", "对象", "说明"], rows)


def _print_issues_by_zone(issues):
    """按展区分组展示问题"""
    from collections import defaultdict
    zones = defaultdict(list)
    for issue in issues:
        z = issue.get("zone", "未分类")
        zones[z].append(issue)

    for zone in sorted(zones.keys()):
        zone_issues = zones[zone]
        err = sum(1 for i in zone_issues if i["level"] == "error")
        warn = sum(1 for i in zone_issues if i["level"] == "warning")
        console.print(f"\n[bold cyan]📌 展区 {zone} ({err} 错 / {warn} 警)[/bold cyan]")
        rows = [[i["level"], i["category"], i["item"], i["message"]] for i in zone_issues]
        print_table("", ["级别", "分类", "对象", "说明"], rows)


def _print_issues_by_category(issues):
    """按分类分组展示问题"""
    from collections import defaultdict
    cats = defaultdict(list)
    for issue in issues:
        cats[issue["category"]].append(issue)

    for cat in sorted(cats.keys()):
        cat_issues = cats[cat]
        err = sum(1 for i in cat_issues if i["level"] == "error")
        warn = sum(1 for i in cat_issues if i["level"] == "warning")
        console.print(f"\n[bold magenta]📂 {cat} ({err} 错 / {warn} 警)[/bold magenta]")
        rows = [[i.get("zone", ""), i["level"], i["item"], i["message"]] for i in cat_issues]
        print_table("", ["展区", "级别", "对象", "说明"], rows)


def _export_issues(issues, output_path: str, fmt: str):
    """导出问题单到文件"""
    import csv as csv_module
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "total": len(issues),
                "errors": sum(1 for i in issues if i["level"] == "error"),
                "warnings": sum(1 for i in issues if i["level"] == "warning"),
                "issues": issues,
            }, f, ensure_ascii=False, indent=2)

    elif fmt == "csv":
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv_module.DictWriter(
                f, fieldnames=["level", "zone", "category", "item", "message"],
                extrasaction="ignore"
            )
            writer.writeheader()
            for issue in issues:
                writer.writerow(issue)

    print_success(f"问题单已导出: {path}")


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


def compute_diff(old: dict, new: dict, v_old: str, v_new: str, with_field_detail: bool = False) -> dict:
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

    display_fields = {
        "booths": ["company", "contact", "email", "phone", "zone", "model", "poster", "logo"],
        "assets": ["name", "type", "filename", "booth_id", "status"],
        "avatars": ["name", "title", "company", "booth_id", "nameplate", "status"],
        "schedules": ["title", "start", "end", "speaker", "booth_id", "zone", "type", "status"],
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
        field_changes = {}
        old_map = {item["id"]: item for item in old_items}
        new_map = {item["id"]: item for item in new_items}

        for cid in common:
            old_item = old_map[cid]
            new_item = new_map[cid]
            if old_item != new_item:
                changed.append(cid)
                if with_field_detail:
                    fields = display_fields.get(key, list(new_item.keys()))
                    item_changes = []
                    for f in fields:
                        old_val = old_item.get(f, "")
                        new_val = new_item.get(f, "")
                        if old_val != new_val:
                            item_changes.append({
                                "field": f,
                                "old": old_val,
                                "new": new_val,
                            })
                    if item_changes:
                        field_changes[cid] = item_changes

        diff["summary"][label] = {
            "old_count": len(old_items),
            "new_count": len(new_items),
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
        }

        details = {
            "added": sorted(list(added)),
            "removed": sorted(list(removed)),
            "changed": sorted(changed),
        }
        if with_field_detail:
            details["field_changes"] = field_changes
        diff["details"][label] = details

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


def print_diff_field_details(diff: dict):
    """打印字段级变更详情"""
    console.print()
    console.rule("[bold yellow]字段级变更详情[/bold yellow]")

    for label, details in diff["details"].items():
        field_changes = details.get("field_changes", {})
        if not field_changes:
            continue

        console.print()
        console.print(f"[bold magenta]📋 {label} 变更详情[/bold magenta]")

        for item_id, changes in sorted(field_changes.items()):
            console.print(f"\n  [bold]{item_id}[/bold]")
            rows = []
            for change in changes:
                rows.append([
                    change["field"],
                    str(change["old"]) if change["old"] else "(空)",
                    str(change["new"]) if change["new"] else "(空)",
                ])
            print_table(
                "", ["字段", "旧值", "新值"], rows
            )


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
        h2 {{ margin-top: 30px; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
        .added {{ color: green; background: #e8f5e9; }}
        .removed {{ color: red; background: #ffebee; }}
        .changed {{ color: #f57c00; background: #fff3e0; }}
        .summary {{ background: #e3f2fd; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
        .item-id {{ font-weight: bold; margin-top: 10px; }}
        .field-table {{ margin-left: 20px; width: calc(100% - 20px); }}
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
            html += f"<h3 class='changed'>变更 ({len(details['changed'])})</h3>"
            field_changes = details.get("field_changes", {})
            if field_changes:
                for item_id in sorted(details["changed"]):
                    html += f"<div class='item-id'>{item_id}</div>"
                    changes = field_changes.get(item_id, [])
                    if changes:
                        html += "<table class='field-table'><tr><th>字段</th><th>旧值</th><th>新值</th></tr>"
                        for c in changes:
                            html += f"<tr><td>{c['field']}</td><td>{c['old'] or '(空)'}</td><td>{c['new'] or '(空)'}</td></tr>"
                        html += "</table>"
                    else:
                        html += "<ul><li>有变更（具体字段未提供）</li></ul>"
            else:
                html += "<ul>"
                for item in details["changed"]:
                    html += f"<li class='changed'>{item}</li>"
                html += "</ul>"

    html += "</body></html>"
    return html
