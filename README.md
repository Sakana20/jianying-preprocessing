# JianYing Preprocessing

`jianying-preprocessing` 是一个面向剪映专业版 5.9 工程的确定性预处理工具和 Codex Skill。

它接收一个已经存在的剪映工程副本，根据经过审核的类型化配置，统一处理字幕、产品名与利益点高亮、利益点图片、风险提示图和逐视频尾帧，同时保留原工程已有的时间线、素材 ID、片段 ID 及未知字段。

项目的核心目标不是重新生成剪映工程，而是把容易重复、容易出错的人工预处理步骤固化为可检查、可计划、可回滚的 CLI 工作流。

## 当前状态

当前版本：`v0.1.0`

支持的写入目标：

- 剪映专业版 5.9.0
- `draft_info.json.version = 360000`
- 30 fps
- 配置声明的精确画布；首个配置集为 720×1280、9:16

其他版本仍可以使用 `inspect` 做只读检查，但不能执行 `plan` 或 `apply`。

项目已使用三个本地参考工程完成回归：

| 工程 | 轨道数 | 片段数 | 用途 |
|---|---:|---:|---|
| Draft 1 | 3 | 127 | 原始工程 |
| Draft 2 | 4 | 128 | 字幕处理及风险提示图 |
| Draft 3 | 5 | 138 | Draft 2 加 10 个利益点图片片段 |

工程 1 的临时副本经过本工具处理后，可得到与 Draft 3 相同的结构规模：5 条轨道、138 个片段、22 个 video/photo material 和 11 个 material animation。重复规划为 no-op，rollback 后原文件哈希可完整恢复。

## 已实现功能

### 配置与计划

- `configs/catalog.jsonc` 统一登记、启停和发现多个项目配置。
- 每个项目使用一份带中文注释的 `config.jsonc` 集中管理全部效果。
- Catalog、Config Set 和六类组件的 closed JSON Schema。
- Catalog 中的项目 ID/路径、配置组件 `kind` 和引用关系校验。
- 产品名与利益点跨类别冲突检查。
- 利益点图片只能引用已批准的 `benefit_id`，不能重复内联自然语言触发词。
- 图片路径、SHA-256、尺寸和透明通道检查。
- Job 禁止内联产品名、利益点、风险图、利益点图或尾帧等业务内容。
- Plan 锁定 Job、Draft 和所有配置组件的 SHA-256。

### Draft 检查

- Draft 版本、fps、画布、时长和轨道统计。
- material、segment 和辅助 material 引用闭合检查。
- 重复 ID、悬空引用和无效时间范围检查。
- 视频与图片 material 分类。
- 媒体路径存在性及基础可读状态检查。
- `draft_info.json` 与 `template-2.tmp` 哈希关系检查。
- `.jypre/state.json` 托管状态检查。

### 字幕处理

- 只修改 Job 唯一选中的字幕轨及其引用的 text material。
- 字体资源解析。
- 字号、填充、描边、行间距、缩放和位置统一。
- 显式换行规则。
- 产品名和利益点 literal/alias 精确匹配。
- longest-match 加 priority 的重叠处理。
- 生成覆盖全文、连续、无重叠的完整富文本 ranges。
- 配置切换时从首次托管前保存的原始字幕文本重新生成，不在旧样式上叠加。

首个配置集使用：

```text
字体：特黑体
字号：5
填充：#FFFFFF
描边：#000000
描边宽度：0.08
缩放：250%
位置：x=0, y=-500
行间距：剪映界面值 5，对应 Draft 值 0.25
```

### 利益点图片

- 根据同一字幕内命中的 `benefit_id` 集合触发图片。
- 图片展示区间直接继承匹配字幕的目标时间范围。
- 支持每个业务视频分段恰好一个命中的严格基数校验。
- 自动创建 photo material、segment、独立 video track 及辅助 material。
- 支持位置、缩放、透明度、旋转和入场动画。
- 正确处理帧边界取整造成的 source/target duration 1 微秒差异。
- 当前淘宝闪购配置可生成 10 个“便利贴”入场利益点图片片段。

### 风险提示图

- 创建覆盖最终 Draft 时长的透明 PNG 图层。
- 风险提示位于字幕上方。
- 若尾帧延长 Draft，风险提示可覆盖延长后的最终时长。
- 显式配置为 `null` 时不添加；配置切换时只删除能够验证归属的旧托管对象。

### 逐视频尾帧

- 在选中的业务视频轨中，只处理引用 `materials.videos[type=video]` 的原始片段。
- 在每个业务视频片段结束后添加独立尾帧片段。
- 30 fps 下严格使用 90 帧表达 3 秒。
- 使用绝对帧边界换算微秒，不反复累加 33333 微秒。
- 前序分段要求存在无碰撞空档。
- 末段空间不足时延长 Draft，不能静默跳过。
- 不平移原视频、字幕、音频或剪辑点。

