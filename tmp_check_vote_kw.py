import pandas as pd
from pathlib import Path
import re

p = Path("DIMIG (collab with Hélène)/AN_debats/data/corpus_debats_2015_2025.csv")
usecols = ["attachmentUrl", "typeAssemblee", "content"]
df = pd.read_csv(p, usecols=usecols, low_memory=False)

bis = df[df["typeAssemblee"] == "AN_BIS"].copy()
pattern = r"scrutin|résultat du vote|résultats du vote|nombre de votants|pour l'adoption|contre"
bis["has_vote_kw"] = bis["content"].astype(str).str.contains(pattern, case=False, regex=True, na=False)

print("an_bis_rows=", len(bis))
print("an_bis_with_vote_keywords=", int(bis["has_vote_kw"].sum()))
print("an_bis_vote_kw_pct=", round(bis["has_vote_kw"].mean()*100, 2))

# Show small snippets for 142 and 142_Bis
ex = df[df["attachmentUrl"].astype(str).str.contains(r"AN_2025-142(_Bis)?\\.pdf", regex=True, na=False)][["attachmentUrl", "typeAssemblee", "content"]]
print("\nExample 142 vs 142_Bis:")
for _, r in ex.iterrows():
    txt = str(r["content"]).replace("\n", " ")
    print(f"- {r['attachmentUrl']} [{r['typeAssemblee']}]: {txt[:260]}")
