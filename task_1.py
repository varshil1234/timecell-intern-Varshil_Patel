from __future__ import annotations
from math import inf
from typing import Any, List, Mapping, Dict

# ==========================================
# 1. DATA NORMALIZATION HELPERS
# ==========================================

def _extract_assets(portfolio: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Extracts assets prioritizing the exact keys from the Timecell specification."""
    assets_raw = portfolio.get("assets", [])
    if not isinstance(assets_raw, list):
        raise TypeError("portfolio['assets'] must be a list.")
        
    assets: List[Dict[str, Any]] = []
    for idx, item in enumerate(assets_raw):
        if not isinstance(item, Mapping):
            raise TypeError(f"Asset at index {idx} must be a mapping.")
        
        assets.append({
            "name": str(item.get("name", f"asset_{idx}")),
            "allocation": float(item.get("allocation_pct", item.get("allocation", 0.0))),
            "crash_magnitude": float(item.get("expected_crash_pct", item.get("crash_magnitude", 0.0))),
        })
    return assets


def _normalize_allocations(assets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalizes asset allocations to fractions that sum exactly to 1.0."""
    allocations = [a["allocation"] for a in assets]
    total_alloc = sum(allocations)

    if total_alloc == 0:
        return [{"name": a["name"], "allocation": 0.0, "crash_magnitude": a["crash_magnitude"]} for a in assets]

    is_percentage = max(abs(x) for x in allocations) > 1.0 + 1e-9
    
    for a in assets:
        if is_percentage:
            a["allocation"] = a["allocation"] / 100.0
            
    total_after = sum(a["allocation"] for a in assets)
    if total_after != 0.0:
        for a in assets:
            a["allocation"] = a["allocation"] / total_after

    return assets


def _normalize_crash_magnitudes(assets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalizes crash magnitudes to decimals (0..1) if provided as percentages."""
    magnitudes = [a["crash_magnitude"] for a in assets]
    if not magnitudes:
        return assets

    if max(abs(m) for m in magnitudes) > 1.0 + 1e-9:
        for a in assets:
            a["crash_magnitude"] = a["crash_magnitude"] / 100.0
    return assets


# ==========================================
# 2. CORE QUANTITATIVE ENGINE
# ==========================================

def compute_risk_metrics(portfolio: Mapping[str, Any], scenario: str = "severe") -> Dict[str, Any]:
    """
    Computes key risk metrics for a given portfolio.
    Evaluates survival runway, identifies maximum risk contributors, and calculates post-crash portfolio drift.
    """
    starting_value = float(portfolio.get("total_value_inr", 0.0))
    monthly_expenses = float(portfolio.get("monthly_expenses_inr", 0.0))
    assets = _normalize_crash_magnitudes(_normalize_allocations(_extract_assets(portfolio)))

    largest_risk_score = float("-inf")
    largest_risk_asset: str | None = None
    post_crash_factor = 0.0
    concentration_warning = False
    
    # Scale shock severity based on scenario
    crash_multiplier = 0.5 if scenario == "moderate" else 1.0
    surviving_assets = []

    for a in assets:
        name = a["name"]
        allocation = a["allocation"]
        adjusted_crash = a["crash_magnitude"] * crash_multiplier

        if allocation > 0.40:
            concentration_warning = True

        # Pure geometric drag calculation
        risk_score = allocation * abs(adjusted_crash)
        if risk_score > largest_risk_score:
            largest_risk_score = risk_score
            largest_risk_asset = name

        # Asset survival rate
        survival_rate = 1.0 - abs(adjusted_crash)
        post_crash_factor += allocation * survival_rate
        
        surviving_assets.append({
            "name": name,
            "post_crash_value": starting_value * allocation * survival_rate
        })

    post_crash_value = starting_value * post_crash_factor

    # Compute Portfolio Drift (New Asset Weights Post-Crash)
# Compute Portfolio Drift (New Asset Weights Post-Crash)
    post_crash_allocation = []
    if post_crash_value > 0:
        for sa in surviving_assets:
            post_crash_allocation.append({
                "name": sa["name"],
                # Add round() here to fix the floating point precision error
                "allocation": round(sa["post_crash_value"] / post_crash_value, 4)
            })

    # Runway & Ruin Logic
    if monthly_expenses == 0.0:
        runway_months = inf if post_crash_value > 0 else 0.0
    else:
        runway_months = post_crash_value / monthly_expenses

    ruin_test = "PASS" if runway_months > 12 else "FAIL"

    # Required Recovery (Asymmetry of Returns)
    drawdown_pct = (starting_value - post_crash_value) / starting_value if starting_value > 0 else 0.0
    if drawdown_pct < 1.0:
        required_recovery_pct = drawdown_pct / (1.0 - drawdown_pct)
    else:
        required_recovery_pct = inf

    return {
        "scenario": scenario,
        "post_crash_value": round(post_crash_value, 2),
        "runway_months": round(runway_months, 2) if runway_months != inf else inf,
        "ruin_test": ruin_test,
        "largest_risk_asset": largest_risk_asset,
        "concentration_warning": concentration_warning,
        "required_recovery_pct": round(required_recovery_pct * 100, 2) if required_recovery_pct != inf else inf,
        "post_crash_allocation": post_crash_allocation
    }


# ==========================================
# 3. CLI VISUALIZATION
# ==========================================

def print_dynamic_bar_chart(assets_list: List[Dict[str, Any]], title: str = "Allocation", width: int = 30) -> None:
    """Renders a CLI bar chart from a list of normalized asset dictionaries."""
    print(f"\n--- {title} ---")
    for a in assets_list:
        name = a["name"]
        allocation = a.get("allocation", 0.0)
        bar_len = int(round(allocation * width))
        bar_len = max(1, bar_len) if allocation > 0 else 0
        bar = "█" * bar_len
        print(f"{name.ljust(12)} | {bar} ({allocation * 100:5.1f}%)")
    print("-" * 45)


# ==========================================
# 4. EXECUTION & TESTING SUITE
# ==========================================

def run_visual_demo():
    """Runs the visual CLI demonstration for the Loom walkthrough."""
    print("\n" + "="*60)
    print("🚀 TIMECELL RISK ENGINE - VISUAL DEMONSTRATION")
    print("="*60)

    sample_portfolio = {
        "total_value_inr": 10_000_000,
        "monthly_expenses_inr": 80_000,
        "assets": [
            {"name": "NIFTY50", "allocation_pct": 40, "expected_crash_pct": -40},
            {"name": "GOLD", "allocation_pct": 30, "expected_crash_pct": -10},
            {"name": "BTC", "allocation_pct": 20, "expected_crash_pct": -80},
            {"name": "CASH", "allocation_pct": 10, "expected_crash_pct": -5}
        ]
    }

    initial_assets = _normalize_allocations(_extract_assets(sample_portfolio))
    print_dynamic_bar_chart(initial_assets, title="INITIAL PORTFOLIO ALLOCATION")

    for sc in ["severe", "moderate"]:
        results = compute_risk_metrics(sample_portfolio, scenario=sc)
        print(f"\n[{sc.upper()} CRASH METRICS]")
        for k, v in results.items():
            if k not in ['scenario', 'post_crash_allocation']: 
                print(f"  - {k}: {v}")
        print_dynamic_bar_chart(results["post_crash_allocation"], title=f"POST-CRASH PORTFOLIO DRIFT ({sc.upper()})")


def run_formal_tests():
    """Runs the formal 10-case unit test suite to prove correctness and prints charts."""
    print("\n" + "="*60)
    print("⚙️ EXECUTING FORMAL UNIT TESTS & DRIFT VISUALIZATIONS")
    print("="*60)

    test_cases = [
        {
            "desc": "Standard Diversified (Severe)", 
            "scenario": "severe",
            "portfolio": {"total_value_inr": 10000000, "monthly_expenses_inr": 80000, "assets": [{"name": "A", "allocation_pct": 40, "expected_crash_pct": -40}, {"name": "B", "allocation_pct": 30, "expected_crash_pct": -80}, {"name": "C", "allocation_pct": 30, "expected_crash_pct": 0}]},
            "expected": {
                "scenario": "severe", "post_crash_value": 6000000.0, "runway_months": 75.0, 
                "ruin_test": "PASS", "largest_risk_asset": "B", "concentration_warning": False, 
                "required_recovery_pct": 66.67,
                "post_crash_allocation": [{"name": "A", "allocation": 0.4}, {"name": "B", "allocation": 0.1}, {"name": "C", "allocation": 0.5}]
            }
        },
        {
            "desc": "Standard Diversified (Moderate)", 
            "scenario": "moderate",
            "portfolio": {"total_value_inr": 10000000, "monthly_expenses_inr": 80000, "assets": [{"name": "A", "allocation_pct": 40, "expected_crash_pct": -40}, {"name": "B", "allocation_pct": 30, "expected_crash_pct": -80}, {"name": "C", "allocation_pct": 30, "expected_crash_pct": 0}]},
            "expected": {
                "scenario": "moderate", "post_crash_value": 8000000.0, "runway_months": 100.0, 
                "ruin_test": "PASS", "largest_risk_asset": "B", "concentration_warning": False, 
                "required_recovery_pct": 25.0,
                "post_crash_allocation": [{"name": "A", "allocation": 0.4}, {"name": "B", "allocation": 0.225}, {"name": "C", "allocation": 0.375}]
            }
        },
        {
            "desc": "Zero Expenses (Infinite Runway)", 
            "scenario": "severe",
            "portfolio": {"total_value_inr": 5000000, "monthly_expenses_inr": 0, "assets": [{"name": "GOLD", "allocation_pct": 100, "expected_crash_pct": -20}]},
            "expected": {
                "scenario": "severe", "post_crash_value": 4000000.0, "runway_months": float('inf'), 
                "ruin_test": "PASS", "largest_risk_asset": "GOLD", "concentration_warning": True, 
                "required_recovery_pct": 25.0,
                "post_crash_allocation": [{"name": "GOLD", "allocation": 1.0}]
            }
        },
        {
            "desc": "100% Wipeout (Infinite Recovery)", 
            "scenario": "severe",
            "portfolio": {"total_value_inr": 2000000, "monthly_expenses_inr": 50000, "assets": [{"name": "RISK", "allocation_pct": 100, "expected_crash_pct": -100}]},
            "expected": {
                "scenario": "severe", "post_crash_value": 0.0, "runway_months": 0.0, 
                "ruin_test": "FAIL", "largest_risk_asset": "RISK", "concentration_warning": True, 
                "required_recovery_pct": float('inf'),
                "post_crash_allocation": [] 
            }
        },
        {
            "desc": "Concentration Exactly 40%", 
            "scenario": "severe",
            "portfolio": {"total_value_inr": 1000000, "monthly_expenses_inr": 10000, "assets": [{"name": "A", "allocation_pct": 40, "expected_crash_pct": 0}, {"name": "B", "allocation_pct": 30, "expected_crash_pct": 0}, {"name": "C", "allocation_pct": 30, "expected_crash_pct": 0}]},
            "expected": {
                "scenario": "severe", "post_crash_value": 1000000.0, "runway_months": 100.0, 
                "ruin_test": "PASS", "largest_risk_asset": "A", "concentration_warning": False, 
                "required_recovery_pct": 0.0,
                "post_crash_allocation": [{"name": "A", "allocation": 0.4}, {"name": "B", "allocation": 0.3}, {"name": "C", "allocation": 0.3}]
            }
        },
        {
            "desc": "Concentration Exceeds 40%", 
            "scenario": "severe",
            "portfolio": {"total_value_inr": 1000000, "monthly_expenses_inr": 10000, "assets": [{"name": "A", "allocation_pct": 41, "expected_crash_pct": 0}, {"name": "B", "allocation_pct": 59, "expected_crash_pct": 0}]},
            "expected": {
                "scenario": "severe", "post_crash_value": 1000000.0, "runway_months": 100.0, 
                "ruin_test": "PASS", "largest_risk_asset": "A", "concentration_warning": True, 
                "required_recovery_pct": 0.0,
                "post_crash_allocation": [{"name": "A", "allocation": 0.41}, {"name": "B", "allocation": 0.59}]
            }
        },
        {
            "desc": "Positive Crash Input Handling", 
            "scenario": "severe",
            "portfolio": {"total_value_inr": 1000000, "monthly_expenses_inr": 50000, "assets": [{"name": "A", "allocation_pct": 100, "expected_crash_pct": 50}]},
            "expected": {
                "scenario": "severe", "post_crash_value": 500000.0, "runway_months": 10.0, 
                "ruin_test": "FAIL", "largest_risk_asset": "A", "concentration_warning": True, 
                "required_recovery_pct": 100.0,
                "post_crash_allocation": [{"name": "A", "allocation": 1.0}]
            }
        },
        {
            "desc": "High Burn Rate (Immediate Ruin)", 
            "scenario": "severe",
            "portfolio": {"total_value_inr": 1000000, "monthly_expenses_inr": 2000000, "assets": [{"name": "CASH", "allocation_pct": 100, "expected_crash_pct": 0}]},
            "expected": {
                "scenario": "severe", "post_crash_value": 1000000.0, "runway_months": 0.5, 
                "ruin_test": "FAIL", "largest_risk_asset": "CASH", "concentration_warning": True, 
                "required_recovery_pct": 0.0,
                "post_crash_allocation": [{"name": "CASH", "allocation": 1.0}]
            }
        },
        {
            "desc": "Zero Crash (Safe Assets)", 
            "scenario": "severe",
            "portfolio": {"total_value_inr": 10000000, "monthly_expenses_inr": 100000, "assets": [{"name": "C1", "allocation_pct": 50, "expected_crash_pct": 0}, {"name": "C2", "allocation_pct": 50, "expected_crash_pct": 0}]},
            "expected": {
                "scenario": "severe", "post_crash_value": 10000000.0, "runway_months": 100.0, 
                "ruin_test": "PASS", "largest_risk_asset": "C1", "concentration_warning": True, 
                "required_recovery_pct": 0.0,
                "post_crash_allocation": [{"name": "C1", "allocation": 0.5}, {"name": "C2", "allocation": 0.5}]
            }
        },
        {
            "desc": "Zero Initial Value Edge Case", 
            "scenario": "severe",
            "portfolio": {"total_value_inr": 0, "monthly_expenses_inr": 10000, "assets": [{"name": "A", "allocation_pct": 100, "expected_crash_pct": -50}]},
            "expected": {
                "scenario": "severe", "post_crash_value": 0.0, "runway_months": 0.0, 
                "ruin_test": "FAIL", "largest_risk_asset": "A", "concentration_warning": True, 
                "required_recovery_pct": 0.0,
                "post_crash_allocation": []
            }
        }
    ]

    passed = 0
    for idx, test in enumerate(test_cases, 1):
        actual = compute_risk_metrics(test["portfolio"], scenario=test["scenario"])
        test_passed = True
        
        for key, expected_val in test["expected"].items():
            if actual.get(key) != expected_val:
                print(f"[✗] Test {idx} Failed ({test['desc']}): Key '{key}' -> Expected {expected_val}, Got {actual.get(key)}")
                test_passed = False
                
        if test_passed: 
            passed += 1
            print(f"[✓] Test {idx} Passed: {test['desc']}")
            
            if actual.get("post_crash_allocation"):
                print_dynamic_bar_chart(actual["post_crash_allocation"], title=f"TEST {idx} POST-CRASH DRIFT")
            else:
                print("   [!] Chart skipped: Portfolio completely wiped out.\n")

    if passed == len(test_cases):
        print(f"\n[✓] ALL {passed} TESTS PASSED. READY FOR PRODUCTION.")
    else:
        print(f"\n[!] {len(test_cases) - passed} TESTS FAILED. CHECK LOGS.")
    print("="*60 + "\n")

if __name__ == "__main__":
    run_visual_demo()
    run_formal_tests()