---
name: scientific
description: |
  [WHAT] Scientific-methodology skills for the SciTeX ecosystem — publication-quality figures, statistics, experiment reproducibility. Distinct from `general/` (which covers package engineering) and per-package skills (which cover package-specific APIs). Load when authoring analysis scripts, preparing figures for manuscripts, or checking scientific rigour of ecosystem output.
  [WHEN] Authoring analysis scripts, preparing figures or PDF reports for manuscripts, or auditing scientific outputs of any ecosystem package.
  [HOW] Read SKILL.md as the index, then drill into the numbered sub-skill leaves (`01_figures_*`, `02_research-project_*`, `03_reporting_*`) for the relevant topic.
tags: [scitex-scientific]
user-invocable: false
primary_interface: mixed
interfaces:
  python: 0-3
  cli: 0-3
  mcp: 0-3
  skills: 3
  http: 0
---

# SciTeX Scientific Standards

`pip install scitex` — scientific-methodology conventions shared across every ecosystem package that produces research artefacts.

These complement (never duplicate) the engineering rules in [../general/SKILL.md](../general/SKILL.md). General covers *how a package is built*; scientific covers *how the research outputs should look*.

Full per-leaf descriptions: [07_sub-skill-catalog.md](07_sub-skill-catalog.md).

## Sub-skills

One-line descriptions per leaf are in [07_sub-skill-catalog.md](07_sub-skill-catalog.md).

### 0. Planning
- [00_planning_01_hypotheses-agreement.md](00_planning_01_hypotheses-agreement.md)
- [00_planning_02_paper-structure.md](00_planning_02_paper-structure.md)

### 1. Figures
- [01_figures_01_standards.md](01_figures_01_standards.md) — comparison, layout, colour maps, robust limits
- [01_figures_04_typography-encoding-and-report-layout.md](01_figures_04_typography-encoding-and-report-layout.md) — typography, legends, thresholds, chartjunk, anti-patterns
- [01_figures_02_provenance-and-verification.md](01_figures_02_provenance-and-verification.md)
- [01_figures_03_no-synthetic-data-policy.md](01_figures_03_no-synthetic-data-policy.md)

### 2. Research project — how a research project *consumes* SciTeX
- [02_research-project_01_project-structure-root.md](02_research-project_01_project-structure-root.md)
- [02_research-project_02_project-structure-scripts.md](02_research-project_02_project-structure-scripts.md)
- [02_research-project_03_project-structure-config-and-data.md](02_research-project_03_project-structure-config-and-data.md)
- [02_research-project_11_config-fstring-paths.md](02_research-project_11_config-fstring-paths.md) — `CONFIG.PATH` f-strings via `eval`; phantom-unused-variable footgun
- [02_research-project_04_project-structure-makefile.md](02_research-project_04_project-structure-makefile.md)
- [02_research-project_05_project-structure-examples.md](02_research-project_05_project-structure-examples.md)
- [02_research-project_06_project-structure-tests.md](02_research-project_06_project-structure-tests.md)
- [02_research-project_07_config-and-parameters.md](02_research-project_07_config-and-parameters.md)
- [02_research-project_08_cohort-datasets.md](02_research-project_08_cohort-datasets.md)
- [02_research-project_12_cohort-dataset-readme.md](02_research-project_12_cohort-dataset-readme.md) — cohort dataset README contract
- [02_research-project_09_id-readability-and-data-immutability.md](02_research-project_09_id-readability-and-data-immutability.md)
- [02_research-project_10_naming-and-numbering.md](02_research-project_10_naming-and-numbering.md)

### 3. Reporting
- [03_reporting_01_pdf-reports.md](03_reporting_01_pdf-reports.md) — PDF report structure, bookmarks, figures, size
- [03_reporting_03_pdf-report-delivery.md](03_reporting_03_pdf-report-delivery.md) — email delivery + issue-comment tracking
- [03_reporting_02_statistics-completeness.md](03_reporting_02_statistics-completeness.md)

### 4. Clew adoption — translating any project into a Clew-verifiable form
- [04_clew_01_dag-as-map-and-evidence.md](04_clew_01_dag-as-map-and-evidence.md) — read first
- [04_clew_02_translation-playbook.md](04_clew_02_translation-playbook.md)
- [04_clew_03_translation-template.md](04_clew_03_translation-template.md)
- [04_clew_04_translation-notebook-delta.md](04_clew_04_translation-notebook-delta.md)
- [04_clew_05_notebook-execution-and-scoring.md](04_clew_05_notebook-execution-and-scoring.md) — execution, extraction, validity, scoring

### 5. Private skills for consumer projects (research repos, paper repos, internal apps)
- [05_private-skills_01_consumer-project.md](05_private-skills_01_consumer-project.md)

### 6. Scitexification — translating existing code into SciTeX form
- [06_scitexification/SKILL.md](06_scitexification/SKILL.md) — package-agnostic translation act; load before picking a chapter
  - [06_scitexification/00_playbook.md](06_scitexification/00_playbook.md)

### Lessons learned
- [99_lessons-learned.md](99_lessons-learned.md) — real mistakes and the rules that fix them
- [99_lessons-learned_02_project-organization.md](99_lessons-learned_02_project-organization.md) — project-organization lessons table
