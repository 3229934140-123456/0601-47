import click
import json
import csv
from pathlib import Path
from metaverse.config import SceneConfig
from metaverse.utils import (
    print_success,
    print_error,
    print_warning,
    print_info,
    print_table,
    validate_booth_id,
    get_booth_zone,
    is_project_dir,
)


@click.group()
@click.pass_context
def booth_cli(ctx):
    """展位管理 - 校验编号、批量导入展商、按展区过滤"""
    pass


@booth_cli.command("validate")
@click.argument("booth_id")
@click.pass_context
def validate_booth(ctx, booth_id):
    """校验展位编号格式

    BOOTH_ID 展位编号，如 A-001
    """
    valid, message = validate_booth_id(booth_id)
    if valid:
        print_success(f"展位编号 {booth_id} 有效 - {message}")
        zone = get_booth_zone(booth_id)
        print_info(f"所属展区: {zone}")
    else:
        print_error(f"展位编号 {booth_id} 无效 - {message}")
        raise click.Abort()


@booth_cli.command("import")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--format", "-f", "fmt", default="auto",
              type=click.Choice(["auto", "json", "csv"]), help="文件格式")
@click.option("--zone", "-z", help="指定展区过滤")
@click.pass_context
def import_booths(ctx, file_path, fmt, zone):
    """批量导入展商资料

    FILE_PATH 展商数据文件路径
    """
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    path = Path(file_path)
    if fmt == "auto":
        if path.suffix.lower() == ".json":
            fmt = "json"
        elif path.suffix.lower() == ".csv":
            fmt = "csv"
        else:
            print_error(f"无法自动识别文件格式: {path.suffix}")
            raise click.Abort()

    exhibitors = []
    if fmt == "json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                exhibitors = data
            elif isinstance(data, dict) and "booths" in data:
                exhibitors = data["booths"]
    elif fmt == "csv":
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            exhibitors = list(reader)

    if zone:
        exhibitors = [e for e in exhibitors if e.get("zone") == zone or get_booth_zone(e.get("id", "")) == zone]

    config = SceneConfig(project_path)
    existing_booths = {b["id"]: b for b in config.get("booths", [])}
    added = 0
    updated = 0
    invalid = 0

    for exhibitor in exhibitors:
        booth_id = exhibitor.get("id") or exhibitor.get("booth_id")
        if not booth_id:
            invalid += 1
            print_warning(f"跳过无效记录: 缺少展位编号")
            continue

        valid, _ = validate_booth_id(booth_id)
        if not valid:
            invalid += 1
            print_warning(f"跳过无效展位编号: {booth_id}")
            continue

        booth_zone = exhibitor.get("zone") or get_booth_zone(booth_id)
        booth_data = {
            "id": booth_id,
            "zone": booth_zone,
            "company": exhibitor.get("company", ""),
            "contact": exhibitor.get("contact", ""),
            "email": exhibitor.get("email", ""),
            "phone": exhibitor.get("phone", ""),
            "description": exhibitor.get("description", ""),
            "logo": exhibitor.get("logo", ""),
            "model": exhibitor.get("model", ""),
            "poster": exhibitor.get("poster", ""),
        }

        if booth_id in existing_booths:
            existing_booths[booth_id].update(booth_data)
            updated += 1
        else:
            existing_booths[booth_id] = booth_data
            added += 1

    config.set("booths", list(existing_booths.values()))
    config.save()

    print_success(f"导入完成: 新增 {added} 个，更新 {updated} 个，无效 {invalid} 个")


@booth_cli.command("list")
@click.option("--zone", "-z", help="按展区过滤，如 -z A")
@click.pass_context
def list_booths(ctx, zone):
    """列出所有展位，支持按展区过滤"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    booths = config.get("booths", [])

    if zone:
        booths = [b for b in booths if b.get("zone") == zone]

    if not booths:
        print_warning("暂无展位数据")
        return

    booths_sorted = sorted(booths, key=lambda x: x.get("id", ""))
    rows = [
        [b["id"], b.get("zone", ""), b.get("company", ""), b.get("contact", "")]
        for b in booths_sorted
    ]
    print_table(f"展位列表 ({len(booths)} 个)", ["展位号", "展区", "公司", "联系人"], rows)


@booth_cli.command("add")
@click.argument("booth_id")
@click.option("--company", "-c", help="公司名称")
@click.option("--contact", help="联系人")
@click.option("--email", help="邮箱")
@click.option("--phone", help="电话")
@click.pass_context
def add_booth(ctx, booth_id, company, contact, email, phone):
    """添加单个展位"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    valid, msg = validate_booth_id(booth_id)
    if not valid:
        print_error(f"展位编号无效: {msg}")
        raise click.Abort()

    config = SceneConfig(project_path)
    booths = config.get("booths", [])

    if any(b["id"] == booth_id for b in booths):
        print_error(f"展位 {booth_id} 已存在")
        raise click.Abort()

    booth_data = {
        "id": booth_id,
        "zone": get_booth_zone(booth_id),
        "company": company or "",
        "contact": contact or "",
        "email": email or "",
        "phone": phone or "",
        "description": "",
        "logo": "",
        "model": "",
        "poster": "",
    }
    booths.append(booth_data)
    config.set("booths", booths)
    config.save()

    print_success(f"展位 {booth_id} 添加成功")
