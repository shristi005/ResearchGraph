"""Stdlib-only tests of the AI layer (providers, router, fallback, quota, embeddings, auth tokens, ranking).
They run real provider-client code over real HTTP against tests/fake_ai_server.py. That proves plumbing and routing logic;
it is NOT evidence of real model quality or of real Groq/Gemini behaviour (see docs/LIVE_TESTS.md for the live checklist).
Run:  python3 -m unittest tests.test_ai_layer -v   (from backend/)"""
import base64, hashlib, hmac, json, math, time, unittest
import urllib.request

from app import config
from app.ai import embeddings, router
from app.ai.errors import AIConfigError, AIUnavailable
from app.ai.providers import PROVIDERS
from app.ai.quota import QuotaTracker
from app.ai.ranking import pick
from app import auth_tokens
from tests import fake_ai_server as fake

SRV = fake.serve(0)
BASE = f"http://127.0.0.1:{SRV.server_address[1]}"


def set_mode(**kw):
    fake.MODES.update(kw)


def sysprompt(task="extraction"):
    return f"TASK:{task}\nYou are a careful assistant. Reply in JSON."


class Base(unittest.TestCase):
    def setUp(self):
        self._saved = {k: getattr(config, k) for k in ("GROQ_API_KEY", "GEMINI_API_KEY", "GROQ_URL", "GEMINI_BASE", "AI_FALLBACK_ENABLED",
                                                         "AI_MAX_RETRIES", "AI_PRIMARY_PROVIDER", "AI_TIMEOUT", "EMBED_PROVIDER", "EMBED_MODEL")}
        config.GROQ_API_KEY, config.GEMINI_API_KEY = "gsk_SECRET_GROQ", "SECRET_GEMINI"
        config.GROQ_URL = f"{BASE}/openai/v1/chat/completions"
        config.GEMINI_BASE = f"{BASE}/v1beta"
        config.AI_FALLBACK_ENABLED, config.AI_MAX_RETRIES, config.AI_PRIMARY_PROVIDER, config.AI_TIMEOUT = True, 1, "", 5
        set_mode(groq="ok", gemini="ok")
        for k in fake.CALLS: fake.CALLS[k] = 0
        self._tracker = router.tracker
        router.tracker = QuotaTracker()
        embeddings.tracker = router.tracker
        self._sleep, router._sleep = router._sleep, lambda s: None
        self._lim = {k: dict(v) for k, v in config.PROVIDER_LIMITS.items()}
        for v in config.PROVIDER_LIMITS.values(): v.update(rpm=0, rpd=0, tpm=0, tpd=0)

    def tearDown(self):
        for k, v in self._saved.items(): setattr(config, k, v)
        router.tracker = self._tracker; embeddings.tracker = self._tracker; router._sleep = self._sleep
        config.PROVIDER_LIMITS.update(self._lim)

    def run_json(self, feature="extraction"):
        return router.complete(feature, sysprompt(), [{"role": "user", "content": "Paper text about GANs."}], json_mode=True)


