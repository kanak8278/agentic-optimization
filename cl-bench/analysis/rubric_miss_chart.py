"""Chart: Rubric miss distribution for failed tasks in Exp 1 (full 1899)."""

import json
from collections import defaultdict, Counter
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
import numpy as np

# Load results
results = []
with open("outputs/exp1_full.jsonl") as f:
    for line in f:
        results.append(json.loads(line))

# Count rubric misses for failed tasks
category_misses = defaultdict(lambda: Counter())
combined_misses = Counter()

for r in results:
    total = r.get("rubrics_total", 0)
    passed = r.get("rubrics_passed", 0)
    if total == 0:
        continue

    missed = total - passed
    if missed == 0:
        continue  # task passed, skip

    category = r.get("metadata", {}).get("context_category", "Unknown")
    # Shorten category names
    cat_short = category.replace(" Reasoning", "").replace(" Tasks", "")
    category_misses[cat_short][missed] += 1
    combined_misses[missed] += 1

max_miss = max(combined_misses.keys())
x = list(range(1, max_miss + 1))

categories = sorted(category_misses.keys())
colors = {
    "Domain Knowledge": "#4C72B0",
    "Empirical Discovery": "#DD8452",
    "Procedural Task": "#55A868",
    "Rule System": "#C44E52",
}

# --- Chart ---
fig, axes = plt.subplots(1, 2, figsize=(16, 6), gridspec_kw={'width_ratios': [1, 1.3]})

# Left: Combined bar chart
ax = axes[0]
vals = [combined_misses.get(i, 0) for i in x]
bars = ax.bar(x, vals, color="#4C72B0", edgecolor="white", linewidth=0.5)

for bar, val in zip(bars, vals):
    if val > 0:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5,
                str(val), ha='center', va='bottom', fontsize=8, fontweight='bold')

ax.set_xlabel("Number of Rubrics Missed", fontsize=11)
ax.set_ylabel("Number of Failed Tasks", fontsize=11)
total_failed = sum(combined_misses.values())
total_tasks = len(results)
ax.set_title(f"How Close Were Failed Tasks?\n(Combined, N={total_failed} failed / {total_tasks} total)",
             fontsize=12, fontweight='bold')
ax.set_xticks(x)
ax.set_xlim(0.3, max_miss + 0.7)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

# Annotate the "missed by 1" bar
pct_1 = combined_misses[1] / total_failed * 100
ax.annotate(f"{pct_1:.1f}% of failures\nmissed by just 1 rubric",
            xy=(1, combined_misses[1]), xytext=(3.5, combined_misses[1] * 0.95),
            arrowprops=dict(arrowstyle='->', color='#333'),
            fontsize=9, color='#333', fontstyle='italic')

# Right: By category (grouped bar chart)
ax = axes[1]
bar_width = 0.2
cap = min(max_miss, 10)
x_pos = np.arange(1, cap + 1)

for i, cat in enumerate(categories):
    vals = [category_misses[cat].get(m, 0) for m in x_pos]
    offset = (i - len(categories)/2 + 0.5) * bar_width
    ax.bar(x_pos + offset, vals, bar_width,
           label=cat, color=colors.get(cat, f"C{i}"),
           edgecolor="white", linewidth=0.5)

ax.set_xlabel("Number of Rubrics Missed", fontsize=11)
ax.set_ylabel("Number of Failed Tasks", fontsize=11)
ax.set_title("Rubric Miss Distribution by Category", fontsize=12, fontweight='bold')
ax.set_xticks(x_pos)
ax.legend(fontsize=9, framealpha=0.9)
ax.set_xlim(0.3, cap + 0.7)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

plt.tight_layout()
plt.savefig("analysis/rubric_miss_distribution.png", dpi=150, bbox_inches='tight')
print(f"Saved: analysis/rubric_miss_distribution.png")

# Print summary stats
print(f"\nTotal failed: {total_failed}")
print(f"Missed by 1: {combined_misses[1]} ({combined_misses[1]/total_failed*100:.1f}%)")
cum2 = combined_misses[1] + combined_misses[2]
print(f"Missed by ≤2: {cum2} ({cum2/total_failed*100:.1f}%)")
cum3 = cum2 + combined_misses[3]
print(f"Missed by ≤3: {cum3} ({cum3/total_failed*100:.1f}%)")

print("\nBy category:")
for cat in categories:
    total_cat = sum(category_misses[cat].values())
    by_1 = category_misses[cat][1]
    print(f"  {cat}: {total_cat} failed, {by_1} by 1 rubric ({by_1/total_cat*100:.1f}%)")
