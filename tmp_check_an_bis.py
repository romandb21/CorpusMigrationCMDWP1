import pandas as pd
from pathlib import Path

p = Path("DIMIG (collab with Hélène)/AN_debats/data/corpus_debats_2015_2025.csv")
cols = [0, 1, 3, 5, 6]
col_names = ["id", "attachmentUrl", "dateParution", "typeAssemblee", "origine"]
df = pd.read_csv(p, usecols=cols, names=col_names, header=0, low_memory=False)
sub = df[df["typeAssemblee"].isin(["AN", "AN_BIS"])].copy()
sub["num"] = sub["attachmentUrl"].astype(str).str.extract(r"AN_\d{4}-(\d+)", expand=False)
sub = sub[sub["num"].notna()]

g = sub.groupby(["dateParution", "num"])["typeAssemblee"].agg(lambda s: set(s)).reset_index(name="types")
g["has_both"] = g["types"].apply(lambda s: {"AN", "AN_BIS"}.issubset(s))

out = {
    "rows_total": int(len(df)),
    "rows_an_or_bis": int(len(sub)),
    "groups_date_num": int(len(g)),
    "groups_with_AN_and_AN_BIS": int(g["has_both"].sum()),
    "groups_only_AN": int((g["types"].apply(lambda s: s == {"AN"})).sum()),
    "groups_only_AN_BIS": int((g["types"].apply(lambda s: s == {"AN_BIS"})).sum()),
}
print(out)
print("coverage_pct=", round(out["groups_with_AN_and_AN_BIS"] / out["groups_date_num"] * 100, 2) if out["groups_date_num"] else None)

sample_142 = sub[sub["attachmentUrl"].astype(str).str.contains(r"AN_2025-142", na=False)][["id", "attachmentUrl", "dateParution", "typeAssemblee", "origine"]]
print("sample_142_rows=", len(sample_142))
print(sample_142.head(20).to_string(index=False))
