import requests
import csv
import time

APP_ID = "6754265953"
SORT = "mostRecent"

COUNTRIES = [
    "us", "gb", "ca", "au", "in", "de", "fr", "it", "es", "nl",
    "br", "mx", "jp", "kr", "sg", "ae", "za", "se", "no", "dk"
]

all_reviews = []
seen_ids = set()

for country in COUNTRIES:
    print(f"Fetching {country}...")

    for page in range(1, 11):
        url = (
            f"https://itunes.apple.com/{country}/rss/customerreviews/"
            f"page={page}/id={APP_ID}/sortBy={SORT}/json"
        )

        try:
            r = requests.get(url, timeout=20)
            if r.status_code != 200:
                break

            data = r.json()
            entries = data.get("feed", {}).get("entry", [])

            page_count = 0

            for entry in entries:
                if "im:rating" not in entry:
                    continue

                review_id = entry.get("id", {}).get("label")
                dedupe_key = f"{country}:{review_id}"

                if dedupe_key in seen_ids:
                    continue

                seen_ids.add(dedupe_key)

                all_reviews.append({
                    "country": country,
                    "review_id": review_id,
                    "author": entry.get("author", {}).get("name", {}).get("label"),
                    "rating": entry.get("im:rating", {}).get("label"),
                    "version": entry.get("im:version", {}).get("label"),
                    "title": entry.get("title", {}).get("label"),
                    "content": entry.get("content", {}).get("label"),
                    "updated": entry.get("updated", {}).get("label"),
                    "vote_sum": entry.get("im:voteSum", {}).get("label"),
                    "vote_count": entry.get("im:voteCount", {}).get("label"),
                })

                page_count += 1

            if page_count == 0:
                break

            time.sleep(0.5)

        except Exception as e:
            print(f"Error for {country} page {page}: {e}")
            break

with open("once_appstore_reviews_all_checked_countries.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "country",
            "review_id",
            "author",
            "rating",
            "version",
            "title",
            "content",
            "updated",
            "vote_sum",
            "vote_count",
        ],
    )
    writer.writeheader()
    writer.writerows(all_reviews)

print(f"Saved {len(all_reviews)} reviews")

