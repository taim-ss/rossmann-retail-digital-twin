"""Bar chart of mean on-hand stock and total cost by forecast source, from results/analysis/summary_by_source.csv."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

root = Path(__file__).resolve().parents[1]
s = pd.read_csv(root / "results/analysis/summary_by_source.csv")
order = ["oracle", "ml", "naive"]
fig, axes = plt.subplots(1, 2, figsize=(9, 3.6))
for ax, metric, title in ((axes[0], "mean_on_hand", "Mean on-hand stock (units = EUR 1 of turnover)"),
                          (axes[1], "total_cost", "Total cost, 159 scored days, EUR (ASSUMPTION-driven)")):
    d = s[s.metric == metric].set_index("source").loc[order]
    ax.bar(order, d["mean"], yerr=d["ci95_half_width"], color=["#7a8b99", "#2f6f9f", "#c98a3a"], capsize=4)
    ax.set_title(title, fontsize=9)
    for i, v in enumerate(d["mean"]):
        ax.text(i, v, f"{v:,.0f}", ha="center", va="bottom", fontsize=8)
fig.suptitle("P2, store 164, order-up-to policy, 10 seeds: all three sources reach 100% fill (agent-built, educational)", fontsize=9)
fig.text(0.5, 0.01, "Error bars: 95% CI over lead-time seeds only. Inventory parameters are ASSUMPTIONS. Rossmann-derived; model run in AnyLogic PLE.",
         ha="center", fontsize=7)
fig.tight_layout(rect=(0, 0.04, 1, 0.94))
fig.savefig(root / "results/analysis/cost_by_source.png", dpi=150)