首个 `taobao-flash-v1` 配置将尾帧显式设置为 `null`；尾帧算法已通过自动测试，但仍需使用正式批准的尾帧图片完成剪映 UI 验收。

### Sidecar 与事务

工具会按需维护：

- `draft_info.json`
- `draft_meta_info.json`
- `key_value.json`
- `draft_virtual_store.json`
- `template-2.tmp`，仅当修改前与 `draft_info.json` 完全同哈希时同步
- `.jypre/state.json`

每次 apply：

1. 重新计算 Job、Draft 和配置哈希。
2. 验证保存的 plan 没有过期。
3. 备份所有将修改的文件到 `.jypre/backups/<run-id>/`。
4. 在内存中生成并验证完整目标状态。
5. 使用同目录临时文件、`fsync` 和 `os.replace` 写入。
6. 再次验证引用闭合和目标文件哈希。
7. 任一步失败时自动恢复原文件。

## 安全原则

- 应当只对上游创建的可修改工程副本执行 apply。
- 不直接修改参考模板或用户未明确指定的工程。
- 不根据图片文件名或字幕语义猜测业务配置。
- 不自动接管或删除看起来相似的人工图层。
- 只有 `.jypre/state.json` 中记录的对象，且轨道、片段、material、辅助引用和资产哈希仍一致时，才允许更新或删除。
- 不使用 `chmod -R`、`chmod 777`，不修改 TCC 数据库，不复制或伪造 `com.apple.macl`。
- 不通过清空 Draft 字段伪造“媒体已重连”。
- 执行 apply 前应关闭剪映，避免两个进程同时保存同一工程。

## 快速开始

要求：Python 3.10 或更高版本。

无需安装即可从项目根目录调用：

```bash
python3 scripts/preprocess_draft.py --help
```

CLI 始终输出 JSON，基本结构为：

```json
{
  "ok": true,
  "code": "operation_complete",
  "reason": "",
  "data": {}
}
```

失败时返回非零退出码，并在 `code` 和 `reason` 中说明原因。

## 推荐工作流

### 1. 查看并校验配置

```bash
python3 scripts/preprocess_draft.py list-configs \
  --config-root configs

python3 scripts/preprocess_draft.py validate-config \
  --config-root configs \
  --config-set taobao-flash-v1
```

该命令不读取或修改剪映工程。

### 2. 检查目标工程

```bash
python3 scripts/preprocess_draft.py inspect \
  --draft "/absolute/path/to/draft-copy"
```

`inspect` 是只读命令，可用于检查不受支持的 Draft 版本。

### 3. 准备 Job

Job 只选择配置和运行策略，不包含业务文案或图片覆盖：

```json
{
  "job_schema": 1,
  "draft_path": "/absolute/path/to/draft-copy",
  "config_root": "/absolute/path/to/jianying-preprocessing/configs",
  "config_set": "taobao-flash-v1",
  "media_manifest": null,
  "search_roots": [],
  "media_strategy": "reference-existing",
  "permission_strategy": "diagnose-only",
  "subtitle_track": {
    "name": "字幕",
    "on_ambiguous": "fail"
  },
  "strict": {
    "unmatched_product": true,
    "unmatched_benefit": true,
    "unmatched_benefit_image": true,
    "font_missing": true,
    "unmanaged_layer_conflict": true
  }
}
```

配置和 Job 的详细约束参见 [`references/config-and-job.md`](references/config-and-job.md)。

### 4. 生成锁定计划

```bash
python3 scripts/preprocess_draft.py plan \
  --job "/absolute/path/to/job.json" \
  --output "/absolute/path/to/plan.json"
```

Plan 文件必须保存在目标 Draft 目录之外。该命令不会修改 Draft。

Plan 包含：

- 输入文件和配置组件哈希。
- 媒体解析状态。
- 字幕、产品名和利益点命中统计。
- 利益点图片对应的字幕、业务视频和目标区间。
- 尾帧帧区间、碰撞结果和是否延长 Draft。
- 将修改的文件、目标哈希和 JSON path 白名单。
- 配置为 configured 或 disabled 的功能状态。

### 5. 应用计划

关闭剪映后执行：

```bash
python3 scripts/preprocess_draft.py apply \
  --job "/absolute/path/to/job.json" \
  --plan "/absolute/path/to/plan.json"
```

如果 plan 之后 Job、Draft、素材或任一配置文件发生变化，apply 会拒绝执行。

### 6. 验证期望状态

```bash
python3 scripts/preprocess_draft.py validate \
  --draft "/absolute/path/to/draft-copy" \
  --job "/absolute/path/to/job.json"
```

结构有效且重新规划为 no-op，才表示文件层面的期望状态已经满足。剪映 UI 内的最终视觉验收仍需要单独完成。

### 7. 回滚

