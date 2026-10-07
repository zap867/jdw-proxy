#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 abdurrehmandaudi
# Required Notice: Copyright (c) 2026 abdurrehmandaudi -- justdowork-proxy
# Licensed under the PolyForm Noncommercial License 1.0.0 -- commercial
# use is not permitted without a separate written commercial license.
# See LICENSE or https://polyformproject.org/licenses/noncommercial/1.0.0
"""
test_offline.py -- tests everything in ccproxy without a real API key.

How to run:
    /Users/abdurrehmandaudigmail.com/deepseek-proxy/.venv/bin/python3 test_offline.py

It uses the actual payloads that used to be DROPPED by the old proxy (taken from
debug_dump), and starts a mock upstream to check the whole
request -> tool_call -> response cycle.
"""
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ.setdefault("UPSTREAM_API_KEY", "sk-test-offline")
os.environ.setdefault("TARGET_URL", "http://127.0.0.1:8799")

import ccproxy  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"   {extra}" if extra else ""))


# --------------------------------------------------------------------------- #
# 1. JSON repair -- this was the multi-agent killer
# --------------------------------------------------------------------------- #
print("\n=== 1. JSON repair (the payloads that really failed) ===")

# (a) Agent: LITERAL NEWLINES in the prompt -> strict json.loads used to fail
agent_body = ('{"description": "Explore repo", "prompt": "Read these files:\n'
              '- a.py\n- b.py\n\nThen summarize the findings.", '
              '"subagent_type": "Explore"}')
obj = ccproxy.loads_tool_json(agent_body)
check("Agent payload (literal newlines) parsed",
      obj is not None and obj.get("subagent_type") == "Explore")
check("Agent prompt kept its newlines",
      obj is not None and "\n- a.py" in obj.get("prompt", ""))

# (b) Monitor: INVALID ESCAPES `\.` and `\]` -> this is what got dropped 3049 times
monitor_body = ('{"command": "until grep -qE \\"Installed\\. Open|warn\\]\\" '
                '/tmp/x.output 2>/dev/null; do sleep 1; done", "description": "wait"}')
obj = ccproxy.loads_tool_json(monitor_body)
check("Monitor payload (invalid escapes \\. and \\]) parsed", obj is not None)
check("Monitor regex survived (backslash still alive)",
      obj is not None and "Installed\\. Open" in obj.get("command", ""),
      repr(obj.get("command", "")[:60]) if obj else "")

# (c) trailing comma
check("Trailing comma fixed",
      ccproxy.loads_tool_json('{"a": 1, "b": [1,2,],}') == {"a": 1, "b": [1, 2]})

# (d) extra closing bracket
check("Extra closing bracket ignored",
      ccproxy.loads_tool_json('{"a": 1}}]') == {"a": 1})

# (e) missing closing brace
check("Missing closing brace added",
      ccproxy.loads_tool_json('{"a": {"b": 2}') == {"a": {"b": 2}})

# (f) VALID JSON must not be corrupted
good = '{"command": "grep -E \\"a\\\\.b\\" file", "n": 3, "flag": true}'
obj = ccproxy.loads_tool_json(good)
check("Valid JSON came back exactly as it was (no corruption)",
      obj == {"command": 'grep -E "a\\.b" file', "n": 3, "flag": True}, repr(obj))

# (g) Write tool: literal newlines plus code in the content
write_body = '{"file_path": "x.py", "content": "def f():\n    return 1\n\nprint(f())"}'
obj = ccproxy.loads_tool_json(write_body)
check("Write content (multi-line code) parsed",
      obj is not None and "def f():" in obj.get("content", ""))


# --------------------------------------------------------------------------- #
# 2. parse_assistant_text -- whole response -> blocks
# --------------------------------------------------------------------------- #
print("\n=== 2. Response parsing ===")

valid = {"Agent", "Monitor", "Bash", "WebSearch", "Read"}

# (a) one Agent call, with newlines
txt = "Launching the agent now.\n\n" + '<tool_call name="Agent">' + agent_body + "</tool_call>"
blocks = ccproxy.parse_assistant_text(txt, valid_names=valid, strict=True)
tools = [b for b in blocks if b["type"] == "tool_use"]
check("Agent tool_use block created (used to be dropped)",
      len(tools) == 1 and tools[0]["name"] == "Agent")
check("The text around the Agent call survived too",
      any(b["type"] == "text" and "Launching" in b["text"] for b in blocks))

