"""意图识别离线评测(学习版)。

用固定评测集跑规则意图分类器(纯函数、确定性、零 API 消耗),输出总体
准确率和分意图准确率,并与已保存的基线对比,防止改动词表或路由时意图
质量悄悄退化。自动测试(check.sh)会跑同一份考卷,门槛为总体准确率 ≥ 0.90。

用法(在 backend/ 目录下):

    # 跑一次评测,打印每题判定和聚合指标
    uv run python -m teachx.evals.run_intent_eval

    # 把当前分数保存为基线(基线文件提交进 Git,作为回归基准)
    uv run python -m teachx.evals.run_intent_eval --save ../evals/baselines/intent_rules.json

    # 与基线对比,任一准确率下降超过容差(默认 0.05)则以退出码 1 失败
    uv run python -m teachx.evals.run_intent_eval --baseline ../evals/baselines/intent_rules.json

说明:本脚本只评测规则分类器——它可以从 Mock 起跑、任何人任何机器跑出
同一分数。LLM 识别路径(parse_intent_json / detect_intent)由单元测试桩
覆盖,不进 CI,避免消耗真实 API 额度。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from teachx.runtime.intents import classify_by_rules

DEFAULT_DATASET = (
    Path(__file__).resolve().parents[3] / "evals" / "datasets" / "intent_classification.json"
)
REGRESSION_TOLERANCE = 0.05
ACCURACY_THRESHOLD = 0.90


def load_dataset(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("samples",):
        if key not in data:
            raise ValueError(f"评测集缺少字段: {key}")
    for index, sample in enumerate(data["samples"], start=1):
        if not sample.get("text") or not sample.get("intent"):
            raise ValueError(f"第 {index} 个样本缺少 text 或 intent 字段")
    return data


def run_eval(dataset_path: Path) -> dict[str, Any]:
    """对评测集逐条跑规则分类器,输出准确率与错误明细。"""

    dataset = load_dataset(dataset_path)
    per_intent: dict[str, dict[str, int]] = {}
    misclassified: list[dict[str, str]] = []
    correct = 0
    total = 0
    for sample in dataset["samples"]:
        expected = str(sample["intent"])
        predicted = classify_by_rules(str(sample["text"])).intent
        bucket = per_intent.setdefault(expected, {"total": 0, "correct": 0})
        bucket["total"] += 1
        total += 1
        if predicted == expected:
            correct += 1
            bucket["correct"] += 1
        else:
            misclassified.append(
                {"text": str(sample["text"]), "expected": expected, "predicted": predicted}
            )
    accuracy = correct / total if total else 0.0
    per_intent_accuracy = {
        intent: bucket["correct"] / bucket["total"] if bucket["total"] else 0.0
        for intent, bucket in sorted(per_intent.items())
    }
    return {
        "total": total,
        "correct": correct,
        "accuracy": accuracy,
        "per_intent": per_intent_accuracy,
        "per_intent_counts": per_intent,
        "misclassified": misclassified,
    }


def print_report(results: dict[str, Any], *, verbose: bool = True) -> None:
    summary = (
        f"样本数: {results['total']}  判对: {results['correct']}"
        f"  准确率: {results['accuracy']:.3f}"
    )
    print(summary)
    print("分意图准确率:")
    for intent, accuracy in results["per_intent"].items():
        counts = results["per_intent_counts"][intent]
        print(f"  {intent:<16} {counts['correct']}/{counts['total']}  {accuracy:.3f}")
    if results["misclassified"]:
        print("误分类明细:")
        for item in results["misclassified"]:
            print(f"  [{item['expected']} → {item['predicted']}] {item['text']}")
        if not verbose:
            print("(以上明细仅在直接运行时展示)")


def compare_with_baseline(
    results: dict[str, Any],
    baseline_path: Path,
    tolerance: float = REGRESSION_TOLERANCE,
) -> bool:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    failed = False
    baseline_accuracy = float(baseline.get("accuracy", 0.0))
    if results["accuracy"] < baseline_accuracy - tolerance:
        print(
            f"回归: 总体准确率 {results['accuracy']:.3f} 低于基线 "
            f"{baseline_accuracy:.3f}(容差 {tolerance})"
        )
        failed = True
    baseline_per_intent = baseline.get("per_intent", {})
    for intent, accuracy in results["per_intent"].items():
        if intent not in baseline_per_intent:
            continue
        expected = float(baseline_per_intent[intent])
        if accuracy < expected - tolerance:
            print(
                f"回归: {intent} 准确率 {accuracy:.3f} 低于基线 {expected:.3f}"
                f"(容差 {tolerance})"
            )
            failed = True
    return not failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="意图识别规则分类器离线评测")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="评测集 JSON 路径(默认 evals/datasets/intent_classification.json)",
    )
    parser.add_argument("--save", type=Path, help="把当前分数保存为基线文件")
    parser.add_argument("--baseline", type=Path, help="与指定基线对比,退化则退出码 1")
    parser.add_argument("--min-accuracy", type=float, default=ACCURACY_THRESHOLD)
    args = parser.parse_args(argv)

    results = run_eval(args.dataset)
    print_report(results)

    exit_code = 0
    if results["accuracy"] < args.min_accuracy:
        print(f"未达标: 总体准确率低于门槛 {args.min_accuracy:.2f}")
        exit_code = 1
    if args.save is not None:
        payload = {
            "name": "intent-rules",
            "description": "规则意图分类器基线(run_intent_eval 生成)",
            "detector": "rule",
            "accuracy": results["accuracy"],
            "per_intent": results["per_intent"],
        }
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"基线已保存: {args.save}")
    if args.baseline is not None and not compare_with_baseline(results, args.baseline):
        exit_code = 1
    if exit_code == 0:
        print("评测通过。")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
