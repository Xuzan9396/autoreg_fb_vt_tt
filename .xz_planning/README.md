# XZ Planning - 轻量级版本计划驱动开发

init → discuss? → plan → exec ⇄ update-plan? → review? → test? → done

辅助: status / ref / del / remove-all

基于 todolist 的开发流程管理工具，通过 Claude Code skill 驱动。

## 命令一览

**核心流程：**

| 命令 | 用途 | 必须 | 示例 |
|------|------|:----:|------|
| `/xz-init` | 初始化当前项目的计划目录 | ✅ | `/xz-init` |
| `/xz-discuss N 讨论内容` | PM × Dev 头脑风暴，收敛想法 | 可选 | `/xz-discuss 1 做个客户管理工具` |
| `/xz-plan N 需求描述` | 创建新版本计划 | ✅ | `/xz-plan 1 实现用户注册登录` |
| `/xz-update-plan N 操作` | 修改/新增/删除 todolist 条目 | 可选 | `/xz-update-plan 1 修改 #3 增加缓存` |
| `/xz-exec N` | 执行版本 N 中未完成的 todolist | ✅ | `/xz-exec 1` |
| `/xz-review N` | 审查版本 N 的代码质量和安全 | 可选 | `/xz-review 1` |
| `/xz-test N` | 生成版本 N 的手动测试指南 | 可选 | `/xz-test 1` |
| `/xz-done N` | 归档已完成的版本 | ✅ | `/xz-done 1` |

**辅助工具：**

| 命令 | 用途 | 示例 |
|------|------|------|
| `/xz-status` | 查看所有版本状态总览 | `/xz-status` |
| `/xz-status N` | 查看版本 N 的详细进度 | `/xz-status 1` |
| `/xz-ref N` 或 `/xz-ref N1,N2` | 加载计划到上下文供参考 | `/xz-ref 1,2` |
| `/xz-del N` | 删除单个版本计划 | `/xz-del 2` |
| `/xz-remove-all` | 交互式清理全部计划数据 | `/xz-remove-all` |

## 典型工作流

```
                          ┌─────────────────────┐
                          │  /xz-init            │  必须，首次使用前执行
                          └──────────┬──────────┘
                                     ↓
                     ┌───────────────────────────────┐
                     │  /xz-discuss N 讨论内容        │  可选，头脑风暴
                     └───────────────┬───────────────┘
                                     ↓
                          ┌─────────────────────┐
                          │  /xz-plan N 需求描述  │  必须，生成 todolist
                          └──────────┬──────────┘
                                     ↓
                          ┌─────────────────────┐
                     ┌──→ │  /xz-exec N          │  必须，逐条执行
                     │    └──────────┬──────────┘
                     │               ↓
                     │    ┌─────────────────────┐
                     └────│  /xz-update-plan N   │  可选，中途增删改条目
                          └──────────┬──────────┘
                                     ↓
                     ┌───────────────────────────────┐
                     │  /xz-review N                  │  可选，代码审查
                     └───────────────┬───────────────┘
                                     ↓
                     ┌───────────────────────────────┐
                     │  /xz-test N                    │  可选，生成测试指南
                     └───────────────┬───────────────┘
                                     ↓
                          ┌─────────────────────┐
                          │  /xz-done N          │  必须，归档
                          └─────────────────────┘
```

**最小流程：** `init → plan → exec → done`

**完整流程：** `init → discuss → plan → exec ⇄ update-plan → review → test → done`

典型使用示例：

```
0. /xz-init                                              ← 首次
1. /xz-discuss 1 做一个用户注册登录和JWT鉴权               ← 可选
2. /xz-plan 1 实现用户注册登录和JWT鉴权
3. /xz-exec 1
4. /xz-update-plan 1 新增一条: 添加密码找回功能            ← 可选
5. /xz-exec 1
6. /xz-review 1                                          ← 可选
7. /xz-test 1                                            ← 可选
8. /xz-done 1
```

## 目录结构

执行 `/xz-init` 后会在项目根目录生成：

```
.xz_planning/
├── STATE.md                    # 全局状态表
├── README.md                   # 使用说明
├── phases/
│   ├── 1.用户注册登录/
│   │   ├── 1-DISCUSS.md        # 讨论文档（可选，由 xz-discuss 生成）
│   │   └── 1-PLAN.md           # 版本 1 的计划和 todolist
│   └── 2.商品管理/
│       └── 2-PLAN.md
└── archive/                    # 已归档的版本
    └── 1.用户注册登录/
        └── 1-PLAN.md
```

全局文件（安装时写入）：

