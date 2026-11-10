import os
import sys
import time

from provider import Provider
from registry import Registry
from session import new_session_file, load_session, DEFAULT_SESSION_DIR
from budget import effective_context_window, estimate_tokens, check_budget, BUDGET_FRACTION
from compression import compact_keep_budget, compact
from subagent import dispatch_tool_calls, can_fan_out, MAX_PARALLEL_SUB_AGENTS


class Agent:
    """Reusable agent core loop.

    The boundary between framework and application: this only handles "session creation -> send ->
    budget check -> compression -> dispatch tool calls". The system prompt and the tool set are
    injected by the caller, so the base agent knows nothing about the specific domain.
    """

    def __init__(self, *, api_key, model, base_url, system_prompt, tools,
                 provider="deepseek", max_rounds=60, state_dir=DEFAULT_SESSION_DIR, work_dir=None,
                 stream=False):
        self.api_key = api_key
        self.model = model or None
        self.provider = provider
        self.base_url = base_url
        self.system_prompt = system_prompt
        self.max_rounds = max_rounds
        self.state_dir = state_dir
        self.work_dir = work_dir or os.getcwd()
        self.stream = stream
        self.reg = Registry(*tools)
        # run telemetry, filled in during `run` (used by persistence)
        self.turn_count = 0
        self.tool_call_count = 0
        self.compile_attempt_count = 0
        self.session_id = None
        self.session_path = None
        self.resolved_provider = None
        self.resolved_model = None

    def run(self, task, resume_id=""):
        """Run one agent session and return the process exit code (0 success, 1 error / max-rounds reached)."""
        if resume_id:
            try:
                sess = load_session(resume_id, session_dir=self.state_dir)
            except (OSError, ValueError) as e:
                print(f"Error: Failed to restore session: {e}", file=sys.stderr)
                return 1
            print(f"Resume session {sess.id}", file=sys.stderr)
        else:
            try:
                sess = new_session_file(
                    [{"role": "system", "content": self.system_prompt}],
                    session_dir=self.state_dir,
                )
            except OSError as e:
                print(f"Error: Failed to create session: {e}", file=sys.stderr)
                return 1
            print(f"Create session {sess.id}", file=sys.stderr)

        self.session_id = sess.id
        self.session_path = os.path.join(sess.session_dir, sess.id + ".jsonl")

        try:
            prov = Provider(self.provider, model=self.model, api_key=self.api_key)
            prov.base_url = (self.base_url or prov.base_url).rstrip("/")
            self.resolved_provider = prov.name
            self.resolved_model = prov.model
        except Exception as e:
            print(e, file=sys.stderr)
            return 1

        window = effective_context_window(prov.model)
        pre_estimate = estimate_tokens(sess.history)
        print(f"[Window: {prov.model} → {window} tokens (Estimate before first request: {pre_estimate} tokens)]", file=sys.stderr)
        if pre_estimate >= window * BUDGET_FRACTION:
            print("⚠️ Estimated restored history is approaching budget limit. Noting this before sending requests — the actual value will be known after the first round response.", file=sys.stderr)

        sess.history.append({"role": "user", "content": task})
        sess.save()

        for round_no in range(1, self.max_rounds + 1):
            self.turn_count += 1
            round_start = time.perf_counter()
            try:
                r = prov.send(sess.history, self.reg.definitions(), stream=self.stream)
            except Exception as e:
                print(e, file=sys.stderr)
                return 1
            print(f"[round {round_no} took {time.perf_counter() - round_start:.2f}s]", file=sys.stderr)

            choice = r["choices"][0]
            msg = choice["message"]
            sess.history.append(msg)
            sess.save()

            u = r.get("usage") or {}
            cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0)

            if check_budget(u.get("prompt_tokens", 0), window):
                trigger = int(window * BUDGET_FRACTION)
                keep_budget = compact_keep_budget(window, trigger)
                try:
                    rebuilt, folded = compact(prov, sess.history, keep_budget)
                except Exception as e:
                    print(f"Warning: Compression failed, continuing with uncompressed history: {e}", file=sys.stderr)
                else:
                    if folded > 0:
                        print(f"[Compression: folded the preceding {folded} messages into one summary, {len(sess.history)} entries → {len(rebuilt)} entries]", file=sys.stderr)
                        sess.history = rebuilt
                        sess.force_rewrite = True
                    else:
                        print("[Compression: Insufficient complete user messages for folding, skipping this round]", file=sys.stderr)

            if choice.get("finish_reason") != "tool_calls":
                if self.stream:
                    print(flush=True)  # the reply was already streamed; just close it with a newline
                else:
                    print(msg.get("content") or "", flush=True)
                print(f"\n[round {round_no}] · Last turn input {u.get('prompt_tokens', 0)} tokens, cached {cached} tokens"
                      f" · finish_reason={choice.get('finish_reason')}]", file=sys.stderr)
                return 0

            tool_calls = msg.get("tool_calls") or []
            self.tool_call_count += len(tool_calls)
            self.compile_attempt_count += sum(
                1 for tc in tool_calls if (tc.get("function") or {}).get("name") == "compile"
            )
            if can_fan_out(tool_calls):
                print(f"[round {round_no} fan-out: {len(tool_calls)} sub-agents, "
                      f"max {MAX_PARALLEL_SUB_AGENTS} slots]", file=sys.stderr)
            sess.history.extend(dispatch_tool_calls(self.reg, round_no, tool_calls))
            sess.save()

        print(f"Reached max round limit of {self.max_rounds}, stopped.", file=sys.stderr)
        return 1
