# Data: Rossmann Store Sales (not included)

This repository contains **no Rossmann data**: no `train.csv`, no `store.csv`, no sample of them and no
database built from them. The competition rules of the data owner (Dirk Rossmann GmbH, hosted by Kaggle)
forbid redistributing the data, so you must download it yourself.

## Source

- Kaggle competition: <https://www.kaggle.com/competitions/rossmann-store-sales>
- Terms: the Data tab says "Subject to Competition Rules". Downloading requires a Kaggle login and
  accepting those rules. Read them yourself before you download; this README is not legal advice.

## Steps

1. Log in to Kaggle, open the competition page, and accept the rules (Rules tab, "I Understand and Accept").
2. Download `train.csv` and `store.csv` from the Data tab (or `kaggle competitions download -c rossmann-store-sales`
   if you have the Kaggle CLI configured).
3. Put the two files in `data/raw/` (this folder is gitignored):

   ```
   data/raw/train.csv
   data/raw/store.csv
   ```

4. Fingerprint the files you downloaded and compare with the table below (no official published hashes exist; the
   values below were recorded from one download and only show that your copy matches it):

   ```powershell
   Get-FileHash data\raw\train.csv, data\raw\store.csv -Algorithm SHA256
   ```

| File | Expected shape (to confirm on your copy) | SHA-256 |
|---|---|---|
| `train.csv` | 1,017,209 rows, 9 columns, 2013-01-01 to 2015-07-31 | `f6e4597c142d7d909a13d53b68a8e85c00b9a4c7b5ff40adbb37d6829cc1f4cc` |
| `store.csv` | 1,115 rows, 10 columns | `f56bd124a2849489e6bbb5c000f5fc9640204355e316475c918ae4d089afb344` |

Hashes recorded on 2026-10-24 from the files in the Kaggle "Download all" zip (`rossmann-store-sales.zip`, 7.3 MB),
downloaded by the project owner's signed-in account after accepting the rules. They fingerprint that download; they are
not an official Kaggle checksum.

The pipeline checks the columns and duplicate keys on load (`analysis/load.py`) and prints the row count and
date range, so a wrong or truncated file fails loudly. It does not claim the file is authentic; compare the hash
with a second source if that matters to you.

## Run without the data

```
python make_demo_data.py          # writes synthetic files with the same columns to data/demo/
python run_pipeline.py --demo     # whole pipeline on synthetic data, output in outputs/demo/
```

Synthetic results test the code only. They say nothing about Rossmann.

## What is committed instead

Parameters, summary tables, forecast-error statistics, aggregate KPIs and figures. Per-store-per-day tables
(`store_day_demand.csv`, the three forecast files, `forecast_error_distribution.csv`) are gitignored.
