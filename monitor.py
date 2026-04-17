import feedparser
import requests
import json
import os
import re
import time

FEEDS = {
    "OpenAI":        "https://openai.com/blog/rss.xml",
    "Anthropic":     "https://techcrunch.com/tag/anthropic/feed/",
    "Google DeepMind": "https://techcrunch.com/tag/google-deepmind/feed/",
    "Google AI":     "https://blog.google/technology/ai/rss/",
    "Mistral AI":    "https://techcrunch.com/tag/mistral/feed/",
    "xAI":           "https://techcrunch.com/tag/xai/feed/",
    "HuggingFace":   "https://huggingface.co/blog/feed.xml",
}

FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")
STATE_FILE = "seen_ids.json"
MAX_SEEN = 2000
MAX_PER_RUN = 8  # 每次最多推送条数


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


def truncate(text, n=150):
    return text[:n] + "..." if len(text) > n else text


def translate(text):
    """使用 Google 翻译免费接口翻译成中文"""
    if not text:
        return ""
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": "zh-CN",
            "dt": "t",
            "q": text[:500],
        }
        resp = requests.get(url, params=params, timeout=10)
        result = resp.json()
        translated = "".join(part[0] for part in result[0] if part[0])
        return translated
    except Exception as e:
        print(f"  翻译失败: {e}")
        return text


def send_feishu_batch(items):
    """将多条新闻合并成一条飞书卡片推送"""
    if not items:
        return

    elements = []
    for i, (source, title, link, summary) in enumerate(items):
        # 翻译标题和摘要
        title_cn = translate(title)
        summary_cn = truncate(translate(strip_html(summary))) if summary else ""

        content = f"**[{source}]** {title_cn}"
        if summary_cn:
            content += f"\n{summary_cn}"

        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": content,
            },
        })
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看原文 →"},
                "url": link,
                "type": "default",
            }],
        })
        # 分隔线（最后一条不加）
        if i < len(items) - 1:
            elements.append({"tag": "hr"})

    count = len(items)
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"🤖 AI 最新动态 · {count} 条新消息",
                },
                "template": "blue",
            },
            "elements": elements,
        },
    }

    resp = requests.post(FEISHU_WEBHOOK, json=card, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    if result.get("code") != 0:
        print(f"  [飞书错误] {result}")


def main():
    if not FEISHU_WEBHOOK:
        print("FEISHU_WEBHOOK 未设置，退出。")
        return

    seen = load_seen()
    new_seen = set(seen)
    new_items = []  # (source, title, link, summary)

    for source, feed_url in FEEDS.items():
        try:
            print(f"检查 {source} ...")
            feed = feedparser.parse(feed_url, request_headers={
                "User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"
            })

            if not feed.entries:
                print(f"  无内容 (bozo={feed.bozo})")
                continue

            for entry in feed.entries[:10]:
                uid = entry.get("id") or entry.get("link", "")
                if not uid or uid in seen:
                    continue

                title = entry.get("title", "(无标题)")
                link = entry.get("link", feed_url)
                summary = entry.get("summary") or entry.get("description", "")

                print(f"  新内容: {title}")
                new_items.append((source, title, link, summary))
                new_seen.add(uid)

                if len(new_items) >= MAX_PER_RUN:
                    break

        except Exception as e:
            print(f"检查 {source} 出错: {e}")

        if len(new_items) >= MAX_PER_RUN:
            break

    if new_items:
        print(f"\n共 {len(new_items)} 条新内容，翻译并推送中...")
        try:
            send_feishu_batch(new_items)
            print("推送成功！")
        except Exception as e:
            print(f"推送失败: {e}")
    else:
        print("无新内容。")

    save_seen(new_seen)


if __name__ == "__main__":
    main()
