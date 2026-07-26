# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
import json
from dataclasses import dataclass
from genlayer import *


@allow_storage
@dataclass
class Feed:
    feed_id: str
    description: str
    sources: str
    schema: str
    last_value: str
    last_updated: str
    update_count: u256
    max_staleness: u256
    deviation_threshold: u256


class CrosschainOracle(gl.Contract):
    feeds: TreeMap[str, str]
    subscribers: TreeMap[Address, TreeMap[str, bool]]
    feed_count: u256
    feed_history: TreeMap[str, str]
    source_health: TreeMap[str, str]

    def __init__(self):
        pass

    def _aggregate_from_sources(self, sources_json: str, schema_json: str) -> dict:
        def fetch_and_aggregate() -> str:
            sources = json.loads(sources_json)
            schema = json.loads(schema_json)
            raw_results = []

            for source in sources:
                try:
                    content = gl.get_webpage(source["url"], mode="text")
                    raw_results.append({
                        "source": source["name"], "url": source["url"],
                        "raw": content[:2000], "extract_path": source.get("extract_path", "")
                    })
                except Exception:
                    raw_results.append({
                        "source": source["name"], "url": source["url"],
                        "raw": "[FETCH_FAILED]", "extract_path": ""
                    })

            task = f"""
You are a decentralized oracle aggregator.

SCHEMA:
{json.dumps(schema)}

SOURCES:
{json.dumps(raw_results, indent=2)}

Respond ONLY in this JSON format:
{{
    "values": dict,
    "confidence": int,
    "sources_used": int,
    "warnings": [str],
    "median_source_count": int,
    "deviation_detected": bool
}}
"""
            result = gl.exec_prompt(task).replace("```json", "").replace("```", "")
            return json.dumps(json.loads(result), sort_keys=True)

        result_json = json.loads(gl.eq_principle_strict_eq(fetch_and_aggregate))
        return result_json

    @gl.public.write
    def create_feed(self, description: str, sources_json: str, schema_json: str, max_staleness: u256, deviation_threshold: u256):
        self.feed_count += 1
        feed_id = str(self.feed_count)
        feed = Feed(
            feed_id=feed_id, description=description,
            sources=sources_json, schema=schema_json,
            last_value="{}", last_updated="0", update_count=0,
            max_staleness=max_staleness, deviation_threshold=deviation_threshold,
        )
        self.feeds[feed_id] = json.dumps(feed.__dict__)
        self.feed_history[feed_id] = "[]"

    @gl.public.write
    def update_feed(self, feed_id: str):
        feed_data = json.loads(self.feeds.get(feed_id, "{}"))
        if not feed_data:
            raise Exception("Feed not found")

        result = self._aggregate_from_sources(feed_data["sources"], feed_data["schema"])
        feed_data["last_value"] = json.dumps(result)
        feed_data["last_updated"] = str(gl.message.timestamp)
        feed_data["update_count"] += 1
        self.feeds[feed_id] = json.dumps(feed_data)

        history = json.loads(self.feed_history.get(feed_id, "[]"))
        entry = {
            "timestamp": str(gl.message.timestamp),
            "value": result["values"],
            "confidence": result["confidence"],
            "deviation": result.get("deviation_detected", False),
        }
        history.append(entry)
        if len(history) > 20:
            history = history[-20:]
        self.feed_history[feed_id] = json.dumps(history)

    @gl.public.write
    def check_staleness(self, feed_id: str) -> dict:
        feed_data = json.loads(self.feeds.get(feed_id, "{}"))
        if not feed_data:
            raise Exception("Feed not found")

        current_time = self._now()
        last_update = int(feed_data["last_updated"])
        is_stale = (current_time - last_update) > feed_data["max_staleness"]

        return {"feed_id": feed_id, "is_stale": is_stale, "seconds_since_update": current_time - last_update, "max_staleness": feed_data["max_staleness"]}

    @gl.public.view
    def _now(self) -> u256:
        return self.feed_count + 1000000

    @gl.public.write
    def subscribe(self, feed_id: str):
        sender = gl.message.sender_address
        if sender not in self.subscribers:
            self.subscribers[sender] = {}
        self.subscribers[sender][feed_id] = True

    @gl.public.write
    def unsubscribe(self, feed_id: str):
        sender = gl.message.sender_address
        if sender in self.subscribers:
            self.subscribers[sender][feed_id] = False

    @gl.public.view
    def get_feed(self, feed_id: str) -> str:
        return self.feeds.get(feed_id, "{}")

    @gl.public.view
    def get_latest_value(self, feed_id: str) -> str:
        feed_data = json.loads(self.feeds.get(feed_id, "{}"))
        if not feed_data:
            return "{}"
        return json.dumps({
            "feed_id": feed_id,
            "value": json.loads(feed_data["last_value"]),
            "updated": feed_data["last_updated"],
            "update_count": feed_data["update_count"],
            "is_stale": False,
        })

    @gl.public.view
    def get_feed_history(self, feed_id: str, limit: u256) -> str:
        history = json.loads(self.feed_history.get(feed_id, "[]"))
        if limit > 0 and limit < len(history):
            return json.dumps(history[-limit:])
        return json.dumps(history)

    @gl.public.view
    def get_feed_count(self) -> int:
        return self.feed_count

    @gl.public.view
    def get_subscribers(self, feed_id: str, user: str) -> bool:
        addr = Address(user)
        return self.subscribers.get(addr, {}).get(feed_id, False)

    @gl.public.view
    def list_feeds(self) -> dict:
        result = {}
        for k, v in self.feeds.items():
            data = json.loads(v)
            result[k] = {
                "description": data["description"],
                "update_count": data["update_count"],
                "last_updated": data["last_updated"],
                "max_staleness": data["max_staleness"],
            }
        return result
