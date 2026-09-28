"""Refresh the live sections of the profile README.

Runs daily from .github/workflows/profile.yml. It rewrites only the text
between these marker pairs and leaves everything else in README.md alone:

    <!-- MERGED:START --> ... <!-- MERGED:END -->   latest merged upstream PRs
    <!-- REVIEW:START --> ... <!-- REVIEW:END -->   open upstream PRs in review
    <!-- POSTS:START -->  ... <!-- POSTS:END -->    latest dev.to posts

If a source cannot be reached, that section keeps its previous content.
Standard library only, so the workflow needs no install step.
"""

import datetime
import json
import os
import re
import sys
import urllib.parse
import urllib.request

GITHUB_USER = "onkar717"
DEVTO_USER = "onkar_s"
README = "README.md"
MERGED_COUNT = 6
REVIEW_COUNT = 5
POSTS_COUNT = 4

# Leading emoji, emoji shortcodes or symbols that some projects put in PR
# titles ("🐛 fix: ...", ":seedling: bump ...").
LEADING_SHORTCODES = re.compile(r"^(?::[a-z0-9_+\-]+:\s*)+")
LEADING_SYMBOLS = re.compile(r"^[^\w\[(`\"':]+", re.UNICODE)
MARKDOWN_SPECIAL = re.compile(r"([\\`*_\[\]<>|])")


def fetch_json(url, headers=None):
    request = urllib.request.Request(
        url, headers={"User-Agent": f"{GITHUB_USER}-profile-refresh", **(headers or {})}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def search_issues(query, per_page):
    params = urllib.parse.urlencode(
        {"q": query, "sort": "updated", "order": "desc", "per_page": per_page}
    )
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return fetch_json(f"https://api.github.com/search/issues?{params}", headers)["items"]


def clean_title(title):
    original = title.strip()
    title = LEADING_SYMBOLS.sub("", LEADING_SHORTCODES.sub("", original)) or original
    return MARKDOWN_SPECIAL.sub(r"\\\1", title)


def short_date(iso_timestamp):
    moment = datetime.datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    return f"{moment.day} {moment.strftime('%b %Y')}"


def repo_name(item):
    return item["repository_url"].split("/repos/", 1)[1]


def pr_line(item, when):
    repo = repo_name(item)
    return (
        f"- [{clean_title(item['title'])}]({item['html_url']}) · "
        f"[{repo}](https://github.com/{repo}) · {when}"
    )


def merged_section():
    items = search_issues(f"author:{GITHUB_USER} is:pr is:merged -user:{GITHUB_USER}", 40)
    items.sort(key=lambda item: item.get("closed_at") or "", reverse=True)
    return "\n".join(
        pr_line(item, f"merged {short_date(item['closed_at'])}") for item in items[:MERGED_COUNT]
    )


def review_section():
    items = search_issues(
        f"author:{GITHUB_USER} is:pr is:open archived:false -user:{GITHUB_USER}", 20
    )
    items = [item for item in items if not item.get("draft")]
    return "\n".join(
        pr_line(item, f"opened {short_date(item['created_at'])}") for item in items[:REVIEW_COUNT]
    )


def posts_section():
    articles = fetch_json(f"https://dev.to/api/articles?username={DEVTO_USER}&per_page=10")
    return "\n".join(
        f"- [{clean_title(article['title'])}]({article['url']}) · "
        f"{short_date(article['published_timestamp'])}"
        for article in articles[:POSTS_COUNT]
    )


def replace_block(text, name, body):
    pattern = re.compile(rf"(<!-- {name}:START -->\n)(.*?)(\n<!-- {name}:END -->)", re.S)
    return pattern.sub(lambda match: match.group(1) + body + match.group(3), text, count=1)


def main():
    with open(README, encoding="utf-8") as handle:
        original = handle.read()

    updated = original
    for name, build in (
        ("MERGED", merged_section),
        ("REVIEW", review_section),
        ("POSTS", posts_section),
    ):
        try:
            body = build()
        except Exception as error:  # keep the old content if a source is down
            print(f"::warning::{name} section not refreshed: {error}")
            continue
        if body:
            updated = replace_block(updated, name, body)

    if updated == original:
        print("README already up to date")
        return 0

    with open(README, "w", encoding="utf-8") as handle:
        handle.write(updated)
    print("README refreshed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
