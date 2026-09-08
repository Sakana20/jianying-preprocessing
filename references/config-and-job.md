# 配置与 Job 使用说明

## 统一配置目录

所有项目配置由 [configs/catalog.jsonc](../configs/catalog.jsonc) 统一登记。每个业务项目只有一份人工维护文件：

```text
configs/
├── catalog.jsonc
├── taobao-flash-v1/
│   └── config.jsonc
└── another-project-v1/
    └── config.jsonc
```

`.jsonc` 支持 `// 行注释` 和 `/* 块注释 */`。注释会在解析时删除，不会进入 Draft。配置值仍遵循严格 JSON：字符串使用双引号，不支持尾随逗号。

一个 `config.jsonc` 集中管理：

- 字幕字体、字号、颜色、描边、位置、缩放和行间距；
- 产品名及别名高亮；
- 每个利益点各自的高亮与换行；
- 由 `benefit_id` 触发的利益点图片、位置和动画；
- 风险提示图；
- 每段视频后的尾帧。

`benefit_images`、`risk_warning`、`end_frame` 整项写为 JSON `null` 即关闭。字段缺失、`{}`、`[]` 或字符串 `"null"` 都不是关闭方式。

## 新增一个项目配置

1. 复制 `configs/taobao-flash-v1/config.jsonc` 到新目录，例如 `configs/my-product-v1/config.jsonc`。
2. 只把顶层的 `config_set_id` 改成 `my-product-v1`，并同步修改 `display_name`。
3. 将 `approval.status` 暂时设为 `draft`，修改字幕、产品词、利益点和素材。
4. 在 `configs/catalog.jsonc.config_sets` 中登记 ID、显示名、路径、标签和启用状态。
5. 运行 `list-configs` 和 `validate-config`。人工确认后把 `approval.status` 改为 `approved`，才允许 plan/apply。

```bash
python3 scripts/preprocess_draft.py list-configs --config-root configs
python3 scripts/preprocess_draft.py validate-config --config-root configs --config-set my-product-v1
```

修改图片后需要同步更新 SHA-256：

```bash
shasum -a 256 /absolute/path/to/image.png
```

## 尾帧配置示例

把 `config.jsonc` 中的 `"end_frame": null` 替换为以下对象，并同步修改素材路径、SHA-256 和尺寸：

```jsonc
"end_frame": {
  "schema_version": 1,
  "kind": "end_frame",
  "asset": {
    "path": "/absolute/path/to/end-frame.png",
    "sha256": "64位小写SHA-256",
    "width": 720,
    "height": 1280
  },
  "duration_us": 3000000,
  "placement": "after_each_video_segment",
  "segment_selector": {
    "track_type": "video",
    "track_name": "视频素材",
    "material_type": "video"
  },
  "collision_policy": "require_gap",
  "last_segment_policy": "extend_draft",
  "risk_overlay_coverage": "final_draft"
}
```

## Job 契约

Job 只选择已登记的 `config_set`，不得内联或覆盖业务内容：

```json
{
  "job_schema": 1,
  "draft_path": "/absolute/path/to/a-writable-draft-copy",
  "config_root": "/absolute/path/to/jianying-preprocessing/configs",
  "config_set": "taobao-flash-v1",
  "media_manifest": null,
  "search_roots": [],
  "media_strategy": "reference-existing",
  "permission_strategy": "diagnose-only",
  "subtitle_track": {"name": "字幕", "on_ambiguous": "fail"},
  "strict": {
    "unmatched_product": true,
    "unmatched_benefit": true,
    "unmatched_benefit_image": true,
    "font_missing": true,
    "unmanaged_layer_conflict": true
  }
}
```

## 锁定计划与执行

```bash
python3 scripts/preprocess_draft.py plan --job /absolute/job.json --output /absolute/plan.json
python3 scripts/preprocess_draft.py apply --job /absolute/job.json --plan /absolute/plan.json
```

Plan 同时锁定 catalog、完整 `config.jsonc` 和每个组件的哈希。任何配置或注释发生变化后，都必须重新 plan。Apply 会重新验证 Job、Draft 与全部配置哈希，备份所有目标文件，进行原子写入，并在失败时自动恢复。

执行 Apply 时不要让剪映保持运行或打开目标 Draft。