# (b) parallel calls in one reply
txt2 = ('<tool_call name="WebSearch">{"query": "a"}</tool_call>\n'
        '<tool_call name="Monitor">' + monitor_body + "</tool_call>")
tools2 = [b for b in ccproxy.parse_assistant_text(txt2, valid, True) if b["type"] == "tool_use"]
check("Two parallel tool calls -> two blocks", len(tools2) == 2,
      str([t["name"] for t in tools2]))

# (c) works even when the closing tag is missing
txt3 = '<tool_call name="Read">{"file_path": "a.py"}'
tools3 = [b for b in ccproxy.parse_assistant_text(txt3, valid, True) if b["type"] == "tool_use"]
check("Works without a closing </tool_call>",
      len(tools3) == 1 and tools3[0]["input"] == {"file_path": "a.py"})

# (d) native XML <invoke><parameter>
txt4 = ('<invoke name="Bash"><parameter name="command">ls -la</parameter>'
        '<parameter name="description">list</parameter></invoke>')
tools4 = [b for b in ccproxy.parse_assistant_text(txt4, valid, True) if b["type"] == "tool_use"]
check("Native <invoke> XML form also parses",
      len(tools4) == 1 and tools4[0]["input"].get("command") == "ls -la")

# (e) a name outside the list produces no call (strict)
txt5 = '<tool_call name="SomethingElse">{"x": 1}</tool_call>'
tools5 = [b for b in ccproxy.parse_assistant_text(txt5, valid, True) if b["type"] == "tool_use"]
check("A name outside the list produces no tool_use (strict)", len(tools5) == 0)

# (f) plain text keeps working
blocks6 = ccproxy.parse_assistant_text("Just a normal answer.", valid, True)
check("Plain text passed through correctly",
      len(blocks6) == 1 and blocks6[0]["type"] == "text")


# --------------------------------------------------------------------------- #
# 2b. Tool results must survive the pipeline
#
# Regression: `_is_empty_content()` counted only `text` and `image` blocks as
# content. A `tool_result` block has no `text` field, so it looked empty and
# `normalize_alternating()` deleted the whole message. The model never saw what
# its tool returned, so it called the same tool again on every turn -- the
# "mkdir forever" loop. Every native Read/Write/Edit/Bash result was lost.
# --------------------------------------------------------------------------- #
print("\n=== 2b. Tool results survive to the payload ===")

check("A tool_result block is not 'empty'",
      not ccproxy._is_empty_content(
          [{"type": "tool_result", "tool_use_id": "t1", "content": "output"}]))

check("A tool_use block is not 'empty'",
      not ccproxy._is_empty_content(
          [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}]))

check("An empty tool_result is still kept (the model must see the tool ran)",
      not ccproxy._is_empty_content(
          [{"type": "tool_result", "tool_use_id": "t1", "content": ""}]))

check("A genuinely empty message is still dropped",
      ccproxy._is_empty_content([{"type": "text", "text": "   "}]))

_loop_req = {
    "model": "claude-opus-4-8",
    "messages": [
        {"role": "user", "content": "make a folder"},
        {"role": "assistant", "content": [
            {"type": "text", "text": "OK."},
            {"type": "tool_use", "id": "toolu_1", "name": "Bash",
             "input": {"command": "mkdir -p /tmp/x"}}]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_1",
             "content": "(folder created)"}]},
    ],
}
_loop_feats = dict(ccproxy.FEATS)
_loop_feats["tool_injection"] = False
_loop_payload = ccproxy.build_payload(_loop_req, _loop_feats)
_loop_msgs = _loop_payload["messages"]

check("The tool_result message reached the payload (3 msgs, not 2)",
      len(_loop_msgs) == 3, f"(got {len(_loop_msgs)})")
check("The tool_result block itself is in the last message",
      any(isinstance(b, dict) and b.get("type") == "tool_result"
          for b in (_loop_msgs[-1].get("content") or [])))
check("The assistant kept its native tool_use",
      any(isinstance(b, dict) and b.get("type") == "tool_use"
          and b.get("name") == "bash"
          for b in (_loop_msgs[1].get("content") or [])))


# --------------------------------------------------------------------------- #
# 3. History trimming -- 1.65MB -> a budget
# --------------------------------------------------------------------------- #
print("\n=== 3. Token saving (history trim) ===")

