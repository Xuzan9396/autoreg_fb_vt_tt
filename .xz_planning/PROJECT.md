# 项目快照

> 更新时间: 2026-03-21 22:20:56

## 技术栈

- 语言: Python 3.10+
- 包管理: uv
- GUI: Flet
- 安卓自动化: Airtest + Poco
- OCR: PaddleOCR / PaddlePaddle
- 本地数据: SQLite
- 打包: PyInstaller / Flet Desktop
- 日志: loguru JSON 日志

## 目录结构

```text
autovt/
├── autovt/
│   ├── auth/             # 登录与鉴权服务
│   ├── emails/           # 邮箱验证码与邮件处理
│   ├── gui/              # Flet GUI 页面与交互
│   ├── multiproc/        # 多设备 worker 主控
│   ├── ocr/              # OCR 识别能力
│   ├── tasks/            # 安卓自动化任务
│   ├── userdb/           # SQLite 用户库与配置
│   ├── adb.py            # ADB 设备发现与命令封装
│   ├── cli.py            # CLI 回退入口
│   ├── logs.py           # 日志初始化与输出策略
│   └── settings.py       # 全局配置
├── adb/                  # 各平台 adb 二进制
├── apks/                 # 本地安装包资源
├── assets/               # GUI 图标资源
├── doc/                  # 项目文档
├── tests/                # 测试
├── main.py               # 程序总入口
├── pyproject.toml        # Python/uv 依赖配置
└── AutoVT.spec           # 打包配置
```

## 关键入口

| 文件 | 用途 |
|------|------|
| `main.py` | 总入口，按参数切换 GUI 或 CLI 模式 |
| `autovt/gui/app.py` | GUI 主应用协调器，管理登录、设备、账号、设置页 |
| `autovt/cli.py` | 命令行主控回退模式 |
| `autovt/multiproc/manager.py` | 多设备进程管理与 ADB 控制中心 |
| `autovt/tasks/open_settings.py` | 设备自动化核心任务之一，负责设置页操作 |
| `autovt/userdb/user_db.py` | 本地 SQLite 用户库与全局配置存取 |

## 核心模块

| 目录/文件 | 职责 |
|------|------|
| `autovt/gui/` | Flet 桌面端后台界面与交互编排 |
| `autovt/multiproc/` | 多进程 worker 生命周期管理、状态同步和控制命令 |
| `autovt/tasks/` | 面向安卓设备的自动化业务任务实现 |
| `autovt/userdb/` | 账号池、全局配置和本地 SQLite 持久化 |
| `autovt/ocr/` | OCR 识别与图像文本处理 |
| `autovt/emails/` | 邮件拉取、验证码读取和邮箱配套能力 |
| `autovt/adb.py` | ADB 可执行路径解析、设备枚举与命令调用 |
| `doc/` | 项目结构、OCR、打包等维护文档 |
