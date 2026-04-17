import asyncio
import os
from flask import Flask, render_template, request, jsonify
from TikTokApi import TikTokApi

app = Flask(__name__)

MS_TOKEN = os.environ.get("MS_TOKEN", "")


def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def fetch_hashtag_videos(hashtag: str, count: int):
    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=[MS_TOKEN] if MS_TOKEN else [None],
            num_sessions=1,
            sleep_after=3,
            headless=True,
        )
        videos = []
        async for video in api.hashtag(name=hashtag).videos(count=count):
            d = video.as_dict
            author = d.get("author", {})
            stats = d.get("stats", {})
            video_info = d.get("video", {})
            videos.append(
                {
                    "id": video.id,
                    "desc": d.get("desc", ""),
                    "author_name": author.get("nickname", ""),
                    "author_id": author.get("uniqueId", ""),
                    "cover": video_info.get("cover", ""),
                    "duration": video_info.get("duration", 0),
                    "plays": stats.get("playCount", 0),
                    "likes": stats.get("diggCount", 0),
                    "comments": stats.get("commentCount", 0),
                    "shares": stats.get("shareCount", 0),
                    "url": f"https://www.tiktok.com/@{author.get('uniqueId', '')}/video/{video.id}",
                }
            )
        return videos


async def fetch_search_videos(query: str, count: int):
    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=[MS_TOKEN] if MS_TOKEN else [None],
            num_sessions=1,
            sleep_after=3,
            headless=True,
        )
        videos = []
        async for video in api.search.search_type(query, search_type=1, count=count):
            d = video.as_dict
            author = d.get("author", {})
            stats = d.get("stats", {})
            video_info = d.get("video", {})
            videos.append(
                {
                    "id": video.id,
                    "desc": d.get("desc", ""),
                    "author_name": author.get("nickname", ""),
                    "author_id": author.get("uniqueId", ""),
                    "cover": video_info.get("cover", ""),
                    "duration": video_info.get("duration", 0),
                    "plays": stats.get("playCount", 0),
                    "likes": stats.get("diggCount", 0),
                    "comments": stats.get("commentCount", 0),
                    "shares": stats.get("shareCount", 0),
                    "url": f"https://www.tiktok.com/@{author.get('uniqueId', '')}/video/{video.id}",
                }
            )
        return videos


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/hashtag")
def hashtag_videos():
    tag = request.args.get("tag", "TikTokMadeMeBuyIt").lstrip("#")
    count = min(int(request.args.get("count", 20)), 50)
    try:
        videos = run_async(fetch_hashtag_videos(tag, count))
        return jsonify({"ok": True, "hashtag": tag, "videos": videos})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/search")
def search_videos():
    query = request.args.get("q", "TikTok made me buy it")
    count = min(int(request.args.get("count", 20)), 50)
    try:
        videos = run_async(fetch_search_videos(query, count))
        return jsonify({"ok": True, "query": query, "videos": videos})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