feats = dict(ccproxy.FEATS)
feats["max_history_chars"] = 200000
feats["max_tool_result_chars"] = 4000

# a synthetic 1300-message history (like the real dump)
big = [{"role": "user", "content": "Start working on the project."}]
for i in range(1300):
    big.append({"role": "assistant", "content": [
        {"type": "tool_use", "id": f"t{i}", "name": "Bash", "input": {"command": "ls"}}]})
    big.append({"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": f"t{i}",
         "content": "x" * 2000}]})

before = sum(ccproxy._msg_chars(m) for m in big)
trimmed = ccproxy.trim_history(big, feats)
after = sum(ccproxy._msg_chars(m) for m in trimmed)
check(f"1300-message history trimmed: {before} -> {after} chars",
      after < 200000 and after < before // 4,
      f"({after * 100 // before}% left)")
check("The first message is still from the user", trimmed[0]["role"] == "user")

_used = {x.get("id") for m in trimmed if isinstance(m.get("content"), list)
         for x in m["content"] if isinstance(x, dict) and x.get("type") == "tool_use"}
_orphans = [b for m in trimmed if isinstance(m.get("content"), list)
            for b in m["content"]
            if isinstance(b, dict) and b.get("type") == "tool_result"
            and b.get("tool_use_id") not in _used]
check("No orphaned tool_results after trimming", not _orphans,
      f"{len(_orphans)} orphans found" if _orphans else "")

# the full payload builds too
req = {"model": "claude-opus-4-8", "max_tokens": 64000, "stream": True,
       "system": [{"type": "text", "text": "You are Claude Code." * 200}],
       "tools": [{"name": "Agent", "description": "Launch agent\n\nLong text " * 40,
                  "input_schema": {"type": "object", "properties": {
                      "description": {"type": "string"}, "prompt": {"type": "string"}},
                      "required": ["description", "prompt"]}}],
       "messages": big}
pl = ccproxy.build_payload(req, feats)
pl.pop("_breakdown", None)
size = len(json.dumps(pl))
check(f"The whole payload became compact ({before + 40000} -> {size} chars)",
      size < 250000, f"{size} chars (~{size // 4} tokens)")
check("A cache breakpoint was set on the system block",
      isinstance(pl.get("system"), list) and pl["system"][0].get("cache_control") is not None)
check("The short tool description was used in compact mode",
      "Launch agent" in pl["system"][0]["text"] and "Long text Long text" not in pl["system"][0]["text"])

# Native tools have to travel in the `tools` array. Without this the relay never
# offers them, and Read/Write/Edit/Bash silently stop working.
req_native = {"model": "claude-opus-4-8", "max_tokens": 4096, "stream": False,
              "system": "You are Claude Code.",
              "tools": [
                  {"name": "Read", "description": "Read a file.",
                   "input_schema": {"type": "object",
                                    "properties": {"file_path": {"type": "string"}},
                                    "required": ["file_path"]}},
                  {"name": "Write", "description": "Write a file.",
                   "input_schema": {"type": "object",
                                    "properties": {"file_path": {"type": "string"},
                                                   "content": {"type": "string"}},
                                    "required": ["file_path", "content"]}},
                  {"name": "Agent", "description": "Launch agent", "input_schema":
                   {"type": "object", "properties": {"prompt": {"type": "string"}}}}],
              "messages": [{"role": "user", "content": "hi"}]}
pl2 = ccproxy.build_payload(req_native, feats)
_sent = sorted(t["name"] for t in (pl2.get("tools") or []))
check("Read/Write are sent as native tools in the payload",
      _sent == ["read", "write"], str(_sent))
check("Agent is NOT sent natively (it goes through <tool_call>)",
      "agent" not in _sent, str(_sent))
check("The native schema rode along (the relay needs the parameters)",
      any((t.get("input_schema") or {}).get("properties", {}).get("file_path")
          for t in (pl2.get("tools") or [])))
_sys2 = pl2["system"][0]["text"] if isinstance(pl2.get("system"), list) else (pl2.get("system") or "")
check("The prompt names the native lowercase tools",
      "`read`" in _sys2 and "`write`" in _sys2)
check("The prompt tells the model to ignore the relay's fake tool names",
      "read_tabular" in _sys2 and "system_todo_write" in _sys2)