```
~/.xz_planning/
├── script/
│   └── xz-tools.py            # 辅助脚本（固定路径）
└── README.md                   # 使用文档
```

## 各命令详细说明

### /xz-init

初始化当前项目的 `.xz_planning/` 目录结构。首次使用前必须执行。已初始化的项目会提示跳过，不会覆盖已有数据。

### /xz-discuss N 讨论内容

PM × Dev 头脑风暴工具，把粗糙想法收敛为结构化讨论文档。**不是必须步骤**，可以跳过直接 `/xz-plan`。

双模式自动切换：
- **讨论模式**（输入粗糙） — 先 brainstorm：用户画像、核心问题、功能方向评估、MVP 收敛
- **直出模式**（输入已有方向） — 直接生成结构化讨论文档

输出 `N-DISCUSS.md`，包含：目标用户、核心问题、功能方向（价值/复杂度/MVP 标记）、产品方案、技术边界（Dev 视角）、MVP 收敛（Must/Should/Later）、风险与待确认。

确认后写入文件。后续 `/xz-plan` 会自动引用同目录下的 `N-DISCUSS.md`。

### /xz-plan N 需求描述

创建新版本计划。要求项目已初始化（已执行 `/xz-init`）。如果同目录存在 `N-DISCUSS.md`，自动引用。遵循双轨制：

- **需求明确** → 直接生成 todolist
- **需求有歧义** → 先出 A/B/C 方案，你选定后再生成

每条 todolist 包含 `change details`，明确写出新建/修改哪些文件：

```markdown
- [ ] 1. 创建 User model
  ```
  change details:
  新建: src/models/user.py
  - class User: id, username, email, password_hash
  修改: src/app.py
  - 注册数据库连接
  ```
```

生成后先展示草案，你确认后才写入文件。如果版本已存在会拒绝，提示用 `/xz-update-plan`。

### /xz-update-plan N 操作描述

修改已有版本的 todolist。支持：

- **修改条目**: `/xz-update-plan 1 修改 #3 增加 refresh token`
- **新增条目**: `/xz-update-plan 1 新增: 添加日志中间件`
- **删除条目**: `/xz-update-plan 1 删除 #4`
- **插入条目**: `/xz-update-plan 1 在 #2 后插入缓存优化`

已完成的 `[x]` 条目受锁定保护，不可修改或删除。修改后自动重编号。

### /xz-exec N

从第一个未完成的 `[ ]` 条目开始，按 change details 逐条执行：

1. 读取 change details
2. 编写/修改代码
3. 标记 `[x]` + 更新 PLAN.md 和 STATE.md
4. 继续下一条

### /xz-done N

归档版本（纯文件操作，不涉及 git）：

- 全部完成 → 直接归档到 `archive/`
- 有未完成 → 警告，询问是否强制归档

### /xz-status

展示所有版本进度的可视化总览和 STATE.md 表格。

### /xz-review N

审查版本 N 的 todolist 改动，只看 PLAN.md 中涉及的文件，不管其他代码。检查内容：

1. **符合性** — change details 描述 vs 实际代码，是否一致
2. **安全** — 注入、硬编码密钥、鉴权缺失、敏感信息泄露等
3. **性能** — N+1 查询、缺少索引、内存泄漏、阻塞操作等
4. **质量** — 边界条件、错误处理、资源释放、命名规范等

输出结构化报告：问题发现（按严重程度排序）→ 符合性检查表 → 改善建议 → 总结。

### /xz-test N

为版本 N 生成手动测试指南，写入 `N-UAT.md`（与 `N-PLAN.md` 同目录）。不更新任何状态文件。

内容包括：
- **前置准备** — 启动服务、准备数据等
- **测试场景** — 每个场景对应 todolist 编号，包含操作步骤和预期结果
- **需要的命令** — curl、SQL 等用代码块给出，说明怎么复制执行
- **检查清单** — 底部附 checkbox 列表，方便逐条打勾确认

覆盖正常路径和异常路径（边界条件、错误输入、权限缺失）。

### /xz-ref N 或 /xz-ref N1,N2,N3

加载一个或多个版本的 PLAN.md（+ UAT.md）到当前对话上下文，让 AI 知道这些计划的内容。活跃版本和已归档版本都会查找。

用途：
- 提问计划细节："版本 1 的注册接口怎么设计的？"
- 跨版本对比："版本 1 和 2 有哪些文件重叠？"
- 辅助新规划："参考版本 1 的风格规划版本 4"
- 排查影响："版本 2 的改动会不会影响版本 1？"

### /xz-del N

删除单个版本的计划目录，需确认。

### /xz-remove-all

交互式终端菜单：

