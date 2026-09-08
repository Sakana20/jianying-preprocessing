# 剪映工程预处理：未完成工作清单

## 文档目的

本文记录 `jianying-preprocessing` v0.1 尚未完成的能力，作为后续 Codex 开发和验收入口。

当前已实现范围以 `doc/jianying-preprocessing-solution.md`、`SKILL.md` 和 CLI 实际行为为准。本文不代表授权扩大：所有会修改剪映工程、文件权限或通过 UI 操作剪映的步骤，仍必须针对用户明确指定的可修改工程副本执行。

## 当前基线

v0.1 已实现：

- `list-configs`、`validate-config`、`inspect`、`plan`、`apply`、`validate`、`rollback` 七个 CLI 子命令。
- Catalog 统一管理、每项目单个中文注释 `config.jsonc`，以及 Catalog、Config Set 和六类组件的 closed JSON Schema。
- 字幕基础样式、布局、换行、产品名高亮和利益点高亮。
- 利益点图片、风险提示图、逐业务视频尾帧的 Draft 结构生成。
- `draft_info.json`、`draft_meta_info.json`、`key_value.json`、`draft_virtual_store.json` 和条件性 `template-2.tmp` 同步。
- `.jypre/state.json` 托管对象归属、哈希锁、事务备份、自动恢复、显式 rollback 和幂等运行。
- 三个参考工程的只读结构回归，以及工程 1 临时副本的 apply/no-op/rollback 回归。

以下工作尚未完成。

## 1. 精确媒体 Manifest 与确定性重连

### 当前状态

Job 保留了 `media_manifest`、`search_roots` 和 `media_strategy` 字段，但 v0.1 只接受：

```json
{
  "media_manifest": null,
  "search_roots": [],
  "media_strategy": "reference-existing"
}
```

当前只验证 Draft 中已有路径的文件存在且 owner 可读，不会寻找替代文件，也不会修改素材路径。

### 待实现

1. 定义并固化 `media-manifest.schema.json`。
2. Manifest 至少支持：
   - `material_id`
   - `segment_id`
   - `original_basename`
   - `expected_path`
   - `size`
   - `duration_us`
   - `width`
   - `height`
   - `has_audio`
   - 可选 `sha256`
   - 可选 volume UUID 和卷内相对路径
3. 实现确定性候选解析顺序：
   - Manifest 的 `expected_path`
   - Draft 现有绝对路径
   - Job 显式提供的有限 `search_roots`
4. 候选过滤顺序：basename、文件大小、宽高、音频、时长一帧容差，仍有歧义时再计算 SHA-256。
5. 处理 macOS Unicode NFC/NFD 文件名和大小写敏感卷。
6. 只有候选身份唯一时才允许更新 `materials.videos[].path`。
7. 路径更新必须保留 material ID、segment ID、原时间线和既有辅助引用。

### 验收标准

- 唯一候选能生成明确的 relink plan，并仅修改目标 video material 的 `path`。
- 0 个或多个候选均失败且不写 Draft。
- Manifest 或素材在 plan 后变化会使 apply 失效。
- 路径更新后引用闭合、片段时间范围和原 ID 完全不变。
- NFC/NFD、外接盘重挂载及同名多文件均有自动化 fixture。

## 2. 剪映原生媒体重连与 TCC 授权

### 未直接使用 JSON 模拟重连的原因

参考工程的原生重连前后没有出现可证明稳定的连接标志：路径、素材 ID、片段 ID和时间线均未变化，只观察到若干普通字段变化和辅助 UUID 刷新。这些变化不能证明剪映进程已获得文件访问权限，也不能视为稳定跨版本协议。

macOS 命令行进程可读取文件，不代表剪映 bundle id `com.lemon.lvpro` 拥有相同的 Files & Folders、Desktop 或 Removable Volumes TCC 授权。因此不得通过清空 JSON 字段、复制 `com.apple.macl`、修改 TCC 数据库或删除 quarantine 来伪造重连成功。

### 待实现

1. 识别剪映是否运行及目标工程是否位于编辑页。
2. 在用户明确允许时启动或切换到剪映。
3. 定位“媒体丢失/重新链接媒体”原生入口。
4. 通过系统文件选择器选择 Manifest 已唯一解析的文件或授权目录。
5. 处理首次授权、外接卷授权、重复文件、错误格式、取消和超时弹窗。
6. 等待剪映完成素材验证和 Draft 保存。
7. 重新读取工程文件，并结合 UI 状态确认红色离线/不支持媒体提示消失。
8. 记录 UI 操作审计结果，不把单纯 JSON 字段变化当作成功依据。

### 停止条件

