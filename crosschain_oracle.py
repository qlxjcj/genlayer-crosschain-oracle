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


class CrosschainOracle(gl.Contract):
    feeds: TreeMap[str, str]
    subscribers: TreeMap[Address, TreeMap[str, bool]]
    feed_count: u256

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
                        "source": source["name"],
                        "url": source["url"],
                        "raw": content[:2000],
                        "extract_path": source.get("extract_path", "")
                    })
                except Exception:
                    raw_results.append({
                        "source": source["name"],
                        "url": source["url"],
                        "raw": "[FETCH_FAILED]",
                        "extract_path": ""
                    })

            task = f"""
You are a decentralized oracle aggregator. Extract and normalize data from multiple sources according to a schema.

SCHEMA (JSON keys to extract):
{json.dumps(schema)}

SOURCES:
{json.dumps(raw_results, indent=2)}

For each schema field, extract its value from the source data. If multiple sources provide different values for the same field, return the most common value or median. Flag any field where sources strongly disagree.

Respond ONLY in this JSON format:
{{
    "values": dict,  // schema field -> extracted value
    "confidence": int,  // 0-100
    "sources_used": int,  // how many sources contributed
    "warnings": [str]  // any data quality issues
}}
"""
            result = gl.exec_prompt(task).replace("```json", "").replace("```", "")
            return json.dumps(json.loads(result), sort_keys=True)

        result_json = json.loads(gl.eq_principle_strict_eq(fetch_and_aggregate))
        return result_json

    @gl.public.write
    def create_feed(self, description: str, sources_json: str, schema_json: str):
        self.feed_count += 1
        feed_id = str(self.feed_count)

        feed = Feed(
            feed_id=feed_id,
            description=description,
            sources=sources_json,
            schema=schema_json,
            last_value="{}",
            last_updated="0",
            update_count=0,
        )
        self.feeds[feed_id] = json.dumps(feed.__dict__)

    @gl.public.write
    def update_feed(self, feed_id: str):
        feed_data = json.loads(self.feeds.get(feed_id, "{}"))
        if not feed_data:
            raise Exception("Feed not found")

        result = self._aggregate_from_sources(
            feed_data["sources"],
            feed_data["schema"],
        )

        feed_data["last_value"] = json.dumps(result)
        feed_data["last_updated"] = str(gl.message.timestamp)
        feed_data["update_count"] += 1
        self.feeds[feed_id] = json.dumps(feed_data)

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
        })

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
            }
        return result
