import click
import shutil
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
@click.pass_context
def list_avatars(ctx, booth, company):
    """列出所有嘉宾"""
    project_path = ctx.obj["project_path"]
    if not is_project_dir(project_path):
        print_error("当前目录不是有效的场景项目")
        raise click.Abort()

    config = SceneConfig(project_path)
    avatars = config.get("avatars", [])

    if booth:
        avatars = [a for a in avatars if a.get("booth_id") == booth]
    if company:
        avatars = [a for a in avatars if company.lower() in a.get("company", "").lower()]

    if not avatars:
        print_warning("暂无嘉宾数据")
        return

    rows = [
        [a["id"], a["name"], a.get("title", ""), a.get("company", ""),
         a.get("booth_id", ""), "✓" if a.get("avatar") else "✗"]
        for a in avatars
    ]
    print_table(f"嘉宾列表 ({len(avatars)} 人)",
                ["ID", "姓名", "头衔", "公司", "展位", "头像"], rows)


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