- `↑↓` 选择「全部删除」或「否」
- `Tab` 切换到自定义输入（如 "只删 archive"、"保留 1 删除 2"）

## 安装/卸载

必须指定 `--claude` 或 `--codex` 参数。需要对应的 `~/.claude` 或 `~/.codex` 目录已存在（即已安装 Claude Code 或 Codex），否则拒绝安装。`skills/` 子目录不存在时会自动创建。

```bash
# 安装
./skills/install.sh --claude    # → ~/.claude/skills/xz-*/
./skills/install.sh --codex     # → ~/.codex/skills/xz-*/

# 重装（每次覆盖）
./skills/reinstall.sh --claude
./skills/reinstall.sh --codex

# 重装 + 注入 Codex 适配层（AskUserQuestion → request_user_input）
./skills/reinstall.sh --codex --inject xz-ask
./skills/reinstall.sh --codex --inject xz-ask,xz-remove-all

# 卸载
./skills/uninstall.sh --claude
./skills/uninstall.sh --codex
```

安装时会同时写入全局文件：
- `~/.xz_planning/script/xz-tools.py` — 辅助脚本
- `~/.xz_planning/README.md` — 使用文档

| 参数 | 安装路径 | 前置条件 |
|------|----------|----------|
| `--claude` | `~/.claude/skills/` | `~/.claude` 目录已存在 |
| `--codex` | `~/.codex/skills/` | `~/.codex` 目录已存在 |

- `install` 遇到同名目录会逐个询问是否覆盖
- `reinstall` 直接覆盖不询问
- `uninstall` 卸载前会列出并确认
- `--inject` 在重装完成后自动为指定 skill 注入 `<codex_skill_adapter>` 头部，将 `AskUserQuestion` 映射为 Codex 的 `request_user_input`，已有适配层的 skill 自动跳过

## Codex 适配层（AskUserQuestion → request_user_input）

XZ 的所有 skill 统一使用 `AskUserQuestion`（Claude Code 语法）编写。安装到 Codex 时，通过 `--inject` 在 SKILL.md 头部注入 `<codex_skill_adapter>` 块，实现跨运行时兼容。

**适配机制（参照 [GSD v1.22.0](https://github.com/gsd-build/get-shit-done)）：**

| 步骤 | 说明 |
|------|------|
| 1. `getCodexSkillAdapterHeader()` | 安装时给指定 SKILL.md 头部注入 `<codex_skill_adapter>` 块 |
| 2. Section B 参数映射 | `header` → `header`，`question` → `question`，`options` → `{label, description}` |
| 3. `config.toml` 配置 | 需在 Codex 的 `config.toml` 中启用 `default_mode_request_user_input = true` |
| 4. multiSelect 降级 | Codex 不支持 `multiSelect`，改为编号列表 + 逗号分隔输入（如 "1,3,4"） |
| 5. Execute mode 降级 | `request_user_input` 被拒绝时（全自动模式），回退为纯文本列表 + 自动选推荐项 |

**注入方式：**

```bash
# 重装时指定需要注入的 skill
./skills/reinstall.sh --codex --inject xz-ask
./skills/reinstall.sh --codex --inject xz-ask,xz-remove-all
```

**注意：** Codex 需要在 `~/.codex/config.toml` 的 `[features]` 中启用：

```toml
[features]
default_mode_request_user_input = true
```

如果没有此配置，`request_user_input` 调用会被静默忽略。

## 辅助脚本

`~/.xz_planning/script/xz-tools.py` 提供底层文件操作：

```bash
python3 ~/.xz_planning/script/xz-tools.py init          # 初始化目录
python3 ~/.xz_planning/script/xz-tools.py status        # 输出 JSON 状态
python3 ~/.xz_planning/script/xz-tools.py parse N       # 解析版本 N 的 PLAN
python3 ~/.xz_planning/script/xz-tools.py update-state  # 刷新 STATE.md
python3 ~/.xz_planning/script/xz-tools.py complete N    # 归档版本 N
python3 ~/.xz_planning/script/xz-tools.py delete N      # 删除版本 N
python3 ~/.xz_planning/script/xz-tools.py remove-all    # 交互式清理
```

## 设计原则

- **初始化先行** — 使用前必须 `/xz-init`，确保目录结构就绪
- **方案先出** — 禁止需求模糊就动手，先对齐再干活
- **先展示后写文件** — 所有计划/修改必须确认后才落盘
- **已完成锁定** — `[x]` 条目不可修改删除
- **不碰 git** — 所有操作均为纯文件操作，不执行任何 git 命令
- **原子化执行** — 每条 todo 独立完成，逐条推进
- **状态可追溯** — STATE.md 实时反映所有版本进度
