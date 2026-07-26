from bs4 import BeautifulSoup
import requests
import re

url = "https://www.tcgplayer.com/categories/trading-and-collectible-card-games/pokemon/me05-pitch-black"
result = requests.get(url)
doc = BeautifulSoup(result.text, "html.parser")

listing_prices = doc.find_all("div", class_="listing-price")
market_prices = doc.find_all("div", class_="market-price")


listing_price_texts = [p.text for p in listing_prices]
market_price_texts = [o.text for o in market_prices]

print(f' {listing_price_texts} \n ------------------------- {market_price_texts}')

