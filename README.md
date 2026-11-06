# OpsWatch

**A historical log-alert classifier with a reproducible ML evaluation and an interactive investigation dashboard.**

**[Explore the live dashboard](https://opswatch-harshiv.virat2718.chatgpt.site)** — view the historical evaluation and sample log windows online.

OpsWatch examines recorded system logs, groups them into one-minute windows and classifies windows against existing alert labels. Its dashboard lets a reviewer compare a trained model with a simple severity rule and explore sampled test-period windows. This is an offline research demonstration; it does not predict future outages or connect to a live production system.

## What the evaluation found

The committed run processes all **4,747,963** log records from the [Loghub BGL dataset](https://zenodo.org/records/8196385). Windows are split chronologically: 60% for training, 20% for threshold selection, and the final 20% for evaluation. Preprocessing is fit on training data only. The held-out test contains **5,534 occupied windows**, of which **385** have an alert label.

| Held-out test | Precision | Recall | F1 | False positives | Missed alert windows |
| --- | ---: | ---: | ---: | ---: | ---: |
| Trained logistic regression | 72.7% | 92.7% | 81.5% | 134 | 28 |
| Severity rule | 56.5% | 100% | 72.2% | 296 | 0 |

The model generated fewer false alarms on this test period, but missed 28 alert windows caught by the severity rule. This trade-off is important: the severity rule may be preferable when missing an alert is more costly. Results do not establish performance on another system or on future incidents.

## Run the dashboard

The saved evaluation and trusted model are included. Python 3.12 is sufficient to **view** the dashboard:

```bash
python server.py
```

Open <http://127.0.0.1:8000>. The app uses the local saved report and 500 evenly sampled test windows; it makes no live monitoring claim. For a different port, run `python server.py --port 8080`. Stop the server with Ctrl+C. The server is intended for local research use, not public production deployment.

## Reproduce or extend the model

For training, use Python 3.12 and install the pinned ML dependencies:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r ml/requirements.txt
.venv/bin/python scripts/download_bgl.py
.venv/bin/python -m ml.pipeline train --input data/raw/BGL.zip --output artifacts --scope "Complete official BGL archive; 60-second occupied windows"
```

The downloader checks the published archive checksum. Downloading the dataset requires an internet connection; raw data is excluded from Git. See [the ML guide](ml/README.md) for the exact recorded run, experiment design, metrics, input format for scoring new BGL-formatted files, and known limitations. Dataset use is subject to its own research/academic terms: see [data notice](data/NOTICE.md). Only load model files from trusted sources; joblib uses pickle serialization.

## Verify

```bash
python -m unittest discover -s tests
npm test --prefix web
```

The Python tests need the ML dependencies; frontend tests use Node 24 or later and require no packages. GitHub Actions runs both suites. A dashboard walkthrough and questions to practice are in the [learning guide](docs/LEARNING_GUIDE.md).

## Project structure

- `ml/` — parsing, feature engineering, training, evaluation and scoring.
- `artifacts/` — fitted model, recorded metrics and a sample of held-out windows.
- `web/` and `server.py` — dependency-free local dashboard and API.
- `tests/` — pipeline and server tests; frontend tests are in `web/`.
- `data/NOTICE.md` — dataset attribution and usage terms.

The labels reflect BGL alert tags. Scores are uncalibrated, message previews are not explanations or verified root causes, and similar message patterns can occur across time splits. The data describes one historical system; it is not evidence of performance across organizations or environments.
