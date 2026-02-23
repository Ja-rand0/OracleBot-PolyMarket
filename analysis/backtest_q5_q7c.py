"""Backtest analyst Q5+Q7c: fitness formula verification + signal direction analysis. Read-only."""
import sqlite3, json, sys
sys.path.insert(0, 'D:/Developer/Personal/Bots/PolyMarketTracker')
from config import TOTAL_METHODS, FITNESS_W_ACCURACY, FITNESS_W_EDGE, FITNESS_W_FALSE_POS, FITNESS_W_COMPLEXITY

print("=== Q5: Fitness formula verification ===")
print(f"TOTAL_METHODS = {TOTAL_METHODS}")
print(f"FITNESS_W_ACCURACY = {FITNESS_W_ACCURACY}")
print(f"FITNESS_W_EDGE = {FITNESS_W_EDGE}")
print(f"FITNESS_W_FALSE_POS = {FITNESS_W_FALSE_POS}")
print(f"FITNESS_W_COMPLEXITY = {FITNESS_W_COMPLEXITY}")

# Verify top combo: S4+T17, fitness=0.3546, acc=1.0, edge=0.0335, fpr=0.0, complexity=2
acc, edge, fpr, complexity = 1.0, 0.0335, 0.0, 2
fitness_manual = (
    acc * FITNESS_W_ACCURACY
    + edge * FITNESS_W_EDGE
    - fpr * FITNESS_W_FALSE_POS
    - (complexity / TOTAL_METHODS) * FITNESS_W_COMPLEXITY
)
print(f"\nManual calc for S4+T17 (acc=1.0, edge=0.0335, fpr=0.0, complexity=2):")
print(f"  {acc}*{FITNESS_W_ACCURACY} + {edge}*{FITNESS_W_EDGE} - {fpr}*{FITNESS_W_FALSE_POS} - ({complexity}/{TOTAL_METHODS})*{FITNESS_W_COMPLEXITY}")
print(f"  = {acc*FITNESS_W_ACCURACY:.5f} + {edge*FITNESS_W_EDGE:.5f} - 0 - {(complexity/TOTAL_METHODS)*FITNESS_W_COMPLEXITY:.5f}")
print(f"  = {fitness_manual:.4f}  (reported: 0.3546)")

# T17+P24 case: edge=0.0317, complexity=2
acc2, edge2, fpr2, comp2 = 1.0, 0.0317, 0.0, 2
f2 = acc2*FITNESS_W_ACCURACY + edge2*FITNESS_W_EDGE - fpr2*FITNESS_W_FALSE_POS - (comp2/TOTAL_METHODS)*FITNESS_W_COMPLEXITY
print(f"\nManual calc for T17+P24 (acc=1.0, edge=0.0317, fpr=0.0, complexity=2):")
print(f"  = {f2:.4f}  (reported: 0.3540)")

# What edge would be needed for the combo to be "meaningful"?
# edge > 0.05 is typical threshold in prediction market research
print("\n=== Q5: Fitness sensitivity to edge ===")
for e in [0.0, 0.01, 0.03, 0.05, 0.10, 0.20]:
    f = 1.0*FITNESS_W_ACCURACY + e*FITNESS_W_EDGE - 0.0*FITNESS_W_FALSE_POS - (2/TOTAL_METHODS)*FITNESS_W_COMPLEXITY
    print(f"  edge={e:.2f}  fitness={f:.4f}")

print("\n=== Q5: Complexity penalty at different sizes ===")
for c in [1, 2, 3, 4, 5, 6]:
    penalty = (c/TOTAL_METHODS)*FITNESS_W_COMPLEXITY
    print(f"  complexity={c}  penalty={penalty:.5f}")

# What does accuracy=1.0 look like with different N?
print("\n=== Q7c: Probability of 100% accuracy by chance (binomial) ===")
# P(all correct) = p^N where p = max(baseline_yes, baseline_no) = 0.545 (always-NO)
import math
p_naive = 0.545  # always predicting NO
for N in [10, 15, 20, 25, 30, 33, 40, 50]:
    prob = p_naive ** N
    print(f"  N={N:3d}: P(all-NO correct) = {prob:.2e}  ({100*prob:.4f}%)")

# More realistic: random predictor at 50%
print("\nWith random 50/50 predictor:")
for N in [10, 15, 20, 25, 30, 33]:
    prob = 0.5 ** N
    print(f"  N={N:3d}: P(all correct by chance) = {prob:.2e}")
