import pandas as pd 

df = pd.read_csv("ME05PitchBlackProductsAndPrices.csv")

print(df.columns.tolist())

print(df[["name", 'subTypeName', "marketPrice", "lowPrice"]].head(20))

df.sort_values("marketPrice", ascending=False)
df.to_csv("output.csv", index=False)

