import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from saarthi import schema
from saarthi.glitch import PATH, GlitchLink
from saarthi.states import Activity


def test_build_music_video_tutorial():
    s = schema.build(Activity(music_playing=True, media_site="youtube", media_title="Tum Hi Ho",
                              media_channel="Arijit Singh - Topic"), "idle")  # fmt: skip
    assert s.media.kind == "music" and s.media.channel == "Arijit Singh - Topic"
    s = schema.build(Activity(video_playing=True, media_tutorial=True, media_site="youtube"), "watching", "notes")
    assert (s.media.kind, s.state, s.take) == ("tutorial", "watching", "notes")
    s = schema.build(Activity(video_playing=True, media_site="youtube"), "watching", "popcorn")
    assert s.media.kind == "video"
    assert schema.build(Activity(), "idle").media is None


def test_typing_and_scrolling_levels():
    assert schema.build(Activity(keys_per_sec=6), "typing_fast").typing == "fast"
    assert schema.build(Activity(keys_per_sec=1), "typing_slow").typing == "slow"
    s = schema.build(Activity(scrolls_per_sec=2), "scrolling")
    assert s.typing == "none" and s.scrolling


def test_json_is_versioned_and_complete():
    d = json.loads(schema.build(Activity(), "idle").model_dump_json())
    assert d["schema_version"] == schema.SCHEMA_VERSION
    for key in (
        "source",
        "device",
        "at",
        "typing",
        "keys_per_sec",
        "scrolling",
        "idle_seconds",
        "media",
        "state",
        "take",
    ):
        assert key in d
    assert not {"weather", "battery", "reminders", "break"} & set(d)  # Saarthi's own features stay out


def test_ticking_numbers_are_the_same_moment():
    a = schema.build(Activity(keys_per_sec=1, idle_seconds=2), "typing_slow")
    b = schema.build(Activity(keys_per_sec=2.5, idle_seconds=9), "typing_slow")
    assert b.same_moment(a)
    assert not schema.build(Activity(keys_per_sec=6), "typing_fast").same_moment(a)
    assert not schema.build(Activity(idle_seconds=200), "afk").same_moment(a)


class FakeGlitch:
    def __init__(self, status=200):
        self.got: list[dict] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                assert self.path == PATH
                outer.got.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(status)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def test_sends_on_change_and_heartbeat():
    g = FakeGlitch()
    try:
        link = GlitchLink(g.url)
        link.offer(schema.build(Activity(keys_per_sec=1), "typing_slow"))
        assert link.send_due(100.0)
        link.offer(schema.build(Activity(keys_per_sec=2), "typing_slow"))
        assert not link.send_due(110.0)  # same moment
        assert link.send_due(131.0)  # heartbeat
        link.offer(schema.build(Activity(video_playing=True, media_tutorial=True), "watching", "notes"))
        assert link.send_due(132.0)
        assert [d["state"] for d in g.got] == ["typing_slow", "typing_slow", "watching"]
        assert g.got[-1]["media"]["kind"] == "tutorial"
    finally:
        g.close()


def test_glitch_down_or_off_is_quiet():
    link = GlitchLink("http://127.0.0.1:9")  # nothing listens there
    link.offer(schema.build(Activity(), "idle"))
    assert not link.send_due(1.0) and link.error
    off = GlitchLink("")
    assert not off.enabled
    off.start()  # no thread, nothing sent
    g = FakeGlitch(status=404)  # Glitch without the endpoint yet
    try:
        link = GlitchLink(g.url)
        link.offer(schema.build(Activity(), "idle"))
        assert not link.send_due(1.0) and link.error == "HTTP 404"
    finally:
        g.close()
