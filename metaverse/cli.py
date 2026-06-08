import click
from metaverse import __version__
from metaverse.commands import (
    scene_cli,
    booth_cli,
    asset_cli,
    avatar_cli,
    schedule_cli,
    publish_cli,
    report_cli,
    zone_cli,
)


@click.group()
@click.version_option(version=__version__, prog_name="metaverse")
@click.option("--project", "-p", default=".", help="项目目录路径，默认为当前目录")
@click.pass_context
def main(ctx, project):
    """元宇宙平台命令行工具 - 批量准备虚拟展厅内容

    \b
    命令组：
      scene     场景管理（创建项目、欢迎语、导航点）
      booth     展位管理（校验、导入、过滤）
      asset     资源管理（上传、清单、检查）
      avatar    嘉宾管理（头像、名牌）
      schedule  日程管理（直播时段）
      publish   发布管理（打包、回滚）
      report    报表统计（参展统计导出）
      zone      展区管理（展区概览、验收检查）
    """
    ctx.ensure_object(dict)
    ctx.obj["project_path"] = project


main.add_command(scene_cli, name="scene")
main.add_command(booth_cli, name="booth")
main.add_command(asset_cli, name="asset")
main.add_command(avatar_cli, name="avatar")
main.add_command(schedule_cli, name="schedule")
main.add_command(publish_cli, name="publish")
main.add_command(report_cli, name="report")
main.add_command(zone_cli, name="zone")


if __name__ == "__main__":
    main()
