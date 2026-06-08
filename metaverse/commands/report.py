import click
import json
import csv
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
)


@click.group()
@click.pass_context
def report_cli(ctx):
    """报表统计 - 导出参展统计"""
    pass


@report_cli.command("summary")
@click.option("--zone", "-z", help="按展区统计")
@click.pass_context
def summary(ctx, zone):
    """查看参展统计摘要"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    booths = config.get("booths", [])
    assets = config.get("assets", [])
    avatars = config.get("avatars", [])
    schedules = config.get("schedules", [])
    zones = config.get("scene.zones", [])

    if zone:
        booths = [b for b in booths if b.get("zone") == zone]
        assets = [a for a in assets if any(b["id"] == a.get("booth_id") for b in booths)]
        avatars = [a for a in avatars if any(b["id"] == a.get("booth_id") for b in booths)]
        schedules = [s for s in schedules if s.get("zone") == zone]

    # 按展区统计
    zone_stats = {}
    for z in zones:
        if zone and z != zone:
            continue
        zone_booths = [b for b in booths if b.get("zone") == z]
        zone_assets = [a for a in assets if any(b["id"] == a.get("booth_id") for b in zone_booths)]
        zone_avatars = [a for a in avatars if any(b["id"] == a.get("booth_id") for b in zone_booths)]
        zone_schedules = [s for s in schedules if s.get("zone") == z]
        zone_stats[z] = {
            "booths": len(zone_booths),
            "assets": len(zone_assets),
            "avatars": len(zone_avatars),
            "schedules": len(zone_schedules),
        }

    print_table(
        "参展统计摘要",
        ["展区", "展位", "资源", "嘉宾", "直播场次"],
        [[z, str(s["booths"]), str(s["assets"]), str(s["avatars"]), str(s["schedules"])]
         for z, s in zone_stats.items()]
    )

    # 总计
    total_booths = len(booths)
    total_assets = len(assets)
    total_avatars = len(avatars)
    total_schedules = len(schedules)

    print_info("=" * 40)
    print_info(f"总计: 展位 {total_booths} 个 | 资源 {total_assets} 个 | 嘉宾 {total_avatars} 人 | 直播 {total_schedules} 场")


@report_cli.command("export")
@click.option("--format", "-f", "fmt", default="json",
              type=click.Choice(["json", "csv", "html"]), help="导出格式")
@click.option("--output", "-o", help="输出文件路径")
@click.option("--zone", "-z", help="按展区过滤导出")
@click.option("--type", "-t", "report_type", default="all",
              type=click.Choice(["all", "booths", "assets", "schedules", "avatars"]),
              help="报表类型")
@click.pass_context
def export_report(ctx, fmt, output, zone, report_type):
    """导出参展统计报表"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    booths = config.get("booths", [])
    assets = config.get("assets", [])
    avatars = config.get("avatars", [])
    schedules = config.get("schedules", [])

    if zone:
        booths = [b for b in booths if b.get("zone") == zone]
        assets = [a for a in assets if any(b["id"] == a.get("booth_id") for b in booths)]
        avatars = [a for a in avatars if any(b["id"] == a.get("booth_id") for b in booths)]
        schedules = [s for s in schedules if s.get("zone") == zone]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not output:
        reports_dir = Path(project_path) / "reports"
        ensure_dir(reports_dir)
        output = str(reports_dir / f"report_{report_type}_{timestamp}.{fmt}")

    report_data = {
        "generated_at": datetime.now().isoformat(),
        "zone": zone or "all",
    }

    if report_type in ["all", "booths"]:
        report_data["booths"] = booths
    if report_type in ["all", "assets"]:
        report_data["assets"] = assets
    if report_type in ["all", "avatars"]:
        report_data["avatars"] = avatars
    if report_type in ["all", "schedules"]:
        report_data["schedules"] = schedules
    if report_type == "all":
        report_data["summary"] = {
            "booth_count": len(booths),
            "asset_count": len(assets),
            "avatar_count": len(avatars),
            "schedule_count": len(schedules),
        }

    output_path = Path(output)

    if fmt == "json":
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
        print_success(f"报表已导出: {output_path}")

    elif fmt == "csv":
        if report_type == "all":
            _export_csv_all(output_path, report_data)
        else:
            _export_csv_single(output_path, report_data, report_type)
        print_success(f"报表已导出: {output_path}")

    elif fmt == "html":
        html_content = _generate_html_report(report_data, report_type)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print_success(f"报表已导出: {output_path}")