```bash
python3 scripts/preprocess_draft.py rollback \
  --draft "/absolute/path/to/draft-copy" \
  --run-id "<apply 返回的 run_id>"
```

如果目标文件在 apply 后又被其他程序修改，rollback 会拒绝覆盖，避免破坏后续编辑结果。备份默认保留，便于审计。

## 配置体系

所有配置集先在 `configs/catalog.jsonc` 登记；每个项目只维护一份可直接编辑、带中文注释的 `config.jsonc`：

```text
configs/
├── catalog.jsonc
├── taobao-flash-v1/
│   └── config.jsonc
└── another-project-v1/
    └── config.jsonc
```

`config.jsonc` 必须显式包含六个带类型组件槽位：

- `subtitle_style`
- `product_names`
- `benefit_points`
- `benefit_images`
- `risk_warning`
- `end_frame`

其中 `benefit_images`、`risk_warning` 和 `end_frame` 可以为 JSON `null`。字段缺失、空字符串、空对象或字符串 `"null"` 都不是合法的关闭方式。

`.jsonc` 支持 `//` 和 `/* ... */` 中文注释，但不支持尾随逗号。首个配置集见 [`configs/taobao-flash-v1/config.jsonc`](configs/taobao-flash-v1/config.jsonc)，新增配置和尾帧示例见 [`references/config-and-job.md`](references/config-and-job.md)，Schema 位于 [`schemas/`](schemas/)。

## 项目结构

```text
jianying-preprocessing/
├── README.md
├── SKILL.md
├── agents/
│   └── openai.yaml
├── configs/
│   ├── catalog.jsonc
│   └── taobao-flash-v1/
│       └── config.jsonc
├── doc/
│   ├── jianying-preprocessing-solution.md
│   └── remaining-work.md
├── references/
│   ├── config-and-job.md
│   └── draft-v5.9.md
├── schemas/
├── scripts/
│   ├── preprocess_draft.py
│   └── jypre/
│       ├── cli.py
│       ├── config.py
│       ├── draft.py
│       ├── photos.py
│       ├── planner.py
│       ├── text.py
│       └── transaction.py
└── tests/
```

主要模块职责：

| 模块 | 职责 |
|---|---|
| `config.py` | 加载、隔离并验证配置集 |
| `draft.py` | 读取 Draft、建立 material 索引、检查引用和输出检查报告 |
| `text.py` | 字体解析、字幕转换和富文本 range 生成 |
| `photos.py` | 利益点图片、风险提示、尾帧及 sidecar 对象生成与托管清理 |
| `planner.py` | Job 校验、业务轨选择、期望状态生成和 plan 锁定 |
| `transaction.py` | 原子写入、事务备份、自动恢复和显式 rollback |
| `cli.py` | 七个 CLI 子命令及机器可读输出 |

## 测试与质量检查

运行标准库测试：

```bash
PYTHONPATH=scripts python3 -m unittest discover -s tests -v
```

当前测试覆盖：

- 三个真实参考 Draft 的结构与引用。
- Catalog、JSONC 注释解析和首个统一配置集校验。
- 跨类别组件混用失败。
- 人工参考图层不被自动接管。
- 字幕和利益点命中数量。
- 利益点图片层级、时间范围和 1 微秒帧相位差。
- 尾帧 90 帧规划及末段延长。
- 临时 Draft 的 apply、二次 no-op 和 rollback 哈希恢复。

代码质量检查：

```bash
ruff format --check .
ruff check .
```

## 当前限制

以下能力尚未完成，CLI 会明确拒绝对应模式，不会静默降级：

- 基于 media manifest 和有限 search roots 的素材解析。
- 修改素材路径后的完整原生重连确认。
- 剪映文件选择器和 macOS TCC 授权自动化。
- POSIX owner 权限最小修复。
- 将媒体 APFS clone/copy 到 Draft staging。
- ffprobe 深度媒体探测。
- 剪映 UI 内视觉验收、保存和重新打开后的自动回归。
- `derive_config.py` 配置派生工具。
- 独立干净环境中的 CLI 安装和跨平台发布验证。

详细任务、原因、风险边界和验收标准见 [`doc/remaining-work.md`](doc/remaining-work.md)。

## 设计与研究文档

- [`doc/jianying-preprocessing-solution.md`](doc/jianying-preprocessing-solution.md)：三个参考工程的差异研究、Draft 关系模型、配置设计和完整实现方案。
- [`doc/remaining-work.md`](doc/remaining-work.md)：尚未完成的工作及推荐实施顺序。
- [`references/config-and-job.md`](references/config-and-job.md)：配置集、Job、计划锁和 apply 契约。
- [`references/draft-v5.9.md`](references/draft-v5.9.md)：剪映 5.9 Draft 结构及不可变约束。
- [`SKILL.md`](SKILL.md)：供后续 Codex 自动选择和执行本项目 CLI 的精简操作规范。
