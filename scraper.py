import requests
from bs4 import BeautifulSoup
import json

url = "https://example.com"

headers = {
    "User-Agent": "Mozilla/5.0"
}

response = requests.get(url, headers=headers)

soup = BeautifulSoup(response.text, "html.parser")

properties = []

cards = soup.select(".property-card")

for card in cards:
    title = card.select_one(".title").text.strip()
    price = card.select_one(".price").text.strip()

    properties.append({
        "title": title,
        "price": price
    })

with open("properties.json", "w") as f:
    json.dump(properties, f, indent=2)

print("Done scraping.")