class RoutingTests(Base):
    def test_feature_routing_uses_preferred_provider(self):
        r = self.run_json("extraction"); self.assertEqual(r.provider, "gemini"); self.assertFalse(r.fallback_used)
        r = router.complete("mentor", sysprompt("mentor"), [{"role": "user", "content": "q [S1]"}])
        self.assertEqual(r.provider, "groq"); self.assertIn("[S1]", r.text)
        self.assertEqual((fake.CALLS["groq"], fake.CALLS["gemini"]), (1, 1))

    def test_normalized_result_fields(self):
        r = self.run_json("graph")
        self.assertEqual((r.provider, r.total_tokens), ("groq", 150)); self.assertTrue(r.model); self.assertGreaterEqual(r.latency_s, 0)

    def test_forced_primary(self):
        config.AI_PRIMARY_PROVIDER = "groq"
        self.assertEqual(self.run_json("extraction").provider, "groq")

    def test_groq_429_falls_back_to_gemini_and_cools_down(self):
        set_mode(groq="429")
        r = router.complete("mentor", sysprompt("mentor"), [{"role": "user", "content": "q"}])
        self.assertEqual(r.provider, "gemini"); self.assertTrue(r.fallback_used); self.assertEqual(r.attempts, ["groq:rate_limit", "gemini:ok"])
        r2 = router.complete("mentor", sysprompt("mentor"), [{"role": "user", "content": "q2"}])
        self.assertEqual(r2.provider, "gemini")
        self.assertEqual(fake.CALLS["groq"], 1, "cooldown must stop us hammering a rate-limited provider")

    def test_gemini_429_falls_back_to_groq(self):
        set_mode(gemini="429")
        r = self.run_json("extraction")
        self.assertEqual((r.provider, r.fallback_used), ("groq", True))

    def test_both_rate_limited_no_loops_no_fabrication(self):
        set_mode(groq="429", gemini="429")
        with self.assertRaises(AIUnavailable) as cm: self.run_json("extraction")
        self.assertEqual((fake.CALLS["groq"], fake.CALLS["gemini"]), (1, 1))
        self.assertIn("temporarily", str(cm.exception))

    def test_transient_retries_same_provider_once_then_falls_back(self):
        set_mode(groq="500")
        r = router.complete("mentor", sysprompt("mentor"), [{"role": "user", "content": "q"}])
        self.assertEqual(r.provider, "gemini"); self.assertEqual(fake.CALLS["groq"], 2)

    def test_bad_request_is_never_forwarded(self):
        set_mode(gemini="400")
        with self.assertRaises(AIUnavailable): self.run_json("extraction")
        self.assertEqual((fake.CALLS["gemini"], fake.CALLS["groq"]), (1, 0))

    def test_invalid_key_falls_back_and_disables_provider(self):
        set_mode(groq="401")
        r = router.complete("mentor", sysprompt("mentor"), [{"role": "user", "content": "q"}])
        self.assertEqual(r.provider, "gemini")
        router.complete("mentor", sysprompt("mentor"), [{"role": "user", "content": "q2"}])
        self.assertEqual(fake.CALLS["groq"], 1)

    def test_unavailable_model_falls_back(self):
        set_mode(gemini="404")
        self.assertEqual(self.run_json("extraction").provider, "groq")

    def test_malformed_json_falls_back_once(self):
        set_mode(gemini="badjson")
        self.assertEqual(self.run_json("extraction").provider, "groq")
        set_mode(gemini="badjson", groq="badjson")
        with self.assertRaises(ValueError): self.run_json("extraction")

    def test_fallback_disabled(self):
        config.AI_FALLBACK_ENABLED = False; set_mode(gemini="429")
        with self.assertRaises(AIUnavailable): self.run_json("extraction")
        self.assertEqual(fake.CALLS["groq"], 0)

    def test_no_keys_and_single_key(self):
        config.GROQ_API_KEY = config.GEMINI_API_KEY = ""
        with self.assertRaises(AIConfigError): self.run_json()
        config.GROQ_API_KEY = "k"; set_mode(groq="429")
        with self.assertRaises(AIUnavailable): router.complete("mentor", sysprompt("mentor"), [{"role": "user", "content": "q"}])
        self.assertEqual(fake.CALLS["gemini"], 0, "an unconfigured provider is never contacted")

    def test_local_quota_guard_diverts_before_any_429(self):
        config.PROVIDER_LIMITS["groq"]["rpm"] = 1
        a = router.complete("mentor", sysprompt("mentor"), [{"role": "user", "content": "1"}])
        b = router.complete("mentor", sysprompt("mentor"), [{"role": "user", "content": "2"}])
        self.assertEqual((a.provider, b.provider), ("groq", "gemini")); self.assertEqual(fake.CALLS["groq"], 1)

    def test_fallback_sends_identical_task_and_schema_requirement(self):
        msgs = [{"role": "user", "content": "SOURCES: [S1] only paper 7. QUESTION: limits?"}]
        set_mode(gemini="429")
        router.complete("extraction", sysprompt(), msgs, json_mode=True)       # gemini 429 -> groq
        g_sys, g_prompt, g_fmt = fake.LAST["groq"]
        set_mode(gemini="ok", groq="ok"); config.AI_PRIMARY_PROVIDER = "gemini"
        router.tracker = QuotaTracker()          # forget the cooldown caused by the simulated 429 above
        router.complete("extraction", sysprompt(), msgs, json_mode=True)
        m_sys, m_prompt, m_fmt = fake.LAST["gemini"]
        self.assertEqual((g_sys, g_prompt), (m_sys, m_prompt))
        self.assertEqual((g_fmt, m_fmt), ({"type": "json_object"}, "application/json"))

    def test_only_two_free_providers_exist_no_paid_path(self):
        self.assertEqual(set(PROVIDERS), {"groq", "gemini"})

    def test_secrets_never_in_errors(self):
        set_mode(groq="401", gemini="401")
        with self.assertRaises(AIUnavailable) as cm: self.run_json("extraction")
        self.assertNotIn("SECRET", str(cm.exception))

    def test_unreachable_provider_is_transient_not_crash(self):
        config.GROQ_URL = "http://127.0.0.1:9/x"
        r = router.complete("mentor", sysprompt("mentor"), [{"role": "user", "content": "q"}])
        self.assertEqual(r.provider, "gemini")


