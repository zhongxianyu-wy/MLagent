---
name: ngs-xgboost-baseline
description: Strict fixture Skill for NGS feature matrix reproduction.
version: 1.0.0
required_features:
  - f1
  - f2
preprocessing: standardize
feature_subset: all_features
model: xgboost
threshold_policy: youden
---

# NGS XGBoost Baseline

Use the declared preprocessing, feature subset, model, and threshold policy without exploratory changes.
