# Learn OpsWatch before discussing it

This guide is a starting point for understanding and extending the project. Describe your actual contribution accurately, including any assistance used; do not claim work you have not done.

## Follow one log entry

1. `ml/pipeline.py` reads each record. The first field is the dataset's existing alert tag (`-` is not an alert); the model never receives that field as an input feature.
2. Records are grouped into occupied 60-second windows. Each window is labeled positive if at least one record in it has an alert tag.
3. Window features describe volume, severity counts, message length and a small set of failure-related words. The model learns patterns of the labels in those historical records.
4. The windows are sorted by time. Earlier windows train the model, the middle portion selects a decision threshold, and the final portion is used for evaluation.
5. The dashboard reads the saved results and a sample of held-out windows; it is not a live connection to a supercomputer.

## Questions to practice

- Why might a model look good on a random train/test split but perform less well on future data?
- What is the difference between a historical alert label and an actual incident, root cause, or future failure?
- Why is an error-severity rule a useful baseline? In which situations might it be preferable to a model?
- What do precision, recall, false positives and false negatives mean to an operations team?
- Why must the scaler be fit only on the training data, and why choose the threshold without using the final test period?
- Which aspects of the dataset and features might cause performance to change on another system?
- What does `class_weight="balanced"` do? Why shouldn't the resulting score automatically be called a calibrated probability?
- How would you improve the model after examining its false positives and false negatives?

Read `artifacts/report.json`, the method in `ml/pipeline.py`, and the project README before attempting numerical answers. Try changing the threshold or adding a feature in a separate experiment; keep the held-out test separate from decisions during tuning.