- 需要用户确认系统权限弹窗。
- 文件选择器中的目标无法与 Manifest 唯一对应。
- 剪映版本、窗口结构或文案不在已验证范围。
- 遇到登录、风控、付费或不可解释的警告弹窗。
- 重连后 Draft 引用、素材身份或时间线发生非计划变化。

### 验收标准

- 在新的工程 1 克隆上复现离线状态，再通过自动流程完成原生重连。
- 剪映 UI 不再显示离线或格式不支持。
- 保存、关闭、重新打开后仍保持在线。
- 10 个业务视频的 ID、片段 ID、时间范围和素材身份均保持一致。
- 取消、授权拒绝、文件选错及 UI 超时均安全失败，不执行后续预处理。

## 3. POSIX 最小权限诊断与修复

### 当前状态

v0.1 只接受：

```json
{"permission_strategy": "diagnose-only"}
```

尚未执行 `chmod` 或 ACL 修改。

### 待实现

1. 将权限问题分类为：
   - 文件不存在
   - 外接卷未挂载
   - 父目录不可 traverse
   - owner 不可读
   - ACL 明确拒绝
   - TCC 授权不足
   - 文件可读但剪映原生导入状态异常
2. 增加显式 `repair-posix-owner` 模式。
3. 只对 Manifest 精确目标增加文件 owner read `u+r`。
4. 只对访问链中必要父目录增加 owner execute `u+x`。
5. 在 plan 中列出精确路径、旧 mode、新 mode 和 rollback 操作。
6. 将旧 mode 写入事务备份并由 rollback 恢复。

### 禁止事项

- `chmod -R`
- `chmod 777`
- 清理整盘 ACL
- 修改或替换 TCC 数据库
- 复制、清除或伪造 `com.apple.macl`
- 将 symlink 当作 TCC 绕过机制

### 验收标准

- 只修改 plan 白名单中的精确文件或目录。
- 无显式策略时严格只诊断。
- 修复前后 mode 可审计并可 rollback。
- POSIX 修复不能被报告成 TCC 修复或原生重连成功。

## 4. Draft 内受控媒体 Staging

### 目的

当素材身份已唯一确认，但剪映对原目录持续无权限时，可由用户选择将媒体放入目标 Draft 下受控目录，例如：

```text
Resources/local_media/
```

### 待实现

1. 在 Job 中定义显式 staging 策略：`disabled`、`apfs-clone` 或 `copy`。
2. 预估所需空间并输出到 plan。
3. 优先尝试 APFS clone；不可用时只有用户允许 `copy` 才能完整复制。
4. 使用临时文件、fsync 和原子 rename。
5. 复制后重新验证大小、媒体属性和 SHA-256。
6. 更新 Draft 路径，同时把新文件和旧路径记录进 `.jypre/state.json`。
7. rollback 只删除本次事务创建且哈希未改变的 staging 文件。

### 验收标准

- 磁盘空间不足时在写入前失败。
- 已存在同名但内容不同的文件不会被覆盖。
- 重复 apply 复用同内容 staging 文件。
- rollback 不删除用户后来修改过的文件。

## 5. 完整媒体探测

### 当前状态

`inspect` 当前报告 Draft 中媒体路径、存在性和基础可读状态，尚未执行 ffprobe 深度分析。

### 待实现

1. 使用 ffprobe 读取：容器时长、视频 codec、宽高、像素格式、帧率、音频 codec 和音频流存在性。
2. 将 Draft 声明与实际媒体对比。
3. 使用目标 Draft fps 计算一帧容差。
4. 区分文件不可读、ffprobe 失败、格式异常和 Draft 元数据不匹配。
5. 对 ffprobe 结果增加按文件 stat/hash 的缓存，避免重复探测。

### 验收标准

- 当前 10 个业务视频应识别为 H.264、1080×1920、yuv420p、含 AAC 音频。
- Draft 与容器时长误差不超过一帧。
- 图片 material 不进入业务视频 ffprobe 检查。
- 一帧封面占位素材不被识别为业务视频。

## 6. 剪映内视觉验收与保存后回归

### 当前状态

v0.1 已完成 JSON 结构、引用、时间范围、配置命中、幂等和 rollback 自动测试，但尚未在新的克隆工程内自动打开剪映做视觉验收。

### 待实现

1. 创建专用可丢弃工程克隆，禁止使用参考工程原件。
2. 打开处理后的工程并定位以下时间点：
   - 普通字幕
   - 产品名字幕
   - 利益点字幕及利益点图片入场
   - 风险提示图覆盖区间
   - 每个尾帧区间
3. 检查字幕位置、缩放、字体、描边、换行和高亮。
4. 检查利益点图片位置、层级、持续时间和“便利贴”入场动画。
5. 检查风险提示透明度和最终 Draft 全时长覆盖。
6. 检查尾帧在每段结束处准确持续 3 秒，末段延长正确。
7. 在剪映中保存一次，关闭并重新打开。
8. 重新运行 `inspect` 和 `validate`，确认剪映没有改坏引用或丢失托管对象。
9. 刷新并检查工程封面。