def _export_csv_single(output_path: Path, report_data: dict, report_type: str):
    """导出单类型 CSV"""
    field_configs = {
        "booths": ["id", "zone", "company", "contact", "email", "phone", "description"],
        "assets": ["id", "name", "type", "filename", "booth_id", "size", "status"],
        "avatars": ["id", "name", "title", "company", "booth_id", "nameplate"],
        "schedules": ["id", "title", "start", "end", "speaker", "booth_id", "zone", "type", "status"],
    }
    fields = field_configs.get(report_type, [])
    items = report_data.get(report_type, [])

    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for item in items:
            writer.writerow(item)


def _export_csv_all(base_output: Path, report_data: dict):
    """导出 all 类型时生成多个 CSV 文件"""
    base_dir = base_output.parent
    base_stem = base_output.stem

    types = [
        ("booths", "展位"),
        ("assets", "资源"),
        ("avatars", "嘉宾"),
        ("schedules", "日程"),
    ]

    for key, label in types:
        items = report_data.get(key, [])
        if items:
            file_path = base_dir / f"{base_stem}_{key}.csv"
            _export_csv_single(file_path, report_data, key)

    # 生成汇总文件
    summary_path = base_dir / f"{base_stem}_summary.csv"
    if "summary" in report_data:
        s = report_data["summary"]
        with open(summary_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["类别", "数量"])
            writer.writerow(["展位", s.get("booth_count", 0)])
            writer.writerow(["资源", s.get("asset_count", 0)])
            writer.writerow(["嘉宾", s.get("avatar_count", 0)])
            writer.writerow(["日程", s.get("schedule_count", 0)])


def _generate_html_report(data, report_type):
    """生成HTML格式报表"""
    html = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>参展统计报表</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        h1 { color: #333; }
        table { border-collapse: collapse; width: 100%; margin-bottom: 20px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #4CAF50; color: white; }
        tr:nth-child(even) { background-color: #f2f2f2; }
        .summary { background: #e8f5e9; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
    </style>
</head>
<body>
    <h1>元宇宙参展统计报表</h1>
    <p>生成时间: {generated_at}</p>
    <p>展区: {zone}</p>
""".format(generated_at=data.get("generated_at", ""), zone=data.get("zone", "all"))

    if "summary" in data:
        s = data["summary"]
        html += f"""
    <div class="summary">
        <h3>统计摘要</h3>
        <p>展位数量: {s['booth_count']}</p>
        <p>资源数量: {s['asset_count']}</p>
        <p>嘉宾数量: {s['avatar_count']}</p>
        <p>直播场次: {s['schedule_count']}</p>
    </div>
"""

    if "booths" in data:
        html += "<h2>展位列表</h2><table><tr><th>展位号</th><th>展区</th><th>公司</th><th>联系人</th><th>电话</th></tr>"
        for b in data["booths"]:
            html += f"<tr><td>{b.get('id','')}</td><td>{b.get('zone','')}</td><td>{b.get('company','')}</td><td>{b.get('contact','')}</td><td>{b.get('phone','')}</td></tr>"
        html += "</table>"

    if "assets" in data:
        html += "<h2>资源列表</h2><table><tr><th>ID</th><th>名称</th><th>类型</th><th>展位</th><th>大小</th></tr>"
        for a in data["assets"]:
            html += f"<tr><td>{a.get('id','')}</td><td>{a.get('name','')}</td><td>{a.get('type','')}</td><td>{a.get('booth_id','')}</td><td>{a.get('size',0)/1024:.1f}KB</td></tr>"
        html += "</table>"

    if "schedules" in data:
        html += "<h2>日程列表</h2><table><tr><th>标题</th><th>开始</th><th>结束</th><th>主讲人</th><th>类型</th></tr>"
        for s in data["schedules"]:
            html += f"<tr><td>{s.get('title','')}</td><td>{s.get('start','')}</td><td>{s.get('end','')}</td><td>{s.get('speaker','')}</td><td>{s.get('type','')}</td></tr>"
        html += "</table>"

    if "avatars" in data:
        html += "<h2>嘉宾列表</h2><table><tr><th>姓名</th><th>头衔</th><th>公司</th><th>展位</th></tr>"
        for a in data["avatars"]:
            html += f"<tr><td>{a.get('name','')}</td><td>{a.get('title','')}</td><td>{a.get('company','')}</td><td>{a.get('booth_id','')}</td></tr>"
        html += "</table>"

    html += "</body></html>"
    return html
