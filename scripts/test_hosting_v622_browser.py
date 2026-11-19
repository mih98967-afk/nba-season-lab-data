#!/usr/bin/env python3
"""Exercise the existing Hosting site with Chromium and an isolated fake guest.

This script neither contacts Firebase nor writes an owner account. Every public
data request is served from the selected local snapshot. Fixture mode generates
explicitly synthetic data and proves UI behavior only. Actual mode uses the
canonical generated feeds, with the browser clock fixed at issuance + 60 s;
the release builder separately checks real wall-clock data freshness.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from threading import Thread
import traceback
from urllib.parse import unquote, urlparse

UTC = timezone.utc
POSITIONS = ["PG", "SG", "SF", "PF", "C"]
DATA_NAMES = ["model_forecasts_v1.json", "matchup_difficulty_v1.json", "schedule.json", "live.json"]


def stamp(value):
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def difficulty_snapshot_is_fresh(as_of_utc, replay_tick, actual_mode, wall_now=None):
    """Replayed forecast time and current wall time are distinct clocks.

    The difficulty generator runs after issuing the forecast, so its timestamp
    can legitimately be newer than the UI replay tick. Do not relax the 72 h
    limit or permit future snapshots in actual mode.
    """
    reference = (wall_now or datetime.now(UTC)) if actual_mode else replay_tick
    observed = parse_time(as_of_utc)
    return reference - timedelta(hours=72) <= observed <= reference


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def make_fixture(base):
    """A deterministic test season: synthetic IDs, results and model values."""
    tick = datetime(2026, 11, 18, 12, tzinfo=UTC)
    issued = tick - timedelta(minutes=1)
    teams = sorted(item["team"] for item in base["teams"])
    ring = list(teams)
    games = []
    for round_number in range(80):
        at = datetime(2026, 10, 20, 23, tzinfo=UTC) + timedelta(days=round_number * 2)
        for index in range(15):
            home, away = ring[index], ring[-1 - index]
            if round_number % 2:
                home, away = away, home
            tip = at + timedelta(minutes=index * 5)
            games.append({"id": f"espn_{990000000 + len(games)}", "utc": stamp(tip),
                          "epoch": int(tip.timestamp() * 1000), "home": home, "away": away,
                          "status": "final" if tip < tick else "scheduled", "source": "SYNTHETIC UI FIXTURE"})
        ring = [ring[0], ring[-1], *ring[1:-1]]
    forecasts, actuals = [], []
    for index, player in enumerate(base["players"]):
        played = next(g for g in reversed(games) if g["status"] == "final" and player["team"] in (g["home"], g["away"]))
        actuals.append({"id": player["id"], "name": player["name"], "game_id": played["id"],
                        "team": player["team"], "utc": played["utc"], "minutes": 24,
                        "fp": 20, "source": "SYNTHETIC UI FIXTURE", "box": {"pts": 14, "reb": 4, "ast": 2}})
        for game in games:
            tip = parse_time(game["utc"])
            if not tick < tip < tick + timedelta(days=28) or player["team"] not in (game["home"], game["away"]):
                continue
            mu, probability = 18.0 + index % 12, 0.82 - 0.06 * (index % 5)
            horizon = (tip.date() - tick.date()).days
            forecasts.append({"player_id": player["id"], "nba_id": str(2000000 + index),
                              "game_id": game["id"], "nba_game_id": f"00226{int(game['id'].split('_')[1]) - 990000000:05d}",
                              "team": player["team"], "opponent": game["away"] if game["home"] == player["team"] else game["home"],
                              "home": game["home"] == player["team"], "game_utc": game["utc"],
                              "lock_utc": stamp(tip - timedelta(minutes=30)), "actual_horizon_days": horizon,
                              "model_id": "near_latest" if horizon < 2 else "long_latest", "support": "exact_lead",
                              "p_play": probability, "mean_if_play": mu, "expected_fp": probability * mu,
                              "conditional_intervals": {"50": [mu - 5, mu + 5], "80": [mu - 10, mu + 10], "95": [mu - 17, mu + 17]},
                              "unconditional_intervals": {"50": [0, mu + 4], "80": [0, mu + 10], "95": [-3, mu + 17]},
                              "interval_status": "historically_calibrated_exact_lead", "eligible_for_decision": True,
                              "official_status": None, "warnings": [],
                              "reasons": ["Синтетический тест интерфейса; это не прогноз для использования.",
                                          "Фиксированные тестовые минуты и вероятность."]})
    model = {"schema_version": 1, "kind": "nba_per_game_model_forecasts", "status": "ready",
             "issued_at_utc": stamp(issued), "source_capture_completed_at_utc": stamp(issued - timedelta(minutes=1)),
             "valid_until_utc": stamp(issued + timedelta(hours=24)), "asof_date_et": "2026-11-18",
             "model_manifest_sha256": "a" * 64, "source_manifest_sha256": "b" * 64,
             "model_policy": {"site_default": True, "purpose": "SYNTHETIC UI FIXTURE ONLY"}, "rows": forecasts, "windows": []}
    opponents = {}
    for index, team in enumerate(teams):
        opponents[team] = {}
        general = (index - 14.5) / 10
        for position_index, position in enumerate(["ALL", *POSITIONS]):
            extra = 0 if position == "ALL" else ((index + position_index) % 7 - 3) / 10
            total = general + extra
            opponents[team][position] = {"general_delta_fp": general, "position_extra_fp": extra,
                                        "total_delta_fp": total, "effect_interval95": [total - 0.7, total + 0.7],
                                        "weighted_player_games": 120, "effective_games": 83,
                                        "n_games": 140, "n_players": 50, "current_season_n_games": 13,
                                        "latest_game_date": "2026-11-17", "status": "descriptive_research",
                                        "predictive_validated": False}
    difficulty = {"schema": "nba_matchup_difficulty_v1", "as_of_utc": stamp(issued),
                  "latest_outcome_date": "2026-11-17", "production_forecasts_adjusted": False,
                  "opponents": opponents, "purpose": "SYNTHETIC UI FIXTURE ONLY"}
    schedule = {"schema_version": 1, "status": "verified_public_calendar_with_known_gaps", "updated_at_utc": stamp(issued),
                "fantasy_timezone": "Europe/Moscow", "completeness": {"teams": 30, "team_games_min": 80, "unassigned_or_unavailable_games": 0},
                "games": games, "purpose": "SYNTHETIC UI FIXTURE ONLY"}
    live = {"schema_version": 4, "mode": "live_sync", "updated_at_utc": stamp(issued),
            "scoreboard_checked_at_utc": stamp(issued), "games": [g for g in games if g["status"] == "final"],
            "schedule": [], "rows": actuals, "injuries": [], "unmatched": [], "warnings": ["SYNTHETIC UI FIXTURE ONLY"]}
    return dict(zip(DATA_NAMES, [model, difficulty, schedule, live])), tick


def guest_state(base, feed, tick):
    first_games = {}
    for row in sorted(feed["rows"], key=lambda item: item["game_utc"]):
        if tick < parse_time(row["game_utc"]) < tick + timedelta(days=14):
            first_games.setdefault(row["player_id"], row)
    candidates = {cid for cid, row in first_games.items() if row.get("eligible_for_decision")
                  and row.get("conditional_intervals") and row.get("model_id") in ("near_latest", "long_latest")}
    roster, clubs = [], Counter()
    for position in POSITIONS:
        choices = sorted((p for p in base["players"] if p["pos"] == position and p["id"] in candidates),
                         key=lambda p: (abs(p["start_price"] - 1500), p["id"]))
        for player in choices:
            if clubs[player["team"]] >= 2:
                continue
            roster.append(player["id"]); clubs[player["team"]] += 1
            if len(roster) == 2 * (POSITIONS.index(position) + 1):
                break
    assert len(roster) == 10, "Snapshot cannot form the synthetic 10-player QA roster"
    return {"v": 5, "initialRoster": roster, "roster": roster, "initialEpoch": 1792522800000,
            "cash": 1000, "executed": [], "prices": {}, "teamOverrides": {}, "medical": {}, "draft": [],
            "riskMode": "baseline", "modelMode": "current", "lastUpdate": None}


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-dir", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=["fixture", "actual"], required=True)
    parser.add_argument("--browser-executable", type=Path, help="Optional normally installed Chromium; no security flags are changed")
    args = parser.parse_args()
    site, data_root, output = args.site_dir.resolve(), args.data_root.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {"schema": "nba_hosting_browser_qa_v1", "status": "FAIL", "mode": args.mode, "owner_profile": "synthetic local guest only",
              "external_network_allowed": False, "firebase_enabled": False, "screenshots": [], "checks": []}
    server = browser = page = playwright = None
    blocked_writes, blocked_external, reads, errors = [], [], [], []
    try:
        base = json.loads((site / "data/base.json").read_text())
        if args.mode == "fixture":
            data, tick = make_fixture(base)
        else:
            data = {name: json.loads((data_root / name).read_text()) for name in DATA_NAMES}
            tick = parse_time(data[DATA_NAMES[0]]["issued_at_utc"]) + timedelta(seconds=60)
        forecast, difficulty, schedule, live = (data[name] for name in DATA_NAMES)
        assert forecast["schema_version"] == 1 and forecast["kind"] == "nba_per_game_model_forecasts"
        assert forecast["status"] == "ready" and forecast["model_policy"]["site_default"] is True
        assert parse_time(forecast["source_capture_completed_at_utc"]) <= parse_time(forecast["issued_at_utc"]) < tick < parse_time(forecast["valid_until_utc"])
        assert difficulty["schema"] == "nba_matchup_difficulty_v1" and len(difficulty["opponents"]) == 30
        assert difficulty["production_forecasts_adjusted"] is False
        assert all(set(["ALL", *POSITIONS]) <= set(row) for row in difficulty["opponents"].values())
        assert schedule["schema_version"] == 1 and 1100 <= len(schedule["games"]) <= 1230
        assert live["schema_version"] == 4 and live["mode"] == "live_sync"
        # UI replay uses a clock fixed 60 s after forecast issuance. The
        # difficulty snapshot is produced later in the same pipeline, so
        # checking its wall-clock timestamp against that replay clock would
        # reject a valid, fresh snapshot as "from the future".
        # Keep the strict <=72 h freshness requirement against the actual
        # verification clock; the release builder checks it independently.
        assert difficulty_snapshot_is_fresh(difficulty["as_of_utc"], tick, args.mode == "actual"), "DIFFICULTY_SNAPSHOT_NOT_FRESH"
        state = guest_state(base, forecast, tick)
        payloads = {name: encoded(value) for name, value in data.items()}
        report.update({"clock_utc": stamp(tick), "clock_purpose": "UI replay at issuance + 60 seconds; real freshness is a separate release gate",
                       "data_sha256": {name: hashlib.sha256((data_root / name).read_bytes() if args.mode == "actual" else payloads[name]).hexdigest() for name in DATA_NAMES},
                       "source_sha256": {name: hashlib.sha256((site / name).read_bytes()).hexdigest() for name in ["index.html", "styles.css", "app.js", "forecast_runtime.js", "schedule_difficulty.js", "forecast_styles.css"]},
                       "forecast_rows": len(forecast["rows"]), "schedule_games": len(schedule["games"]),
                       "position_ratings": sum(len(row) for row in difficulty["opponents"].values()),
                       "desktop": [1440, 1040], "mobile": [390, 844]})
        script = (site / "app.js").read_text()
        storage_key = re.search(r"const KEY='([^']+)'", script)
        assert storage_key, "Established guest storage key not found"
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(site)))
        Thread(target=server.serve_forever, daemon=True).start()

        from playwright.sync_api import sync_playwright
        playwright = sync_playwright().start()
        if playwright:
            browser = playwright.chromium.launch(headless=True, **({"executable_path": str(args.browser_executable)} if args.browser_executable else {}))
            context = browser.new_context(viewport={"width": 1440, "height": 1040}, device_scale_factor=1,
                                          timezone_id="Europe/Moscow", locale="ru-RU", service_workers="block")
            page = context.new_page()
            page.clock.set_fixed_time(tick)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("dialog", lambda dialog: dialog.dismiss())

            def route_request(route):
                request, parsed = route.request, urlparse(route.request.url)
                if request.method != "GET":
                    blocked_writes.append({"method": request.method, "url": request.url}); route.abort(); return
                local = parsed.hostname in ("127.0.0.1", "localhost")
                if local and parsed.path == "/firebase-config.js":
                    route.fulfill(status=200, body="window.FIREBASE_CONFIG={}; /* isolated UI QA */", content_type="text/javascript"); return
                relative = None
                if local and parsed.path.startswith("/data/"):
                    relative = unquote(parsed.path[len("/data/"):])
                elif parsed.hostname == "raw.githubusercontent.com" and parsed.path.startswith("/mih98967-afk/nba-season-lab-data/main/data/"):
                    relative = unquote(parsed.path.split("/main/data/", 1)[1])
                if relative is not None:
                    path = (data_root / relative).resolve()
                    assert path.is_relative_to(data_root), "Unsafe data request"
                    reads.append(relative)
                    body = payloads.get(relative)
                    if body is None and args.mode == "actual" and path.is_file():
                        body = path.read_bytes()
                    if body is None and local and (site / "data" / relative).is_file():
                        body = (site / "data" / relative).read_bytes()
                    route.fulfill(status=200 if body is not None else 404, body=body or b"{}", content_type="application/json",
                                  headers={"Access-Control-Allow-Origin": "*"}); return
                if local:
                    route.continue_(); return
                blocked_external.append(request.url); route.abort()

            context.route("**/*", route_request)
            context.add_init_script("localStorage.setItem(" + json.dumps(storage_key.group(1)) + "," + json.dumps(json.dumps(state)) + ");")

            def shot(name):
                page.screenshot(path=str(output / name), full_page=True)
                report["screenshots"].append(name)

            def check_page(label):
                assert "NaN" not in page.locator("body").inner_text(), label + ": rendered NaN"
                dimensions = page.evaluate("({viewport:innerWidth,document:document.documentElement.scrollWidth})")
                assert dimensions["document"] <= dimensions["viewport"] + 2, (label, dimensions)
                report["checks"].append(label)

            page.goto(f"http://127.0.0.1:{server.server_port}/", wait_until="networkidle", timeout=60000)
            page.wait_for_function("window.PythosNBA && window.PythosNBA.modelForecasts() && window.PythosNBA.matchupDifficulty()", timeout=30000)
            assert page.locator(".model-mode-bar").count() == 1
            assert "Новая модель FP и участия" in page.locator(".model-mode-bar").inner_text()
            check_page("desktop new-model default"); shot("01_today_desktop.png")
            page.locator('[data-model-choice="legacy"]').click()
            assert page.evaluate("window.PythosNBA.getState().modelMode") == "legacy"
            page.locator('[data-model-choice="research"]').click()
            assert page.evaluate("window.PythosNBA.getState().modelMode") == "research"
            report["checks"].append("actual old/new model button clicks")

            page.locator('#navigation [data-tab="calendar"]').click()
            page.locator('[data-calendar-quick="difficulty"]').click()
            page.wait_for_selector("#difficulty-position")
            assert page.locator(".difficulty-table tbody tr").count() == 10
            assert page.locator("#difficulty-position").input_value() == "ALL"
            page.locator('[data-action="difficulty-toggle-more"]').click()
            assert page.locator(".difficulty-table tbody tr").count() == 30
            page.locator('[data-action="difficulty-toggle-more"]').click()
            assert page.locator(".difficulty-table tbody tr").count() == 10
            report["checks"].append("10 compact difficulty cards, expand to all 30 and collapse")
            check_page("desktop general difficulty"); shot("02_difficulty_all_desktop.png")
            for position in POSITIONS:
                page.select_option("#difficulty-position", position)
                assert page.locator("#difficulty-position").input_value() == position
                assert page.locator(".difficulty-table tbody tr").count() == 10
            page.select_option("#difficulty-position", "PG")
            for days in [7, 14, 21, 28]:
                page.locator(f'[data-difficulty-days="{days}"]').click()
                assert page.locator(f'[data-difficulty-days="{days}"]').get_attribute("aria-pressed") == "true"
            assert page.locator("#difficulty-position").input_value() == "PG"
            shot("03_difficulty_pg_28_desktop.png")
            page.select_option("#difficulty-sort", "hardest")
            values = page.locator(".difficulty-table tbody td:nth-child(3) strong").all_text_contents()
            scores = [float(value.replace("\u00a0", "").replace(",", ".")) for value in values if value != "—"]
            assert scores == sorted(scores), "Hardest-first sort is not applied"
            page.check("#difficulty-owned")
            count = page.evaluate("new Set(window.PythosNBA.getState().roster.map(id => window.PythosNBA.base.players.find(p => p.id === id)?.team)).size")
            assert page.locator(".difficulty-table tbody tr").count() == count
            page.uncheck("#difficulty-owned")
            report["checks"].append("all five positions, all four horizons, hardest sort, owned-club filter")

            page.locator('#navigation [data-tab="players"]').click()
            page.locator('[data-market-view="mine"]').click()
            first = page.locator(".market-item [data-player]").first
            target_id = first.get_attribute("data-player")
            first.click()
            page.wait_for_selector(".player-model-panel .model-game-values")
            model_card = page.locator(".player-model-panel .model-game").filter(has=page.locator(".model-game-values")).first
            assert model_card.locator(".model-game-values > div").count() == 3
            displayed = model_card.locator(".model-game-values b").all_text_contents()
            numbers = [float(re.sub(r"[%\s\u00a0\u202f]", "", value).replace(",", ".")) for value in displayed]
            assert abs(numbers[1] * numbers[2] / 100 - numbers[0]) <= max(0.25, abs(numbers[1]) * 0.005 + 0.1), "Displayed unconditional FP is inconsistent with conditional FP and P(play)"
            model_card.locator(".model-ranges summary").click()
            assert model_card.locator(".model-ranges tbody tr").count() == 3
            assert [row.split("%")[0] for row in model_card.locator(".model-ranges tbody tr").all_text_contents()] == ["50", "80", "95"]
            check_page("desktop three quantities and 50/80/95 ranges"); shot("04_player_ranges_desktop.png")
            page.locator('[data-action="close-modal"]').click()

            page.set_viewport_size({"width": 390, "height": 844})
            page.locator('#navigation [data-tab="calendar"]').click()
            page.locator('[data-calendar-quick="difficulty"]').click()
            check_page("mobile difficulty without document overflow"); shot("05_difficulty_mobile.png")
            page.locator('#navigation [data-tab="players"]').click()
            page.locator('[data-market-view="mine"]').click()
            page.locator(f'.market-item [data-player="{target_id}"]').click()
            page.locator(".model-ranges summary").first.click()
            check_page("mobile player ranges without document overflow"); shot("06_player_ranges_mobile.png")
            final_state = page.evaluate("window.PythosNBA.getState()")
            for key in ["roster", "initialRoster", "cash", "executed", "medical", "prices", "teamOverrides"]:
                assert final_state[key] == state[key], "UI changed synthetic owner data: " + key
            assert not errors, errors
            assert not blocked_writes, blocked_writes
            report["checks"].append("no JS errors, no network writes, original guest roster/cash/history preserved")
            report["status"] = "PASS"
            browser.close(); browser = None
    except Exception as error:
        report["error"] = str(error)
        report["traceback"] = traceback.format_exc()
        if page is not None:
            try:
                page.screenshot(path=str(output / "FAILURE.png"), full_page=True)
                report["screenshots"].append("FAILURE.png")
            except Exception:
                pass
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if playwright is not None:
            playwright.stop()
        if server is not None:
            server.shutdown(); server.server_close()
        report.update({"verified_at_utc": stamp(datetime.now(UTC)), "source_reads": sorted(set(reads)), "blocked_write_requests": blocked_writes,
                       "blocked_external_reads": sorted(set(blocked_external)), "page_errors": errors})
        (output / "BROWSER_QA.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
