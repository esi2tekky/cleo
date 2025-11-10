from exa_py import Exa
import csv
from bs4 import BeautifulSoup

# Initialize client
exa = Exa(api_key="f8cfe700-7bad-465f-b5cf-39c7ff23f55c")

# Crawl knitwear page and product subpages
result = exa.get_contents(
    ["https://www.cos.com/en-us/women/knitwear"],
    text=True,
    subpages=20,  # Crawl deeper
    subpage_target=["/product/"],  # Only follow actual product links
    extras={"links": 1, "image_links": 1},
    livecrawl="always"
)

# Parse and save to CSV
data = []
for page in result.results:
    html_text = page.text or ""
    soup = BeautifulSoup(html_text, "html.parser")

    title = page.title or ""
    text = soup.get_text(separator="\n", strip=True)

    image_links = []
    if page.extras and "imageLinks" in page.extras:
        image_links = page.extras["imageLinks"]
    main_image = image_links[0] if image_links else None

    data.append({
        "title": title,
        "url": page.url,
        "image": main_image,
        "description": text[:400]
    })


# Save to CSV
csv_path = "data/processed/cos_test_products.csv"
with open(csv_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["title", "url", "image", "description"])
    writer.writeheader()
    writer.writerows(data)

print(f"✅ Saved {len(data)} items to {csv_path}")
