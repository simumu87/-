"""Browser GUI for the prompt composer (stage 1: the existing composer, shown as a page, output in weighted-phrase format).

Run:   python gui_server.py            (opens http://127.0.0.1:8765 in the browser)
       python gui_server.py --port 9000 --no-browser

Only the Python standard library is used. The page talks to this server on the same machine; nothing leaves the computer.
"""
import argparse
import json
import random
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import krea2_composer as comp           # noqa: E402
import krea2_prompt_studio as studio    # noqa: E402
import krea2_weighted as wt             # noqa: E402

PAGE = HERE / "gui" / "index.html"


def _lora_rows():
    rows = []
    for r in studio.load_loras():
        if isinstance(r, dict) and r.get("trigger") and r.get("gender") != "male":
            rows.append({"name": r.get("name", r["trigger"]), "trigger": r["trigger"]})
    return rows


def options() -> dict:
    exps = comp.load_expressions()
    return {
        "loras": _lora_rows(),
        "locations": list(comp.PACK_FILES),
        "expressions": [{"key": k, "desc": v.get("desc_ko", "")} for k, v in exps.items()],
        "hair_presets": [{"key": k, "desc": v.get("desc_ko", "")} for k, v in comp.load_hair_presets().items()],
        "hair_colors": [{"key": k, "desc": v.get("desc_ko", "")} for k, v in comp.load_hair_colors().items()],
        "accessory_options": {k: v for k, v in comp.load_accessory_options().items() if isinstance(v, dict)},
        "canvas_sizes": json.loads((comp.k.CONFIG_DIR / "canvas_sizes.json").read_text(encoding="utf-8"))["items"],
        "lighting_triggers": json.loads((comp.k.CONFIG_DIR / "lighting_triggers.json").read_text(encoding="utf-8")),
        "outfit_colors": [{"key": k, "en": v} for k, v in comp.load_outfit_colors().items()],
        "makeups": [{"key": k, "desc": v.get("desc_ko", "")} for k, v in comp.load_makeup().items()],
        "modes": list(comp.MODES),
        "weights": {k: v for k, v in wt.DEFAULT_WEIGHTS.items()},
        "weight_order": list(wt.ORDER),
        "full_body_frame": wt.FULL_BODY_FRAME,
    }


def place_options(trigger: str, location: str) -> dict:
    pack = comp.load_pack(location)
    outfits = []
    for oid in comp.outfits_for_trigger(trigger):
        data = comp.load_outfit(oid)
        if location in data.get("applies_to", {}).get("locations", [location]):
            outfits.append({"id": oid, "name": data.get("name_ko", oid), "desc": data.get("desc_ko", "")})
    return {
        "outfits": outfits,
        "times": [{"key": k, "desc": v.get("desc_ko", "")} for k, v in pack["times"].items()],
        "framings": list(pack["camera"]),
        "moments": [{"key": k, "desc": v.get("desc_ko", ""), "frames": v.get("frames", list(pack["camera"]))}
                    for k, v in pack["moments"].items()],
    }


def compose(body: dict) -> dict:
    seed = int(body.get("seed") or random.randrange(1, 2**32))
    outfit = body.get("outfit", "")
    common = outfit == "__common__"
    custom = outfit == "__custom__"
    r = comp.compose_split(
        body["trigger"], "" if outfit in ("", "__none__", "__common__", "__custom__") else outfit,
        location=body["location"], time_key=body["time"],
        moment=(list(comp.load_pack(body["location"])["moments"])[0] if body["moment"] == "__custom__" else body["moment"]),
        framing=body["framing"], pose_text=body.get("pose_text", "") if body["moment"] == "__custom__" else "",
        accessories=body.get("accessories") or None,
        expression=body["expression"], hair=body.get("hair", ""), mode=body.get("mode", "보통"),
        reinforce=None if body.get("reinforce", "auto") == "auto" else int(body["reinforce"]),
        seed=seed, common_outfit=common, reference=bool(body.get("reference")), makeup=body.get("makeup", ""),
        hair_color=body.get("hair_color", ""),
        outfit_text=body.get("outfit_text", "") if custom else "", outfit_color="" if (custom or common) else body.get("outfit_color", ""))
    weights = {}
    for key, value in (body.get("weights") or {}).items():
        weights[key] = None if value in ("", None) else float(value)
    lighting_w = body.get("lighting_weight")
    weighted = wt.weighted_prompt(
        r["sections"], weights, lighting_tag=bool(body.get("lighting_tag", True)),
        lighting_weight=float(lighting_w) if lighting_w not in (None, "") else 1.1,
        lighting_words=body.get("lighting_words") or [], lighting_format=body.get("lighting_format", "separate"),
        short_skin=bool(body.get("short_skin", True)), extra_camera=body.get("extra_camera", ""))
    return {"seed": seed, "weighted": weighted, "plain": r["combined"], "sections": r["sections"],
            "problems": r["problems"], "words": len(weighted.split())}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload, ctype="application/json; charset=utf-8"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        try:
            if url.path in ("/", "/index.html"):
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
            elif url.path == "/api/options":
                self._send(200, options())
            elif url.path == "/api/place":
                q = parse_qs(url.query)
                self._send(200, place_options(q["trigger"][0], q["location"][0]))
            else:
                self._send(404, {"error": "not found"})
        except (KeyError, SystemExit, ValueError) as exc:
            self._send(400, {"error": str(exc)})

    def do_POST(self):
        if urlparse(self.path).path != "/api/compose":
            self._send(404, {"error": "not found"})
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            self._send(200, compose(body))
        except (KeyError, SystemExit, ValueError, json.JSONDecodeError) as exc:
            self._send(400, {"error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, fmt, *args):      # keep the console quiet
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Prompt composer in the browser")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"프롬프트 생성기 화면: {url}   (끄려면 Ctrl+C)")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
