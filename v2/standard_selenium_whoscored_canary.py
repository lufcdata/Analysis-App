from __future__ import annotations

import csv
import json
import time
from collections import Counter
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

MATCH_ID = 1903117
OUT = Path("standard-selenium-canary")
URL = f"https://www.whoscored.com/Matches/{MATCH_ID}/Live"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--no-first-run")
    # Deliberately use normal Selenium. No SeleniumBase UC mode and no patched uc_driver.
    chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if chrome.exists():
        options.binary_location = str(chrome)

    driver = None
    try:
        print(f"Opening {URL} with standard Selenium/WebDriver")
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(90)
        driver.get(URL)

        # Wait for WhoScored's matchCentreData object to become available in page JS.
        wait = WebDriverWait(driver, 90, poll_frequency=1.0)
        wait.until(
            lambda d: d.execute_script(
                "return !!(window.require && require.config && require.config.params && "
                "require.config.params['args'] && require.config.params['args'].matchCentreData);"
            )
        )
        data = driver.execute_script("return require.config.params['args'].matchCentreData;")
        if not isinstance(data, dict):
            raise RuntimeError(f"matchCentreData was not returned as an object: {type(data)!r}")

        raw_path = OUT / "matchCentreData.json"
        raw_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        events = data.get("events") or []
        if not isinstance(events, list) or len(events) < 100:
            raise RuntimeError(f"Unexpected event payload: {type(events)!r}, rows={len(events) if hasattr(events, '__len__') else 'n/a'}")
        (OUT / "events_raw.json").write_text(json.dumps(events, indent=2, ensure_ascii=False), encoding="utf-8")

        qualifier_rows = []
        event_type_counts = Counter()
        satisfied_counts = Counter()
        events_with_qualifiers = 0
        qualifier_instances = 0
        numeric_qualifier_ids = 0

        for ev in events:
            ev_id = ev.get("id")
            ev_type = (ev.get("type") or {}).get("displayName") if isinstance(ev.get("type"), dict) else ev.get("type")
            event_type_counts[str(ev_type)] += 1
            qualifiers = ev.get("qualifiers") or []
            if qualifiers:
                events_with_qualifiers += 1
            for q in qualifiers:
                qualifier_instances += 1
                qtype = q.get("type") or {}
                qid = qtype.get("value") if isinstance(qtype, dict) else None
                qname = qtype.get("displayName") if isinstance(qtype, dict) else str(qtype)
                if isinstance(qid, int):
                    numeric_qualifier_ids += 1
                qualifier_rows.append(
                    {
                        "match_id": MATCH_ID,
                        "event_id": ev_id,
                        "event_type": ev_type,
                        "qualifier_id": qid,
                        "qualifier_name": qname,
                        "qualifier_value": q.get("value"),
                    }
                )
            for sid in ev.get("satisfiedEventsTypes") or []:
                satisfied_counts[str(sid)] += 1

        with (OUT / "qualifiers_exploded.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["match_id", "event_id", "event_type", "qualifier_id", "qualifier_name", "qualifier_value"],
            )
            writer.writeheader()
            writer.writerows(qualifier_rows)

        summary = {
            "match_id": MATCH_ID,
            "url": URL,
            "acquisition": "standard Selenium/WebDriver; no SeleniumBase UC mode",
            "events": len(events),
            "events_with_qualifiers": events_with_qualifiers,
            "qualifier_instances": qualifier_instances,
            "numeric_qualifier_ids": numeric_qualifier_ids,
            "unique_qualifier_ids": sorted({r["qualifier_id"] for r in qualifier_rows if isinstance(r["qualifier_id"], int)}),
            "event_type_counts": dict(event_type_counts),
            "satisfied_event_type_ids": sorted(satisfied_counts, key=lambda x: int(x) if x.isdigit() else x),
            "satisfied_event_type_instance_counts": dict(satisfied_counts),
            "top_level_keys": sorted(data.keys()),
            "home": data.get("home"),
            "away": data.get("away"),
        }
        (OUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

        print(json.dumps({k: summary[k] for k in ["match_id", "events", "events_with_qualifiers", "qualifier_instances", "numeric_qualifier_ids"]}, indent=2))
        print(f"unique qualifier IDs={len(summary['unique_qualifier_ids'])}")
        print(f"satisfiedEventsTypes IDs={len(summary['satisfied_event_type_ids'])}")

        if qualifier_instances == 0 or numeric_qualifier_ids == 0:
            raise RuntimeError("Raw events were found, but numeric qualifier evidence was missing.")

    except Exception:
        if driver is not None:
            try:
                (OUT / "page_source.html").write_text(driver.page_source or "", encoding="utf-8")
                driver.save_screenshot(str(OUT / "failure.png"))
                (OUT / "failure_url.txt").write_text(driver.current_url or "", encoding="utf-8")
            except Exception:
                pass
        raise
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
