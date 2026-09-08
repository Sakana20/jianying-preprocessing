from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .config import config_report, list_config_sets, load_config
from .draft import inspect_draft, load_draft, validate_references
from .errors import JypreError
from .planner import build_plan
from .transaction import apply_plan, rollback
from .util import canonical_json_bytes


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jypre", description="Preprocess JianYing 5.9 drafts")
    parser.add_argument("--version", action="version", version="jypre 0.1.0")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_configs = subparsers.add_parser("list-configs", help="list centrally registered config sets")
    list_configs.add_argument("--config-root", required=True, type=Path)

    validate_config = subparsers.add_parser("validate-config", help="validate one typed config set")
    validate_config.add_argument("--config-root", required=True, type=Path)
    validate_config.add_argument("--config-set", required=True)

    inspect = subparsers.add_parser("inspect", help="inspect a Draft without changing it")
    inspect.add_argument("--draft", required=True, type=Path)

    plan = subparsers.add_parser("plan", help="build a read-only locked plan")
    plan.add_argument("--job", required=True, type=Path)
    plan.add_argument("--output", type=Path, help="optional path outside the Draft for the saved plan")

    apply = subparsers.add_parser("apply", help="apply an unchanged saved plan transactionally")
    apply.add_argument("--job", required=True, type=Path)
    apply.add_argument("--plan", required=True, type=Path)

    validate = subparsers.add_parser("validate", help="validate Draft structure and desired state")
    validate.add_argument("--draft", required=True, type=Path)
    validate.add_argument("--job", type=Path)

    rollback_parser = subparsers.add_parser("rollback", help="restore files from an apply backup")
    rollback_parser.add_argument("--draft", required=True, type=Path)
    rollback_parser.add_argument("--run-id", required=True)
    return parser


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))


def _success(code: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "code": code, "reason": "", "data": data}


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "list-configs":
            _emit(_success("config_list", list_config_sets(args.config_root)))
        elif args.command == "validate-config":
            config = load_config(args.config_root, args.config_set)
            _emit(_success("valid_config", config_report(config)))
        elif args.command == "inspect":
            _emit(_success("inspection_complete", inspect_draft(load_draft(args.draft))))
        elif args.command == "plan":
            plan = build_plan(args.job).plan
            if args.output:
                output = args.output.expanduser().resolve()
                draft = Path(plan["draft_path"])
                try:
                    output.relative_to(draft)
                except ValueError:
                    pass
                else:
                    raise JypreError("plan --output must be outside the target Draft")
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(canonical_json_bytes(plan))
                plan = {**plan, "saved_to": str(output)}
            _emit(_success("plan_complete", plan))
        elif args.command == "apply":
            _emit(_success("apply_complete", apply_plan(args.job, args.plan)))
        elif args.command == "validate":
            bundle = load_draft(args.draft)
            structural = validate_references(bundle.info)
            desired = None
            if args.job:
                plan = build_plan(args.job).plan
                if Path(plan["draft_path"]) != args.draft.expanduser().resolve():
                    raise JypreError("job draft_path does not match --draft")
                desired = {"no_op": plan["no_op"], "plan_id": plan["plan_id"], "changes": plan["changes"]}
            _emit(_success("validation_complete", {"structural": structural, "desired_state": desired}))
            if not structural["valid"] or (desired and not desired["no_op"]):
                return 2
        elif args.command == "rollback":
            _emit(_success("rollback_complete", rollback(args.draft, args.run_id)))
        return 0
    except JypreError as exc:
        _emit({"ok": False, "code": exc.code, "reason": str(exc), "data": {}})
        return 2
    except Exception as exc:  # defensive CLI boundary
        _emit({"ok": False, "code": "internal_error", "reason": str(exc), "data": {}})
        return 3


if __name__ == "__main__":
    sys.exit(main())
