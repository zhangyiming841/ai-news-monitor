import feedparser
import requests
import json
import os
import re
import time

FEEDS = {
    "OpenAI":         "https://openai.com/blog/rss.xml",
    "Anthropic":      "https://www.anthropic.com/rss.xml",
    "Google DeepMind":"https://deepmind.google/discover/blog/rss/",
    "Google AI Blog": "https://blog.google/technology/ai/rss/",
    "Meta AI":        "https://ai.meta.com/blog/feed/",
    "Mistral AI":     "https://mistral.ai/feed/",
    "xAI":            "https://x.ai/news/rss.xml",
}

FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")
STATE_FILE = "seen_ids.json"
MAX_SEEN = 2000


def load_seen():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    items = list(seen)[-MAX_SEEN:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)


def strip_html(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def truncate(text, n=220):
    return text[:n] + "..." if len(text) > n else text


def send_feishu(source, title, link, summary):
    summary_clean = truncate(strip_html(summary))

    content_md = f"**{title}**"
    if summary_clean:
        content_md += f"\n\n{summary_clean}"

    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"🚀 {source} 最新动态"},
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": content_md},
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "查看原文 →"},
                            "url": link,
                            "type": "primary",
                        }
                    ],
                },
            ],
        },
    }

    resp = requests.post(FEISHU_WEBHOOK, json=card, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    if result.get("code") != 0:
        print(f"  [Feishu Error] {result}")


def main():
    if not FEISHU_WEBHOOK:
        print("FEISHU_WEBHOOK not set, exiting.")
        return

    seen = load_seen()
    new_seen = set(seen)
    new_count = 0

    for source, feed_url in FEEDS.items():
        try:
            print(f"Checking {source} ...")
            feed = feedparser.parse(feed_url)

            if not feed.entries:
                print(f"  No entries (bozo={feed.bozo})")
                continue

            for entry in feed.entries[:10]:
                uid = entry.get("id") or entry.get("link", "")
                if not uid or uid in seen:
                    continue

                title = entry.get("title", "(no title)")
                link = entry.get("link", feed_url)
                summary = entry.get("summary") or entry.get("description", "")

                print(f"  NEW: {title}")
                try:
                    send_feishu(source, title, link, summary)
                    new_count += 1
                    time.sleep(1)
                except Exception as e:
                    print(f"  Send failed: {e}")

                new_seen.add(uid)

        except Exception as e:
            print(f"Error on {source}: {e}")

    save_seen(new_seen)
    print(f"\nDone. {new_count} new item(s) pushed.")


if __name__ == "__main__":
    main()
