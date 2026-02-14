- 新增独立 GUI 包：autovt/gui/app.py:33、autovt/gui/__init__.py:1
- 登录页（默认账号密码）：admin / 123456，见 autovt/gui/app.py:17、autovt/gui/app.py:75
- 登录后默认展示 adb devices，并显示每台设备状态（online/pid/alive/state/detail），见 autovt/gui/app.py:246、
  autovt/gui/app.py:295
- 支持手动刷新 + 自动监控 USB 插拔刷新，见 autovt/gui/app.py:388
- 全局按钮：启动全部/停止全部/暂停全部/恢复全部，见 autovt/gui/app.py:172
- 每设备按钮：启动/停止/暂停/恢复/重启，见 autovt/gui/app.py:301
- GUI 已去掉 once/run_once 入口（按你的要求）
- CLI 同步去掉 once/run_once，见 autovt/cli.py:12、autovt/cli.py:163

入口调整

- main.py 改为默认启动 GUI，并保留 --mode cli 回退，见 main.py:11、main.py:28

依赖与文档

- 新增 Flet 依赖：pyproject.toml:11、requirements.txt:13
- 文档已同步到你指定文件：doc/project_structure.md:13、doc/project_structure.md:83
- README 已改为 GUI 默认使用说明：README.md:15

已校验

- uv lock：成功（已写入 uv.lock）
- uv run python -m compileall main.py autovt/cli.py autovt/gui：通过
- uv run python main.py --help：参数正常
- unittest 当前显示 Ran 0 tests（项目里暂未发现可执行测试用例）

你现在可以直接运行：

- uv run python main.py（默认 GUI）
- uv run python main.py --mode cli（命令行回退）