check("Agent is still described through <tool_call>", "`Agent`" in _sys2)
check("A forced tool_choice is mapped to the native name",
      (ccproxy.build_payload(dict(req_native, tool_choice={"type": "tool", "name": "Read"}),
                             feats).get("tool_choice") or {}).get("name") == "read")


# --------------------------------------------------------------------------- #
# 4. Full integration -- against a mock upstream
# --------------------------------------------------------------------------- #
print("\n=== 4. Integration (mock upstream) ===")

from flask import Flask, Response, request as freq  # noqa: E402

mock = Flask("mock-upstream")
MOCK = {"calls": [], "script": []}


@mock.route("/v1/messages", methods=["POST"])
def mock_messages():
    body = freq.get_json(force=True)
    MOCK["calls"].append(body)
    MOCK.setdefault("headers", []).append(dict(freq.headers))
    idx = len(MOCK["calls"]) - 1
    script = MOCK["script"]
    text = script[idx] if idx < len(script) else "done"
    return Response(json.dumps({
        "id": f"msg_mock{idx}", "type": "message", "role": "assistant",
        "model": body.get("model"), "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 12345, "output_tokens": 42}}),
        content_type="application/json")


threading.Thread(target=lambda: mock.run(port=8799, threaded=True, debug=False),
                 daemon=True).start()
threading.Thread(target=lambda: ccproxy.app.run(port=8798, threaded=True, debug=False),
                 daemon=True).start()
time.sleep(2.0)

import requests  # noqa: E402

PROXY = "http://127.0.0.1:8798/v1/messages"


def pcall(payload):
    return requests.post(PROXY, json=payload, timeout=120)


base_req = {"model": "claude-opus-4-8", "max_tokens": 4096, "stream": False,
            "system": "You are Claude Code.",
            "tools": [{"name": "Bash", "description": "run", "input_schema":
                       {"type": "object", "properties": {"command": {"type": "string"}}}},
                      {"name": "Agent", "description": "launch", "input_schema":
                       {"type": "object", "properties": {"prompt": {"type": "string"}}}}],
            "messages": [{"role": "user", "content": "hello"}]}

# (a) a normal request
MOCK["calls"].clear()
MOCK["script"] = []
r = pcall(dict(base_req))
check("Non-stream request returned 200 OK", r.status_code == 200, r.text[:150])

_sent_tools = [t.get("name") for t in (MOCK["calls"][0].get("tools") or [])]
check("The upstream call carried the native `bash` tool",
      _sent_tools == ["bash"], str(_sent_tools))

# (b) the Agent call made it through (this used to be dropped)
MOCK["calls"].clear()
MOCK["script"] = ["Sending the agent now.\n\n" + '<tool_call name="Agent">' + agent_body + "</tool_call>"]
r = pcall(dict(base_req))
j = r.json()
tus = [b for b in j.get("content", []) if b.get("type") == "tool_use"]
check("Agent tool_use reached the client", len(tus) == 1 and tus[0]["name"] == "Agent")
check("stop_reason = tool_use", j.get("stop_reason") == "tool_use")
check("The Agent prompt is complete (newlines intact)",
      len(tus) == 1 and "\n- a.py" in tus[0]["input"].get("prompt", ""))

# (c) WebSearch is run by the proxy itself (network call monkeypatched)
called = {}
orig_search = ccproxy.run_web_search


def fake_search(q, f):
    called["q"] = q
    return "Web search results for: %s\n1. Example\n   https://example.com\n   snippet" % q


ccproxy.run_web_search = fake_search
MOCK["calls"].clear()
MOCK["script"] = ['<tool_call name="WebSearch">{"query": "flutter build error"}</tool_call>',
                  "According to the search, this error comes from X."]
r = pcall(dict(base_req))
j = r.json()
check("The proxy ran WebSearch itself", called.get("q") == "flutter build error")
check("The client only saw the final answer (no tool_use)",
      not any(b.get("type") == "tool_use" for b in j.get("content", [])))
check("The final answer came after the search",
      "comes from X" in json.dumps(j.get("content", [])), json.dumps(j.get("content"))[:120])
check("The search results were sent back to the model (2 upstream calls)",
      len(MOCK["calls"]) == 2 and "Web search results" in
      json.dumps(MOCK["calls"][1].get("messages", []))[:100000])
ccproxy.run_web_search = orig_search

# (d) streaming
MOCK["calls"].clear()
MOCK["script"] = ["The streaming answer is fine."]
r = requests.post(PROXY, json=dict(base_req, stream=True), timeout=120)
body = r.text
check("SSE stream returned 200 OK", r.status_code == 200)
check("message_start received", "event: message_start" in body)
check("message_start carried real input_tokens (for 9Router)", '"input_tokens": 12345' in body)
check("ping received (no dead air)", "event: ping" in body)
check("text_delta received", "text_delta" in body and "streaming answer" in body)
check("message_delta carried output_tokens", '"output_tokens": 42' in body)
check("message_stop received", "event: message_stop" in body)

# (e) count_tokens
r = requests.post("http://127.0.0.1:8798/v1/messages/count_tokens",
                  json={"messages": [{"role": "user", "content": "x" * 400}]}, timeout=30)
check("count_tokens endpoint works (used to be 404)",
      r.status_code == 200 and r.json().get("input_tokens", 0) > 50)

# (f) health
r = requests.get("http://127.0.0.1:8798/health", timeout=30)
check("/health OK", r.status_code == 200 and r.json().get("ok"))


# --------------------------------------------------------------------------- #
# 5. Dashboard (served at /)
# --------------------------------------------------------------------------- #
print("\n=== 5. Dashboard ===")

check("dashboard.py loaded (not the fallback page)",
      bool(getattr(ccproxy, "DASHBOARD_HTML", None)))

r = requests.get("http://127.0.0.1:8798/", timeout=30)
check("/ returns HTML", r.status_code == 200 and "text/html" in r.headers.get("content-type", ""))
check("The page mentions ccproxy and /stats.json",
      "ccproxy" in r.text and "/stats.json" in r.text)

r = requests.get("http://127.0.0.1:8798/stats.json", timeout=30)
check("/stats.json returned 200 OK", r.status_code == 200, r.text[:120])
st = r.json() if r.status_code == 200 else {}
for key in ("total_reqs", "ok", "fail", "in_tok", "out_tok", "duration",
            "server_tools", "tool_uses", "disk", "recent", "errors",
            "saved_tok", "sent_tok", "raw_hist_tok", "raw_tools_tok",
            "max_history_chars", "max_tool_result_chars"):
    if key not in st:
        check(f"stats contains '{key}'", False)
        break
else:
    check("stats contains every required field", True)

check("Requests were counted (total_reqs > 0)", st.get("total_reqs", 0) > 0,
      f"total={st.get('total_reqs')}")
check("The recent list is not empty", len(st.get("recent") or []) > 0)
check("The Agent tool_use was counted", (st.get("tool_uses") or {}).get("Agent", 0) > 0,
      str(st.get("tool_uses")))
check("The WebSearch server tool was counted",
      sum((st.get("server_tools") or {}).values()) > 0, str(st.get("server_tools")))
check("Disk accounting is present", "log_bytes" in (st.get("disk") or {}))
_avg = st.get("duration", 0) / max(1, st.get("total_reqs", 1))
check(f"Average latency was computed ({round(_avg, 2)}s)", _avg >= 0)

r = requests.post("http://127.0.0.1:8798/stats/reset", timeout=30)
check("/stats/reset worked", r.status_code == 200 and r.json().get("ok"))
st2 = requests.get("http://127.0.0.1:8798/stats.json", timeout=30).json()
check("Counters are zero after reset", st2.get("total_reqs") == 0 and not st2.get("recent"))

# the "avoided by trimming" counter has to actually move on a big history
_before_saved = st2.get("saved_tok", 0)
bigmsgs = [{"role": "user", "content": "Start."}]
for i in range(300):
    bigmsgs.append({"role": "assistant", "content": [
        {"type": "tool_use", "id": f"b{i}", "name": "Bash", "input": {"command": "ls"}}]})
    bigmsgs.append({"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": f"b{i}", "content": "y" * 3000}]})
