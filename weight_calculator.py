from __future__ import annotations

import math


# Model parameters. Change these values when tuning the game model.
STANDARD_WEIGHT = 48.0
METABOLIC_CONSTANT = 5.0
POWER = 4.0

# Nonlinear surplus-to-weight conversion:
# delta = SATURATION_LIMIT * sign(d) * (1 - exp(-abs(d) / SATURATION_SCALE))
# These values give approximately 3 kg at d=10 and 6 kg at d=30.
SATURATION_LIMIT = 7.8541
SATURATION_SCALE = 20.7809


def metabolic_threshold(current_weight: float) -> float:
    """Return the daily intake threshold at the current weight."""
    return METABOLIC_CONSTANT * (current_weight / STANDARD_WEIGHT) ** POWER


def nonlinear_weight_change(surplus: float) -> float:
    """Convert intake surplus/deficit into the next day's weight change."""
    if surplus == 0:
        return 0.0
    return math.copysign(
        SATURATION_LIMIT * (1.0 - math.exp(-abs(surplus) / SATURATION_SCALE)),
        surplus,
    )


def calculate(current_weight: float, intake: float) -> dict[str, float]:
    threshold = metabolic_threshold(current_weight)
    surplus = intake - threshold
    weight_change = nonlinear_weight_change(surplus)
    next_weight = current_weight + weight_change
    return {
        "ratio": current_weight / STANDARD_WEIGHT,
        "threshold": threshold,
        "surplus": surplus,
        "weight_change": weight_change,
        "next_weight": next_weight,
    }


def read_number(prompt: str) -> float | None:
    while True:
        raw = input(prompt).strip()
        if raw.lower() in {"q", "quit", "exit"}:
            return None
        try:
            value = float(raw)
        except ValueError:
            print("请输入数字，或输入 q 退出。")
            continue
        if not math.isfinite(value):
            print("请输入有限数字。")
            continue
        return value


def print_result(current_weight: float, intake: float, result: dict[str, float]) -> None:
    print("\n公式计算：")
    print(
        f"1. 基础代谢阈值 a = M × (Wi / W0)^p"
        f" = {METABOLIC_CONSTANT:.4f} × ({current_weight:.4f} / "
        f"{STANDARD_WEIGHT:.4f})^{POWER:.4f}"
    )
    print(f"   a = {result['threshold']:.4f}")
    print(f"2. 摄入盈余 d = i - a = {intake:.4f} - {result['threshold']:.4f}")
    print(f"   d = {result['surplus']:.4f}")
    print(
        "3. 非线性体重变化 "
        "ΔW = L × sign(d) × (1 - exp(-|d| / T))"
    )
    print(
        f"   ΔW = {SATURATION_LIMIT:.4f} × sign({result['surplus']:.4f}) × "
        f"(1 - exp(-|{result['surplus']:.4f}| / {SATURATION_SCALE:.4f}))"
    )
    print(f"   ΔW = {result['weight_change']:+.4f} kg")

    print("\n最终结果：")
    print(f"当前体重：{current_weight:.4f} kg")
    print(f"本次摄入：{intake:.4f} kg")
    print(f"体重变化：{result['weight_change']:+.4f} kg")
    print(f"下一次结算使用的当前体重：{result['next_weight']:.4f} kg")


def main() -> None:
    print("Bot 体重结算计算器")
    print("输入 q、quit 或 exit 退出。")
    print(
        f"当前参数：W0={STANDARD_WEIGHT:g}kg，"
        f"M={METABOLIC_CONSTANT:g}，p={POWER:g}，"
        f"边际曲线 L={SATURATION_LIMIT:g}，T={SATURATION_SCALE:g}\n"
    )

    current_weight = read_number("请输入初始当前体重 Wi（kg）：")
    if current_weight is None:
        return
    while current_weight <= 0:
        print("当前体重必须大于 0。")
        current_weight = read_number("请重新输入初始当前体重 Wi（kg）：")
        if current_weight is None:
            return

    round_number = 1
    while True:
        print(f"\n第 {round_number} 次结算，当前体重自动使用：{current_weight:.4f} kg")
        intake = read_number("请输入本次摄入 i（kg 等效值）：")
        if intake is None:
            break
        if intake < 0:
            print("摄入量不能小于 0。\n")
            continue

        result = calculate(current_weight, intake)
        print_result(current_weight, intake, result)
        current_weight = result["next_weight"]
        round_number += 1
        print()


if __name__ == "__main__":
    main()
