# Selective Carbon-Aware Scheduling in CI/CD

Research artifact for the BSc study *An Empirical Decision Model for Selective Carbon-Aware Scheduling
in CI/CD Pipelines Using Commit-Level Software Engineering Characteristics* (K. P. S. Nimsara,
Coventry University / NIBM).

The study asks which commit-triggered CI builds should be delayed to cleaner hours of the electricity
grid, and whether commit-level software-engineering characteristics help beyond an estimate of build
duration. On TravisTorrent data replayed against the Great Britain grid, they did not: the
evidence-derived policy delays a build only if it may wait and is expected to take at least 480 s, to
the cleanest hour within 24 hours.

| I want to… | Go to |
| :-- | :-- |
| Try the advisor, make commits that show RUN NOW and DEFER RECOMMENDED, or generate a What-If report | [`Research_Artifact/USER_GUIDE.md`](Research_Artifact/USER_GUIDE.md) |
| Add the GitHub Action to my repository | [`Research_Artifact/code/github-action/`](Research_Artifact/code/github-action/) |
| See it running in a real repository | [`senith02/carbon-advisor-demo`](https://github.com/senith02/carbon-advisor-demo) |
| Read the results behind the thesis | [`Research_Artifact/results/`](Research_Artifact/results/) |
| Understand the project structure and reproduce the research | [`Research_Artifact/README.md`](Research_Artifact/README.md) |

The TravisTorrent dataset is not included in this repository because of its size.