_raw_chars = sum(ccproxy._msg_chars(m) for m in bigmsgs)

MOCK["calls"].clear()
MOCK["script"] = ["done"]
r = pcall(dict(base_req, messages=bigmsgs))
check("A big-history request still returned 200 OK", r.status_code == 200, r.text[:150])

_sent_chars = len(json.dumps(MOCK["calls"][0].get("messages", [])))
check(f"Upstream payload was much smaller than the client sent "
      f"({_raw_chars} -> {_sent_chars} chars)", _sent_chars < _raw_chars // 3)

st3 = requests.get("http://127.0.0.1:8798/stats.json", timeout=30).json()
check("saved_tok counted the tokens avoided by trimming",
      st3.get("saved_tok", 0) > _before_saved,
      f"saved={st3.get('saved_tok')} tokens")
check("sent_tok shows what was actually sent",
      st3.get("sent_tok", 0) > 0, f"sent={st3.get('sent_tok')} tokens")
_last = (st3.get("recent") or [{}])[0]
check("The per-request row compares kept vs offered history",
      _last.get("raw_hist_tok", 0) > _last.get("hist_tok", 0),
      f"kept={_last.get('hist_tok')} of offered={_last.get('raw_hist_tok')}")

# --------------------------------------------------------------------------- #
# 6. Dynamic Key & 9Router Pass-through
# --------------------------------------------------------------------------- #
print("\n=== 6. Dynamic Key & 9Router Pass-through ===")

MOCK["calls"].clear()
MOCK.setdefault("headers", []).clear()
MOCK["script"] = ["dynamic-alice"]

# (a) Pass key via x-api-key
r_alice = requests.post(
    "http://127.0.0.1:8798/v1/messages",
    json=dict(base_req),
    headers={"x-api-key": "sk-jdw-key-alice"},
    timeout=30
)
check("Request with dynamic x-api-key returned 200 OK", r_alice.status_code == 200)
last_h = MOCK["headers"][-1] if MOCK.get("headers") else {}
check("Upstream received forwarded x-api-key: sk-jdw-key-alice",
      last_h.get("X-Api-Key") == "sk-jdw-key-alice" or last_h.get("x-api-key") == "sk-jdw-key-alice",
      str(last_h.get("x-api-key") or last_h.get("X-Api-Key")))
check("Upstream received Bearer token matching x-api-key",
      "Bearer sk-jdw-key-alice" in (last_h.get("Authorization") or ""))

# (b) Pass key via Authorization: Bearer
MOCK["script"] = ["dynamic-bob"]
r_bob = requests.post(
    "http://127.0.0.1:8798/v1/messages",
    json=dict(base_req),
    headers={"Authorization": "Bearer sk-jdw-key-bob"},
    timeout=30
)
check("Request with dynamic Bearer token returned 200 OK", r_bob.status_code == 200)
last_h = MOCK["headers"][-1] if MOCK.get("headers") else {}
check("Upstream received forwarded key from Bearer auth: sk-jdw-key-bob",
      last_h.get("X-Api-Key") == "sk-jdw-key-bob" or last_h.get("x-api-key") == "sk-jdw-key-bob")

# (c) Flexible route without /v1 prefix (/messages)
MOCK["script"] = ["no-v1-prefix"]
r_nov1 = requests.post(
    "http://127.0.0.1:8798/messages",
    json=dict(base_req),
    headers={"x-api-key": "sk-jdw-flexible"},
    timeout=30
)
check("Request to /messages (without /v1) returned 200 OK", r_nov1.status_code == 200)

# (d) Forward anthropic-beta header
MOCK["script"] = ["beta-forwarding"]
r_beta = requests.post(
    "http://127.0.0.1:8798/v1/messages",
    json=dict(base_req),
    headers={"x-api-key": "sk-jdw-beta", "anthropic-beta": "prompt-caching-2024-07-25"},
    timeout=30
)
check("Request with anthropic-beta returned 200 OK", r_beta.status_code == 200)
last_h = MOCK["headers"][-1] if MOCK.get("headers") else {}
check("Upstream received forwarded anthropic-beta header",
      (last_h.get("Anthropic-Beta") or last_h.get("anthropic-beta")) == "prompt-caching-2024-07-25")

# (e) Health checks
r_h1 = requests.get("http://127.0.0.1:8798/health", timeout=30).json()
r_h2 = requests.get("http://127.0.0.1:8798/v1/health", timeout=30).json()
check("/health and /v1/health report dynamic_key_enabled",
      r_h1.get("dynamic_key_enabled") is True and r_h2.get("dynamic_key_enabled") is True)

# --------------------------------------------------------------------------- #
print("\n" + "=" * 60)
print(f"RESULT:  {len(PASS)} pass, {len(FAIL)} fail")
if FAIL:
    print("Failed:")
    for f in FAIL:
        print("   -", f)
print("=" * 60)
sys.exit(1 if FAIL else 0)
