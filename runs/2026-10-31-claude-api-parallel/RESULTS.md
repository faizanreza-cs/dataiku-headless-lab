# Results: 2026-10-31-claude-api-parallel

Scored 2026-10-31 against `reference/`: **13 of 13 checks passed.**

| Check | Rule | Result | Detail |
|---|---|---|---|
| All three tables, with the right columns | - | pass | found |
| No national-total rows | 1 | pass | none |
| Same state-quarter-brand rows | 2, 4 | pass | 3,302 rows as expected |
| One row per state, quarter and brand | 3 | pass | yes |
| Same brands | 4, 5 | pass | 13 brands |
| Generic names match | - | pass | all 3,302 matching rows agree |
| Prescriptions match | 1-5 | pass | all 3,302 matching rows agree |
| Units match | 1-5 | pass | all 3,302 matching rows agree |
| Spend matches | 6 | pass | all 3,302 matching rows agree |
| Class share matches | 5 | pass | all 3,302 matching rows agree |
| Growth matches, including empty values | 7 | pass | all 3,302 matching rows agree |
| National table matches | 1 | pass | all 96 rows agree |
| Unmatched NDCs reported | 8 | pass | all 101 reported, with the same counts |

Rules are numbered as in the README's table of business rules.
