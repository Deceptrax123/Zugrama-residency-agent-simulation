from concurrent.futures import ThreadPoolExecutor
from http.cookiejar import CookieJar
import json
import unittest
import urllib.error
import urllib.request

from residency.config import APP_ROOT
from tests.support import account, app, gateway, settings


class Client:
    def __init__(self, base):
        self.base = base
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()), urllib.request.ProxyHandler({}))
        self.csrf = ""

    def request(self, path, method="GET", payload=None, headers=None):
        request = urllib.request.Request(self.base + path, method=method,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json", "X-CSRF-Token": self.csrf, **(headers or {})})
        try:
            response = self.opener.open(request, timeout=100)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read()
            body = json.loads(raw) if response.headers.get_content_type() == "application/json" and raw else raw
            return response.status, body, response.headers

    def join(self, email="ada@example.test", name="Ada"):
        status, body, _ = self.request("/api/join", "POST", account(email, name))
        if status != 201:
            raise AssertionError(body)
        self.csrf = body["csrf"]
        return self.request("/api/state")[1]["me"]["id"]


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        (APP_ROOT / ".data").mkdir(exist_ok=True)
        self.gateway_context = gateway()
        self.gateway = self.gateway_context.__enter__()
        self.addCleanup(self.gateway_context.__exit__, None, None, None)
        self.config_context = settings(hermes_url=self.gateway.url, hermes_key="integration-key")
        self.config = self.config_context.__enter__()
        self.addCleanup(self.config_context.__exit__, None, None, None)
        self.app_context = app(self.config)
        self.server = self.app_context.__enter__()
        self.addCleanup(self.app_context.__exit__, None, None, None)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.ada = Client(self.base)
        self.bob = Client(self.base)
        self.eve = Client(self.base)

    def test_assets_health_and_unauthed_access(self):
        for path, expected in (("/", b"Commonroom"), ("/app.js", b"/api/assistant"), ("/styles.css", b".shell")):
            status, body, headers = self.ada.request(path)
            self.assertEqual(status, 200)
            self.assertIn(expected, body)
            self.assertIn("connect-src 'self'", headers["Content-Security-Policy"])
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.ada.request("/healthz")[1]["status"], "ok")
        self.assertEqual(self.ada.request("/api/state")[0], 401)
        self.assertEqual(self.ada.request("/api/hermes/status")[0], 401)
        self.assertEqual(self.ada.request("/../residency.sqlite3")[0], 401)
        self.assertEqual(self.ada.request("/", "HEAD")[1], b"")

    def test_local_memory_two_hop_privacy_controls_and_zero_provider_calls(self):
        ada = self.ada.join()
        bob = self.bob.join('bob@example.test', 'Bob')
        eve = self.eve.join('eve@example.test', 'Eve')
        self.ada.request('/api/messages', 'POST', {'recipient_id': bob, 'body': 'Private-original-546 never relayed.'})
        self.bob.request('/api/messages', 'POST', {'recipient_id': eve, 'body': 'Ada suggested a rainwater prototype for the village.'})
        self.assertEqual(self.eve.request('/api/memory/policy', 'PATCH', {'topics': ['rainwater']})[0], 200)
        status, job, _ = self.eve.request('/api/memory/extract', 'POST', {})
        self.assertEqual(status, 200)
        self.assertEqual(job['stored_units'], 1)
        view = self.eve.request('/api/memory?q=rainwater&peer=' + ada)[1]
        note = view['results'][0]
        self.assertEqual(note['path'], [ada, bob, eve])
        self.assertEqual(note['kind'], 'relayed_claim')
        self.assertNotIn('Private-original-546', json.dumps(view))
        self.assertNotIn('Private-original-546', json.dumps(self.eve.request('/api/memory/sources')[1]))
        route = '/api/memory/notes/' + note['id']
        self.assertEqual(self.ada.request(route, 'PATCH', {'pinned': True})[0], 404)
        self.assertEqual(self.eve.request(route, 'PATCH', {'pinned': True})[0], 200)
        self.assertEqual(self.eve.request(route, 'PATCH', {'hidden': True})[0], 200)
        self.assertEqual(self.eve.request('/api/memory')[1]['units'], [])
        self.assertEqual(self.gateway.records, [])
        self.assertEqual(self.eve.request('/api/memory/policy', 'PATCH', {}, {'X-CSRF-Token': 'bad'})[0], 403)
        # Existing Hermes chat must not silently acquire local private memories.
        self.eve.request('/api/assistant', 'POST', {'message': 'Hello there'})
        self.assertNotIn('rainwater prototype', json.dumps(self.gateway.records[-1]['payload']))

    def test_public_intro_joined_conversation_privacy_and_automatic_local_memory(self):
        ada = self.ada.join()
        bob = self.bob.join('bob@example.test','Bob')
        self.eve.join('eve@example.test','Eve')
        status, _, _ = self.ada.request('/api/introductions','POST',{'body':'I enjoy mathematical ideas and music.'})
        self.assertEqual(status,201)
        self.assertEqual(len(self.eve.request('/api/state')[1]['introductions']),1)
        self.assertIn('music',json.dumps(self.eve.request('/api/memory')[1]['units']))
        self.assertEqual(self.ada.request('/api/introductions','POST',{'body':'Replacement intro'})[0],409)
        status, result, _ = self.ada.request('/api/conversations/actions','POST',{
            'start_conversations':[{'with':bob,'body':'PREJOIN-PRIVATE-112 original statement.'}]})
        self.assertEqual(status,201)
        room = result['created_conversations'][0]
        self.assertNotIn('PREJOIN-PRIVATE-112',json.dumps(self.eve.request('/api/state')[1]))
        self.assertEqual(self.eve.request('/api/conversations/actions','POST',{
            'messages':[{'conversation_id':room,'body':'Not yet a participant.'}]})[0],403)
        self.assertEqual(self.eve.request('/api/conversations/actions','POST',{'join_conversations':[room]})[0],201)
        self.bob.request('/api/conversations/actions','POST',{'messages':[
            {'conversation_id':room,'body':'Ada suggested a rainwater prototype for the village.'}]})
        state = self.eve.request('/api/state')[1]
        self.assertEqual(len(state['conversation_messages']),1)
        relay = next(n for n in state['memory']['units'] if n['kind']=='relayed_claim')
        self.assertEqual(relay['path'][:2],[ada,bob])
        self.assertNotIn('PREJOIN-PRIVATE-112',json.dumps(self.eve.request('/api/memory/sources')[1]))
        self.eve.request('/api/conversations/actions','POST',{'leave_conversations':[room]})
        self.ada.request('/api/conversations/actions','POST',{'messages':[{'conversation_id':room,'body':'GAP-PRIVATE-113 withheld statement.'}]})
        self.eve.request('/api/conversations/actions','POST',{'join_conversations':[room]})
        self.assertNotIn('GAP-PRIVATE-113',json.dumps(self.eve.request('/api/state')[1]))
        self.assertEqual(self.gateway.records,[])
        self.eve.request('/api/assistant','POST',{'message':'Hello.'})
        self.assertNotIn('rainwater prototype',json.dumps(self.gateway.records[-1]['payload']))

    def test_manual_memory_and_opt_in_local_automatic_batches(self):
        self.ada.join()
        bob = self.bob.join('bob@example.test', 'Bob')
        self.ada.request('/api/memory/policy', 'PATCH', {'auto_extract': True, 'auto_after': 1})
        self.ada.request('/api/messages', 'POST', {'recipient_id': bob, 'body': 'I enjoy collaborative music improvisation.'})
        view = self.ada.request('/api/memory')[1]
        self.assertEqual(view['last_job']['status'], 'completed')
        source = self.ada.request('/api/memory/sources')[1]['sources'][0]
        status, _, _ = self.ada.request('/api/memory/notes', 'POST', {
            'source_key': source['key'], 'quote': source['body'], 'summary': 'Music is a shared interest.', 'category': 'interests'})
        self.assertEqual(status, 201)
        self.assertEqual(len(self.ada.request('/api/memory')[1]['units']), 2)
        self.assertEqual(self.bob.request('/api/memory')[1]['units'], [])
        self.assertEqual(self.gateway.records, [])

    def test_host_event_requires_host_and_csrf_and_runs_only_when_started(self):
        from residency.event import HostEvent
        ada=self.ada.join()
        bob=self.bob.join('bob@example.test','Bob')
        eve=self.eve.join('eve@example.test','Eve')
        for member in (ada,bob,eve): self.server.store.introduce(member,{'body':'I enjoy interesting ideas and music.'})
        self.server.event=HostEvent(self.server,ada,{p:{'name':p} for p in (ada,bob,eve)},self.config.data_dir/'event')
        self.assertEqual(self.ada.request('/api/event')[1]['status'],'idle')
        self.assertEqual(self.gateway.records,[])
        self.assertFalse(self.bob.request('/api/state')[1]['event']['can_control'])
        self.assertEqual(self.bob.request('/api/event/start','POST',{'max_calls':1})[0],403)
        self.assertEqual(self.ada.request('/api/event/start','POST',{'max_calls':1},{'X-CSRF-Token':'wrong'})[0],403)
        self.gateway.reply=json.dumps({'wait_seconds':0,'start_conversations':[],'join_conversations':[],'messages':[],'leave_conversations':[]})
        self.assertEqual(self.ada.request('/api/event/start','POST',{'max_calls':1})[0],200)
        for thread in self.server.event.threads: thread.join(3)
        self.assertEqual(self.ada.request('/api/event')[1]['status'],'completed')
        self.assertEqual(len(self.gateway.records),1)
        self.assertIn('room_prompt',self.gateway.records[0]['payload']['messages'][1]['content'])

    def test_end_to_end_join_profiles_network_problem_and_hermes(self):
        ada_id = self.ada.join()
        bob_id = self.bob.join("bob@example.test", "Bob")
        self.eve.join("eve@example.test", "Eve")
        status, _, headers = self.ada.request("/api/login", "POST", account())
        self.assertEqual(status, 200)
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        self.ada.csrf = self.ada.request("/api/state")[1]["csrf"]
        self.assertEqual(self.ada.request("/api/profile", "PATCH", dict(name="Ada", bio="Working on robotics", seeking="Controls", offering="Statistics"))[0], 200)
        status, problem, _ = self.ada.request("/api/problems", "POST", dict(title="A control problem", body="How can I test my hypothesis?"))
        self.assertEqual(status, 201)
        path = f"/api/problems/{problem['id']}"
        self.assertEqual(self.bob.request(path + "/comments", "POST", dict(body="Compare with a baseline."))[0], 201)
        self.assertEqual(self.bob.request(path, "PATCH", dict(status="solved"))[0], 403)
        self.assertEqual(self.ada.request(path, "PATCH", dict(status="solved"))[0], 200)
        self.assertEqual(self.ada.request("/api/messages", "POST", dict(recipient_id=bob_id, body="Private hello"))[0], 201)
        bob_state = self.bob.request("/api/state")[1]
        self.assertEqual(bob_state["messages"][0]["sender_id"], ada_id)
        self.assertEqual(self.eve.request("/api/state")[1]["messages"], [])
        status, reply, _ = self.ada.request("/api/assistant", "POST", dict(message="Who could help me?"))
        self.assertEqual(status, 200)
        self.assertIn("Talk with another", reply["reply"])
        self.assertEqual(len(self.gateway.records), 1)
        ada_state = self.ada.request("/api/state")[1]
        self.assertEqual(ada_state["assistant_turns"][0]["status"], "completed")
        self.assertEqual(self.bob.request("/api/state")[1]["assistant_turns"], [])
        self.assertEqual(self.ada.request("/api/hermes/status")[1]["status"], "ready")

    def test_csrf_and_origin_and_host_checks(self):
        self.ada.join()
        for headers in ({"X-CSRF-Token": "wrong"}, {"Origin": "https://attacker.example"},
                        {"Host": "attacker.example"}, {"Sec-Fetch-Site": "cross-site"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.ada.request("/api/problems", "POST", dict(title="x", body="y"), headers)[0], 403)
        self.assertEqual(self.ada.request("/api/state", headers={"Host":"attacker.example"})[0],403)

    def test_residents_iterate_on_code_and_pseudocode_in_any_domain(self):
        self.ada.join()
        bob_id = self.bob.join("bob@example.test", "Bob")
        original = 'A music practice helper.\n\n```python\ndef choose_song(songs):\n    return songs[0]\n```'
        revised = 'Consider an empty library:\n\n```text\nIF songs is empty\n    RETURN no_selection\nELSE\n    RETURN first_song\n```'
        status, problem, _ = self.ada.request('/api/problems', 'POST', {'title':'Music practice helper', 'body':original})
        self.assertEqual(status,201)
        status, comment, _ = self.bob.request(f"/api/problems/{problem['id']}/comments", 'POST', {'body':revised})
        self.assertEqual(status,201)
        self.assertEqual(comment['member_id'],bob_id)
        state = self.ada.request('/api/state')[1]
        self.assertEqual(state['problems'][0]['body'],original)
        self.assertEqual(state['comments'][0]['body'],revised)
        status, _, _ = self.ada.request('/api/assistant','POST',{'message':'Review the draft and suggest code.'})
        self.assertEqual(status,200)
        system = self.gateway.records[-1]['payload']['messages'][0]['content']
        self.assertIn(original, system.replace('\\n','\n'))
        self.assertIn('in any domain',system)
        self.assertIn('Drafting and reviewing this work are valid activities',system)
        self.assertIn('only claim those outcomes when supported by actual results',system)

    def test_invalid_content_type_json_shape_size_and_routes(self):
        self.ada.join()
        self.assertEqual(self.ada.request("/api/messages", "POST", {}, {"Content-Type":"text/plain"})[0], 415)
        self.assertEqual(self.ada.request("/api/messages", "POST", [1,2])[0], 400)
        self.assertEqual(self.ada.request("/api/messages", "POST", {"body":"x"*70000})[0], 413)
        self.assertEqual(self.ada.request("/api/unknown")[0], 404)
        self.assertEqual(self.ada.request("/api/state", "DELETE")[0], 405)

    def test_logout_revokes_session_and_login_recovers_saved_work(self):
        self.ada.join()
        self.ada.request("/api/problems", "POST", dict(title="Saved problem", body="Persistent"))
        self.assertEqual(self.ada.request("/api/logout", "POST", {})[0], 200)
        self.assertEqual(self.ada.request("/api/state")[0], 401)
        status, data, _ = self.ada.request("/api/login", "POST", account())
        self.assertEqual(status, 200)
        self.ada.csrf = data["csrf"]
        self.assertEqual(self.ada.request("/api/state")[1]["problems"][0]["title"], "Saved problem")

    def test_hermes_failure_is_visible_and_human_collaboration_still_works(self):
        self.ada.join()
        self.gateway.failure = 503
        self.assertEqual(self.ada.request("/api/assistant", "POST", dict(message="Help"))[0], 502)
        state = self.ada.request("/api/state")[1]
        self.assertEqual(state["assistant_turns"][0]["status"], "failed")
        self.assertNotIn("secret-upstream-diagnostic", json.dumps(state))
        self.assertEqual(self.ada.request("/api/problems", "POST", dict(title="Still works", body="Hello"))[0],201)

    def test_concurrent_turns_serialized_per_member_while_other_member_can_work(self):
        self.ada.join()
        self.bob.join("bob@example.test", "Bob")
        self.gateway.block = True
        with ThreadPoolExecutor(2) as executor:
            work = executor.submit(self.ada.request, "/api/assistant", "POST", dict(message="Help me"))
            self.assertTrue(self.gateway.entered.wait(3))
            try:
                self.assertEqual(self.ada.request("/api/assistant", "POST", dict(message="Duplicate"))[0],409)
                self.assertEqual(self.bob.request("/api/problems", "POST", dict(title="Independent", body="Working"))[0],201)
            finally:
                self.gateway.release.set()
            self.assertEqual(work.result()[0],200)
        self.assertEqual(len(self.gateway.records),1)

    def test_two_members_have_distinct_hermes_session_identifiers(self):
        self.ada.join()
        self.bob.join("bob@example.test", "Bob")
        self.ada.request("/api/assistant", "POST", dict(message="ada-private"))
        self.bob.request("/api/assistant", "POST", dict(message="bob-private"))
        headers = [{k.lower():v for k,v in record["headers"].items()} for record in self.gateway.records]
        self.assertNotEqual(headers[0]["x-hermes-session-key"], headers[1]["x-hermes-session-key"])
        self.assertNotEqual(headers[0]["x-hermes-session-id"], headers[1]["x-hermes-session-id"])
        self.assertNotIn("ada-private", json.dumps(self.gateway.records[1]["payload"]))

    def test_second_process_cannot_open_same_data_directory(self):
        from residency.server import ResidencyServer
        with self.assertRaises(BlockingIOError):
            ResidencyServer(("127.0.0.1",0), self.config)

    def test_auth_rate_limit(self):
        for _ in range(12):
            self.assertEqual(self.ada.request("/api/login", "POST", {**account(), "password":"wrong"})[0],401)
        self.assertEqual(self.ada.request("/api/login", "POST", account())[0],429)


if __name__ == "__main__":
    unittest.main()
