### Cross-instance robustness: best F1-AUC per instance, mean and worst case (min)

| method | mutation_openpilot | mutation_transfuser | real_tfpp | real_pylot | mean | min |
|---|---|---|---|---|---|---|
| STRAP one-verdict | 0.322 | 0.403 | 0.456 | 0.414 | 0.398 | 0.322 |
| Uniform round-robin | 0.330 | 0.419 | 0.551 | 0.497 | 0.449 | 0.330 |
| k-rerun-majority | 0.301 | 0.382 | 0.416 | 0.373 | 0.368 | 0.301 |
| PFS Beta (flat) | 0.347 | 0.422 | 0.488 | 0.417 | 0.418 | 0.347 |
| EB-PFS (warm prior) | 0.311 | 0.360 | 0.374 | 0.375 | 0.355 | 0.311 |
| SPRT (Wald) | 0.380 | 0.627 | 0.856 | 0.687 | 0.637 | 0.380 |
| Thresholding bandit (APT) | 0.378 | 0.682 | 0.823 | 0.644 | 0.632 | 0.378 |
| SA-TRP base | 0.398 | 0.733 | 0.891 | 0.717 | 0.685 | 0.398 |
| SA-TRP warm | 0.397 | 0.746 | 0.892 | 0.718 | 0.688 | 0.397 |
