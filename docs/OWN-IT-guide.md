# Own-it step: re-implement the seasonal-naive baseline and its WAPE yourself

Goal: you write this piece without AI help, run it, and can explain every line out loud. Nothing here is solved for you.
Time: about 90 minutes. Do it in a new file, `own_it/my_baseline.py`, not in `analysis/`.

## What you build
For ONE store (pick any store from `outputs/selected_stores.csv`), forecast each day of **2015-02-02 to 2015-02-08**
as "the sales of the same weekday, one week earlier, among the days you could have known on 2015-02-01", then score it
with WAPE and bias against the real sales of those 7 days.

## Steps (you decide how to code each one)
1. Load `data/raw/train.csv` for your store only. Look at the first rows. What type is `StateHoliday`? Why does that matter?
2. Decide what "closed" means. Check `Open`, `Sales` and `StateHoliday`. How many days in your store's history are closed?
   What does the SQL in `sql/01_clean.sql` do about them (rules R1 to R6)? Do you agree with each rule?
3. Cut the data at 2015-01-31 (the last day known when the forecast is made). Write down in one sentence why a forecast
   for 2015-02-08 must NOT use the sales of 2015-02-01.
4. For each target day, find the most recent same weekday that is on or before the cutoff and was open. Take its sales.
   Careful: for 2015-02-08 the "one week earlier" day is 2015-02-01, which is after the cutoff. Which day do you use instead?
5. Score only days the store was open: WAPE = sum of absolute errors / sum of actual sales, bias = sum of (forecast minus
   actual) / sum of actual. Compute both by hand on a calculator for two days first, then in code.
6. Compare with `outputs/forecast_naive.csv` is not possible for this week (it covers other dates). Instead run
   `analysis/forecasters.py::baseline_forecasts` on the same cutoff for your store and compare the `snaive1` row with yours.
   If they differ, find out who is right. A difference is the most useful thing that can happen in this exercise.

## You are done when you can answer, without notes
* Why WAPE and not the average of per-day percentage errors? (Think of a day with sales 0.)
* What does a positive bias mean and what would you change in an ordering policy because of it?
* Why is the baseline fair to beat, and why would "yesterday's sales" be a weak baseline for a store closed on Sundays?
* Which assumption makes the promo and holiday columns usable for a forecast, and is it realistic?
* Where in the repository is the leakage test for this baseline, and what does it do?

## Then claim only what is true
After you did this, the honest sentence is: "re-implemented the seasonal-naive baseline and its WAPE on one Rossmann store
and checked it against the pipeline". Everything else in the repository was built with AI assistance (Claude) under
your direction; say so.