### 验收标准

- 无红色离线/格式不支持提示。
- 视觉效果与工程 2/3 对应人工结果一致。
- 保存和重启后仍然一致。
- 剪映产生的允许范围内 UUID churn 不被误报为业务差异。
- 所有非计划时间线、ID 和未知字段保持不变。

## 7. 尾帧真实配置集验证

### 当前状态

尾帧规划与 Draft 生成逻辑已经实现并通过自动化测试：30 fps 下 3 秒等于 90 帧，前 9 段使用已有 300 帧空档，第 10 段将 Draft 从 7535 帧延长到 7625 帧。

当前 `taobao-flash-v1` 的 `end_frame` 为 `null`，因此尚未使用一张人工批准的真实尾帧图片进行剪映 UI 验收。

### 待实现

1. 为实际产品准备独立配置集和已批准尾帧图片。
2. 写入真实 SHA-256、720×1280 尺寸及配置集归属。
3. 验证尾帧图与利益点图、风险提示图的 path/hash 不冲突。
4. 在克隆 Draft 中执行 apply 和视觉验收。
5. 验证非空风险提示覆盖延长后的最终时长。

## 8. 配置派生工具 `derive_config.py`

### 待实现

提供一个只读辅助 CLI，从源工程和人工处理后工程生成候选差异报告及配置草案：

```text
python3 scripts/derive_config.py --before <draft> --after <draft> --output <directory>
```

要求：

- 只输出候选配置，不修改参考 Draft。
- 默认生成 `approval.status = "draft"`。
- 自动区分业务语义候选和机器相关字段、UUID churn、复制元数据。
- 不通过 OCR 或语言模型自动批准产品名、利益点和图片用途。
- 必须经人工复核后才能把状态改为 `approved`。

## 9. 更完整的验证器

### 待实现

1. 校验 text rich ranges 对 BMP、emoji 和补充平面字符采用的实际索引单位。
2. 增加 UTF-16 code unit fixture；验证前继续拒绝不能安全映射的文本。
3. 校验每个托管 sidecar ID 和 asset-level/segment-level 映射语义。
4. 校验 animation cache 不仅路径唯一，还应验证 resource/effect identity。
5. 校验 font cache 的 resource ID、文件名和可选文件 hash。
6. 对 `draft_meta_info.tm_duration` 等时长 sidecar 建立已验证更新规则，特别是启用尾帧时。
7. 增加 plan 的逐 JSON path semantic diff，而不仅是文件级 target hash 和路径白名单。
8. 增加配置从非空切换到 `null`、跨配置集切换、人工修改托管轨道和资产消失的完整 fixture。

## 10. CLI 安装与发布

### 当前状态

当前可靠调用方式是：

```bash
python3 scripts/preprocess_draft.py <command> ...
```

`pyproject.toml` 已声明 `jypre` console script，但尚未完成独立干净环境的安装回归和版本发布。

### 待实现

1. 在干净 Python 3.10、3.11、3.12、3.13 环境测试安装。
2. 固化开发依赖和质量检查命令。
3. 验证 macOS Intel/Apple Silicon；Windows 仅在明确支持 Draft 5.9 文件布局后开放 apply。
4. 增加版本迁移策略和 state schema 迁移器。
5. 在安装或复制为个人 Skill 前运行 `quick_validate.py`。

## 推荐实施顺序

1. 媒体 Manifest Schema、ffprobe 和确定性候选解析。
2. 精确路径 relink plan/apply 与回归 fixture。
3. POSIX 权限诊断及可回滚的 owner 最小修复。
4. staging clone/copy。
5. 剪映原生重连与 TCC UI 自动化。
6. 克隆工程视觉验收、保存和重启回归。
7. 使用真实尾帧配置完成 UI 验收。
8. `derive_config.py`、更深的 sidecar/Unicode 验证和 CLI 发布。

## 完成定义

只有同时满足以下条件，才能认为首版完整交付：

- 通过类型化配置、Draft 结构、媒体探测、权限分类和计划哈希全部校验。
- 丢失媒体可通过确定性路径更新或用户授权的原生重连恢复，且不会假报成功。
- 字幕、高亮、利益点图片、风险提示和尾帧在剪映 UI 中通过视觉验收。
- 保存、关闭、重新打开后结果稳定。
- 相同 Job 二次 plan 为 no-op。
- 配置切换和显式 `null` 可安全清理所有且仅清理可验证归属的托管对象。
- 任一写入失败均可自动恢复，用户也可用 run ID 显式 rollback。
- 原始参考工程和任何未授权工程从未被修改。
