"""Tests for the production-hardening fixes: dead-model skipping, live Blender progress, token error message."""
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel

from pipeline import llm as llm_mod
from pipeline.render3d import RenderProgress
from pipeline.utils import run_stream


class Out(BaseModel):
    ok: bool


def make_llm(models, behaviour):
    """LLM with a fake client. behaviour(model) -> Out instance or raises."""
    calls = []

    class Models:
        def generate_content(self, model, contents, config):
            calls.append(model)
            res = behaviour(model)

            class R:
                parsed = res
                text = ""
            return R()

    class Client:
        models = Models()

    obj = llm_mod.LLM.__new__(llm_mod.LLM)
    obj.client, obj.models, obj.dead = Client(), models, set()
    return obj, calls


def api_error(code):
    from google.genai import errors
    return errors.APIError(code, {"error": {"code": code, "message": "x", "status": "S"}})


class DeadModelTest(unittest.TestCase):
    def test_404_model_is_skipped_and_not_retried(self):
        def behaviour(model):
            if model == "old":
                raise api_error(404)
            return Out(ok=True)
        obj, calls = make_llm(["old", "new"], behaviour)
        self.assertTrue(obj.json("p", Out).ok)
        self.assertEqual(calls, ["old", "new"])
        self.assertEqual(obj.dead, {"old"})
        obj.json("p", Out)                       # second call must not touch the dead model again
        self.assertEqual(calls, ["old", "new", "new"])

    def test_all_models_dead_fails_fast_with_hint(self):
        obj, calls = make_llm(["a", "b"], lambda m: (_ for _ in ()).throw(api_error(404)))
        with mock.patch("time.sleep") as sl, self.assertRaises(RuntimeError) as cm:
            obj.json("p", Out)
        self.assertIn("llm.models", str(cm.exception))
        self.assertEqual(calls, ["a", "b"])      # one probe each, no 4x retry storm
        self.assertLessEqual(sl.call_count, 1)

    def test_429_is_retried_not_marked_dead(self):
        state = {"n": 0}

        def behaviour(model):
            state["n"] += 1
            if state["n"] == 1:
                raise api_error(429)
            return Out(ok=True)
        obj, _ = make_llm(["m"], behaviour)
        with mock.patch("time.sleep"):
            self.assertTrue(obj.json("p", Out).ok)
        self.assertEqual(obj.dead, set())

    def test_is_model_unavailable(self):
        self.assertTrue(llm_mod.is_model_unavailable(api_error(404)))
        self.assertTrue(llm_mod.is_model_unavailable(api_error(403)))
        self.assertFalse(llm_mod.is_model_unavailable(api_error(429)))
        self.assertFalse(llm_mod.is_model_unavailable(api_error(503)))
        self.assertTrue(llm_mod.is_model_unavailable(RuntimeError("404 NOT_FOUND: gone")))


class RenderProgressTest(unittest.TestCase):
    def test_counts_saved_frames_and_reports_eta(self):
        t = {"now": 0.0}
        rp = RenderProgress(total_frames=100, every=25, clock=lambda: t["now"])
        t["now"] = 0.0
        rp.t0 = 0.0
        with self.assertLogs("shorts", level="INFO") as cm:
            for i in range(1, 51):
                t["now"] = i * 4.0               # 4 s/frame
                rp("Fra:%d Mem:10M | Time:00:04.00 | Saved: 'f_%04d.png'" % (i, i))
        self.assertEqual(rp.done, 50)
        joined = "\n".join(cm.output)
        self.assertIn("render 25/100", joined)
        self.assertIn("4.00 s/frame", joined)
        self.assertIn("ETA 3.3 min", joined)    # 50 frames left * 4 s = 200 s

    def test_flags_missing_denoiser(self):
        rp = RenderProgress(10)
        with self.assertLogs("shorts", level="INFO"):
            rp("[blender] WARNING: this Blender build has no OpenImageDenoise -> raw (noisy) samples")
        self.assertTrue(rp.denoise_warning)


class RunStreamTest(unittest.TestCase):
    def _script(self, body):
        f = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False)
        f.write(textwrap.dedent(body)); f.close()
        return f.name

    def test_streams_lines_and_feeds_progress(self):
        script = self._script("""
            import sys
            print("[blender] scene 1/1: chip / happy", flush=True)
            for i in range(1, 6):
                print(f"Fra:{i} | Saved: 'f_{i:04d}.png'", flush=True)
            print("warning on stderr", file=sys.stderr, flush=True)
        """)
        rp = RenderProgress(5, every=5)
        with self.assertLogs("shorts", level="INFO"):
            run_stream([sys.executable, script], rp)
        self.assertEqual(rp.done, 5)

    def test_failure_raises_with_output_tail(self):
        script = self._script("""
            import sys
            print("Error: Python: Traceback ... KeyError 'Musgrave'", flush=True)
            sys.exit(1)
        """)
        with self.assertRaises(RuntimeError) as cm:
            run_stream([sys.executable, script])
        self.assertIn("KeyError", str(cm.exception))


class UploadTokenTest(unittest.TestCase):
    def test_refresh_error_gives_actionable_message(self):
        from google.auth.exceptions import RefreshError
        from pipeline import upload as up

        class Req:
            def next_chunk(self):
                raise RefreshError("invalid_grant: Token has been expired or revoked.")

        class Videos:
            def insert(self, **kw):
                return Req()

        class YT:
            def videos(self):
                return Videos()

        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            f.write(b"x" * 100); f.flush()
            with mock.patch.object(up, "_service", lambda: YT()), self.assertRaises(RuntimeError) as cm:
                up.upload(Path(f.name), "t", "d", [], {"upload": {}})
        msg = str(cm.exception)
        self.assertIn("In production", msg)
        self.assertIn("YT_REFRESH_TOKEN", msg)


if __name__ == "__main__":
    unittest.main()