class EmbeddingTests(Base):
    def test_gemini_embeddings_768_normalized_and_ranked(self):
        config.EMBED_PROVIDER, config.EMBED_MODEL = "gemini", "gemini-embedding-001"
        docs = embeddings.embed_documents(["crop disease detection with drones and GANs", "music mixing workflow with AI tools"])
        q = embeddings.embed_query("detect plant disease from UAV imagery")
        self.assertTrue(all(len(v) == 768 for v in docs + [q]))
        self.assertAlmostEqual(math.sqrt(sum(x * x for x in q)), 1.0, places=5)
        dot = lambda a, b: sum(x * y for x, y in zip(a, b))
        self.assertEqual(max(range(2), key=lambda i: dot(q, docs[i])), 0)
        self.assertTrue(embeddings.model_id().startswith("gemini:gemini-embedding-001:768"))

    def test_embedding_429_is_a_clean_unavailable(self):
        config.EMBED_PROVIDER = "gemini"; set_mode(gemini="429")
        with self.assertRaises(AIUnavailable): embeddings.embed_query("x")

    def test_hash_provider_for_offline_tests(self):
        config.EMBED_PROVIDER = "hash"
        v = embeddings.embed_query("hello world"); self.assertEqual(len(v), 768)
        self.assertNotEqual(embeddings.model_id().split(":")[0], "gemini")


class AuthTokenTests(unittest.TestCase):
    @staticmethod
    def mint(secret, alg="HS256", **claims):
        b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
        h, p = b({"alg": alg, "typ": "JWT"}), b({"aud": "authenticated", "exp": time.time() + 3600, "sub": "user-1", "email": "a@b.c", **claims})
        sig = base64.urlsafe_b64encode(hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
        return f"{h}.{p}.{sig}"

    def test_valid_expired_tampered_wrongalg(self):
        self.assertEqual(auth_tokens.verify_hs256(self.mint("s"), "s").id, "user-1")
        with self.assertRaises(auth_tokens.AuthError): auth_tokens.verify_hs256(self.mint("s", exp=time.time() - 5), "s")
        with self.assertRaises(auth_tokens.AuthError): auth_tokens.verify_hs256(self.mint("other"), "s")
        with self.assertRaises(auth_tokens.AuthError): auth_tokens.verify_hs256(self.mint("s", alg="none"), "s")
        with self.assertRaises(auth_tokens.AuthError): auth_tokens.verify_hs256(self.mint("s", aud="anon"), "s")
        with self.assertRaises(auth_tokens.AuthError): auth_tokens.verify_hs256("garbage", "s")

    def test_remote_verification_and_cache(self):
        auth_tokens._cache.clear(); old = config.SUPABASE_URL; config.SUPABASE_URL = "https://x.supabase.co"
        calls = []
        def fetch(url, headers): calls.append(url); return 200, {"id": "u-9", "email": "z@z.z"}
        try:
            self.assertEqual(auth_tokens.verify_remote("tok", fetch).id, "u-9")
            auth_tokens.verify_remote("tok", fetch); self.assertEqual(len(calls), 1)
            with self.assertRaises(auth_tokens.AuthError): auth_tokens.verify_remote("bad", lambda u, h: (401, {}))
        finally: config.SUPABASE_URL = old; auth_tokens._cache.clear()


class RankingTests(unittest.TestCase):
    def test_each_selected_paper_keeps_best_chunk_and_is_ordered(self):
        ranked = [(1, 10, .9), (2, 10, .8), (3, 10, .7), (4, 20, .2)]
        out = pick(ranked, [10, 20], 3)          # paper 20 is weak but must not be crowded out
        self.assertEqual(out, [1, 2, 4])

    def test_many_papers_plain_topk(self):
        ranked = [(i, i, 1 - i / 100) for i in range(20)]
        self.assertEqual(pick(ranked, list(range(20)), 4), [0, 1, 2, 3])

    def test_never_returns_chunks_outside_given_papers(self):
        ranked = [(1, 10, .9), (2, 20, .8)]
        self.assertTrue(set(pick([r for r in ranked if r[1] in [10]], [10], 6)) <= {1})


if __name__ == "__main__":
    unittest.main()
