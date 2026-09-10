from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jypre.config import ConfigError, list_config_sets, load_config
from jypre.draft import inspect_draft, load_draft
from jypre.errors import ApplyError, DraftError
from jypre.planner import build_plan
from jypre.transaction import _jianying_running, apply_plan, rollback
from jypre.util import canonical_json_bytes, read_jsonc, sha256_file, strip_jsonc_comments

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = Path("/Users/sakana/Movies/JianyingPro/User Data/Projects/com.lveditor.draft")


def _local_samples_available() -> bool:
    return all((SAMPLES / str(number) / "draft_info.json").is_file() for number in (1, 2, 3))


class JypreTests(unittest.TestCase):
    @unittest.skipUnless(_local_samples_available(), "local JianYing reference drafts unavailable")
    def test_three_reference_drafts_have_documented_shapes(self) -> None:
        expected = {1: (3, 127), 2: (4, 128), 3: (5, 138)}
        for number, (tracks, segments) in expected.items():
            report = inspect_draft(load_draft(SAMPLES / str(number)))
            self.assertEqual(report["track_count"], tracks)
            self.assertEqual(report["segment_count"], segments)
            self.assertTrue(report["references"]["valid"])

    def test_config_set_validates(self) -> None:
        config = load_config(ROOT / "configs", "taobao-flash-v1", require_approved=True)
        self.assertEqual(config.config_set_id, "taobao-flash-v1")
        self.assertIsNone(config.components["end_frame"])
        self.assertTrue(config.config_path.name.endswith(".jsonc"))
        catalog = list_config_sets(ROOT / "configs")
        self.assertEqual(catalog["default_config_set"], "taobao-flash-v1")
        self.assertEqual(
            {item["config_set_id"] for item in catalog["config_sets"]},
            {"taobao-flash-v1", "taobaoshangou-normal", "taobaoshangou-normal-side-compliance"},
        )
        source = config.config_path.read_text(encoding="utf-8")
        self.assertIn("// ==================== 利益点高亮与换行", source)

        normal = load_config(ROOT / "configs", "taobaoshangou-normal", require_approved=True)
        self.assertEqual(normal.data["display_name"], "淘宝闪购-常规")
        self.assertIsNone(normal.components["benefit_images"])
        self.assertIsNotNone(normal.components["risk_warning"])
        self.assertIsNotNone(normal.components["end_frame"])

        side_compliance = load_config(
            ROOT / "configs", "taobaoshangou-normal-side-compliance", require_approved=True
        )
        self.assertEqual(side_compliance.data["display_name"], "淘宝闪购-常规侧合规")
        self.assertEqual(side_compliance.components["benefit_points"]["items"][0]["literal"], "大额红包")
        self.assertEqual(
            side_compliance.components["benefit_points"]["items"][0]["style"],
            normal.components["benefit_points"]["items"][0]["style"],
        )

    def test_jsonc_parser_preserves_comment_markers_inside_strings(self) -> None:
        source = '{/* 中文块注释 */"url":"https://example.com/a//b","value":1// 行注释\n}'
        self.assertEqual(json.loads(strip_jsonc_comments(source)), {"url": "https://example.com/a//b", "value": 1})

    @patch("jypre.transaction.subprocess.run")
    def test_jianying_process_probe_is_fail_closed(self, run) -> None:
        run.return_value.returncode = 3
        with self.assertRaisesRegex(ApplyError, "cannot determine whether JianYing is running"):
            _jianying_running()
        pattern = run.call_args.args[0][2]
        self.assertIn("VideoFusion-macOS", pattern)

    @unittest.skipUnless(_local_samples_available(), "local JianYing reference drafts unavailable")
    def test_plan_reproduces_reference_counts_and_hits(self) -> None:
        build = build_plan(ROOT / "tests/fixtures/sample-job.json")
        info = build.desired.info
        self.assertEqual(len(info["tracks"]), 5)
        self.assertEqual(sum(len(track["segments"]) for track in info["tracks"]), 138)
        self.assertEqual(len(info["materials"]["videos"]), 22)
        self.assertEqual(len(info["materials"]["material_animations"]), 11)
        benefit_track = info["tracks"][2]
        self.assertEqual(benefit_track["segments"][-1]["source_timerange"]["duration"], 3_933_333)
        self.assertEqual(benefit_track["segments"][-1]["target_timerange"]["duration"], 3_933_334)
        self.assertEqual(
            [track["name"] for track in info["tracks"]],
            ["封面 / 主视频", "视频素材", "", "字幕", ""],
        )
        self.assertEqual(
            [track["segments"][0]["track_render_index"] for track in info["tracks"]],
            [0, 1, 2, 3, 4],
        )
        self.assertEqual(info["tracks"][-1]["segments"][0]["target_timerange"]["duration"], 251_166_666)
        benefit_material = next(
            item for item in info["materials"]["texts"] if json.loads(item["content"])["text"].startswith("最高25元")
        )
        benefit_content = json.loads(benefit_material["content"])
        self.assertEqual([style["range"] for style in benefit_content["styles"]], [[0, 2], [2, 10], [10, 16], [16, 21]])
        key_values = build.desired.documents["key_value.json"]
        self.assertEqual(len(key_values), 12)
        self.assertEqual(build.plan["subtitles"]["product_hits"], {"taobao-flash": 10})
        self.assertEqual(
            build.plan["subtitles"]["benefit_hits"],
            {"coupon-25-no-threshold": 10, "subsidy-card-90-percent": 10},
        )
        self.assertEqual(len(build.plan["benefit_images"]), 10)

    @unittest.skipUnless(_local_samples_available(), "local JianYing reference drafts unavailable")
    def test_manual_reference_layers_are_not_adopted(self) -> None:
        source_job = json.loads((ROOT / "tests/fixtures/sample-job.json").read_text(encoding="utf-8"))
        source_job["draft_path"] = str(SAMPLES / "3")
        with tempfile.TemporaryDirectory() as temporary:
            job_path = Path(temporary) / "job.json"
            job_path.write_bytes(canonical_json_bytes(source_job))
            with self.assertRaisesRegex(DraftError, "unmanaged configured-asset layers"):
                build_plan(job_path)

    @unittest.skipUnless(_local_samples_available(), "local JianYing reference drafts unavailable")
    def test_end_frame_plan_uses_frame_boundaries_and_extends_last_segment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            config_root = tmp_path / "configs"
            shutil.copytree(ROOT / "configs", config_root)
            source_config = read_jsonc(config_root / "taobao-flash-v1/config.jsonc")
            config_dir = config_root / "end-test"
            config_dir.mkdir()
            source_config["config_set_id"] = "end-test"
            source_config["display_name"] = "尾帧测试"
            risk = source_config["risk_warning"]
            end_frame = {
                "schema_version": 1,
                "kind": "end_frame",
                "asset": {key: risk["asset"][key] for key in ("path", "sha256", "width", "height")},
                "duration_us": 3_000_000,
                "placement": "after_each_video_segment",
                "segment_selector": {
                    "track_type": "video",
                    "track_name": "视频素材",
                    "material_type": "video",
                },
                "collision_policy": "require_gap",
                "last_segment_policy": "extend_draft",
                "risk_overlay_coverage": "final_draft",
            }
            source_config["benefit_images"] = None
            source_config["risk_warning"] = None
            source_config["end_frame"] = end_frame
            (config_dir / "config.jsonc").write_bytes(canonical_json_bytes(source_config))
            catalog_path = config_root / "catalog.jsonc"
            catalog = read_jsonc(catalog_path)
            catalog["config_sets"].append(
                {
                    "config_set_id": "end-test",
                    "display_name": "尾帧测试",
                    "description": "测试逐视频尾帧",
                    "tags": ["test"],
                    "path": "end-test/config.jsonc",
                    "enabled": True,
                }
            )
            catalog_path.write_bytes(canonical_json_bytes(catalog))
            source_job = json.loads((ROOT / "tests/fixtures/sample-job.json").read_text(encoding="utf-8"))
            source_job["config_root"] = str(config_root)
            source_job["config_set"] = "end-test"
            job_path = tmp_path / "job.json"
            job_path.write_bytes(canonical_json_bytes(source_job))
            build = build_plan(job_path)
            self.assertEqual(len(build.plan["end_frames"]), 10)
            self.assertEqual(build.desired.info["duration"], 254_166_666)
            self.assertTrue(build.plan["end_frames"][-1]["extends_draft"])
            self.assertTrue(all(item["duration_us"] == 3_000_000 for item in build.plan["end_frames"]))

    @unittest.skipUnless(_local_samples_available(), "local JianYing reference drafts unavailable")
    @patch("jypre.transaction._jianying_running", return_value=False)
    def test_apply_is_idempotent_and_rollback_restores(self, _process_probe) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            draft = tmp_path / "draft"
            shutil.copytree(SAMPLES / "1", draft)
            original_hashes = {
                name: sha256_file(draft / name)
                for name in ("draft_info.json", "draft_meta_info.json", "key_value.json", "template-2.tmp")
            }
            source_job = json.loads((ROOT / "tests/fixtures/sample-job.json").read_text(encoding="utf-8"))
            source_job["draft_path"] = str(draft)
            job_path = tmp_path / "job.json"
            job_path.write_bytes(canonical_json_bytes(source_job))
            build = build_plan(job_path)
            plan_path = tmp_path / "plan.json"
            plan_path.write_bytes(canonical_json_bytes(build.plan))
            result = apply_plan(job_path, plan_path)
            self.assertTrue(result["applied"])
            self.assertTrue(inspect_draft(load_draft(draft))["references"]["valid"])
            self.assertTrue(build_plan(job_path).plan["no_op"])
            rollback_result = rollback(draft, result["run_id"])
            self.assertTrue(rollback_result["rolled_back"])
            self.assertEqual({name: sha256_file(draft / name) for name in original_hashes}, original_hashes)
            self.assertFalse((draft / ".jypre/state.json").exists())

    def test_cross_category_component_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            shutil.copytree(ROOT / "configs", tmp_path / "configs")
            config_path = tmp_path / "configs/taobao-flash-v1/config.jsonc"
            config = read_jsonc(config_path)
            config["product_names"] = config["benefit_points"]
            config_path.write_bytes(canonical_json_bytes(config))
            with self.assertRaisesRegex(ConfigError, "product_names.kind"):
                load_config(tmp_path / "configs", "taobao-flash-v1")


if __name__ == "__main__":
    unittest.main()
