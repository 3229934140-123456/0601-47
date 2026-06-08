from setuptools import setup, find_packages

setup(
    name="metaverse-cli",
    version="1.0.0",
    description="元宇宙平台命令行工具 - 批量准备虚拟展厅内容",
    author="活动技术团队",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "click>=8.0.0",
        "PyYAML>=6.0",
        "rich>=12.0.0",
    ],
    entry_points={
        "console_scripts": [
            "metaverse=metaverse.cli:main",
        ],
    },
    python_requires=">=3.8",
)
