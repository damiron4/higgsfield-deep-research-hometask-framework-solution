"""Generates a self-contained HTML trace viewer for a run.

One HTML file per run. Inline CSS + vanilla JS only (no frameworks, no CDN).
A human should find the failing step in under 30 seconds.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval.models import CaseResult, RunReport

_REPORTS_DIR = Path(__file__).parent.parent / "reports"


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Eval Run {run_id_short}</title>
<style>
  :root {{
    --pass: #22c55e; --fail: #ef4444; --warn: #f59e0b;
    --bg: #0f172a; --surface: #1e293b; --border: #334155;
    --text: #e2e8f0; --muted: #94a3b8; --code-bg: #0d1117;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; font-size: 14px; }}
  header {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: 16px 24px; position: sticky; top: 0; z-index: 10; }}
  header h1 {{ font-size: 18px; font-weight: 600; }}
  header .meta {{ color: var(--muted); font-size: 12px; margin-top: 4px; }}
  .regression-banner {{ background: #450a0a; border: 1px solid var(--fail); border-radius: 6px; color: #fca5a5; margin: 16px 24px; padding: 12px 16px; }}
  .improvement-banner {{ background: #052e16; border: 1px solid var(--pass); border-radius: 6px; color: #86efac; margin: 16px 24px; padding: 12px 16px; }}
  .stats-bar {{ display: flex; gap: 24px; padding: 16px 24px; background: var(--surface); border-bottom: 1px solid var(--border); flex-wrap: wrap; }}
  .stat {{ display: flex; flex-direction: column; gap: 2px; }}
  .stat-label {{ font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; }}
  .stat-value {{ font-size: 20px; font-weight: 700; }}
  .pass-rate {{ color: var(--pass); }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
  .case-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 16px; overflow: hidden; }}
  .case-header {{ display: flex; align-items: center; gap: 12px; padding: 14px 16px; cursor: pointer; user-select: none; }}
  .case-header:hover {{ background: #263348; }}
  .badge {{ border-radius: 4px; font-size: 11px; font-weight: 700; padding: 2px 8px; text-transform: uppercase; letter-spacing: .05em; }}
  .badge-pass {{ background: #14532d; color: var(--pass); }}
  .badge-fail {{ background: #450a0a; color: var(--fail); }}
  .badge-flaky {{ background: #451a03; color: var(--warn); }}
  .case-id {{ font-weight: 600; flex: 1; }}
  .case-meta {{ color: var(--muted); font-size: 12px; }}
  .caret {{ color: var(--muted); transition: transform .2s; }}
  .case-body {{ border-top: 1px solid var(--border); display: none; }}
  .case-body.open {{ display: block; }}
  .section {{ padding: 16px; border-bottom: 1px solid var(--border); }}
  .section:last-child {{ border-bottom: none; }}
  .section-title {{ color: var(--muted); font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .07em; margin-bottom: 10px; }}
  .question {{ color: #93c5fd; font-style: italic; }}
  .answer {{ background: var(--code-bg); border-radius: 6px; padding: 12px; line-height: 1.6; }}
  .assertions-list {{ display: flex; flex-direction: column; gap: 6px; }}
  .assertion {{ display: flex; align-items: flex-start; gap: 8px; padding: 8px 10px; border-radius: 6px; }}
  .assertion-pass {{ background: #052e16; }}
  .assertion-fail {{ background: #450a0a; }}
  .assertion-icon {{ font-size: 14px; line-height: 1.4; flex-shrink: 0; }}
  .assertion-type {{ font-weight: 600; margin-right: 6px; }}
  .assertion-reason {{ color: var(--muted); font-size: 13px; }}
  .assertion-rationale {{ color: #fbbf24; font-size: 12px; margin-top: 4px; display: block; }}
  .timeline {{ display: flex; flex-direction: column; gap: 0; }}
  .msg {{ border-bottom: 1px solid var(--border); }}
  .msg:last-child {{ border-bottom: none; }}
  .msg-header {{ display: flex; align-items: center; gap: 10px; padding: 10px 14px; cursor: pointer; }}
  .msg-header:hover {{ background: #263348; }}
  .role-pill {{ border-radius: 4px; font-size: 10px; font-weight: 700; padding: 1px 7px; text-transform: uppercase; }}
  .role-system {{ background: #1e3a5f; color: #93c5fd; }}
  .role-user {{ background: #3b0764; color: #d8b4fe; }}
  .role-assistant {{ background: #1c3b1e; color: #86efac; }}
  .role-tool {{ background: #2d1b00; color: #fbbf24; }}
  .tool-name {{ font-weight: 600; color: var(--warn); }}
  .latency {{ color: var(--muted); font-size: 12px; margin-left: auto; }}
  .msg-body {{ display: none; background: var(--code-bg); padding: 12px 14px; }}
  .msg-body.open {{ display: block; }}
  pre {{ white-space: pre-wrap; word-break: break-all; font-size: 12px; line-height: 1.5; color: #cbd5e1; font-family: 'Cascadia Code', 'Fira Code', monospace; }}
  .tool-call-block {{ border: 1px solid var(--border); border-radius: 6px; margin-bottom: 8px; overflow: hidden; }}
  .tool-call-header {{ display: flex; gap: 8px; align-items: center; padding: 8px 12px; background: #1a1a2e; cursor: pointer; }}
  .tool-call-header:hover {{ background: #23233a; }}
  .tool-call-body {{ display: none; padding: 10px 12px; background: var(--code-bg); }}
  .tool-call-body.open {{ display: block; }}
  .citations-list {{ display: flex; flex-direction: column; gap: 4px; }}
  .citation-url {{ color: #60a5fa; font-size: 12px; word-break: break-all; }}
  .empty {{ color: var(--muted); font-style: italic; }}
  .tag {{ background: #1e293b; border: 1px solid var(--border); border-radius: 12px; color: var(--muted); font-size: 11px; padding: 1px 8px; }}
</style>
</head>
<body>
<header>
  <h1>Eval Run &mdash; {run_id_short}&hellip;</h1>
  <div class="meta">{timestamp} &nbsp;|&nbsp; Model: {model} &nbsp;|&nbsp; {total_cases} cases &times; {total_repeats} repeat(s)</div>
</header>
{banners}
<div class="stats-bar">
  <div class="stat"><span class="stat-label">Pass rate</span><span class="stat-value pass-rate">{pass_rate}</span></div>
  <div class="stat"><span class="stat-label">Total cost</span><span class="stat-value">${total_cost}</span></div>
  <div class="stat"><span class="stat-label">p50 latency</span><span class="stat-value">{p50}ms</span></div>
  <div class="stat"><span class="stat-label">p95 latency</span><span class="stat-value">{p95}ms</span></div>
  <div class="stat"><span class="stat-label">Mean tool calls</span><span class="stat-value">{mean_tools}</span></div>
</div>
<div class="container">
{cases_html}
</div>
<script>
document.querySelectorAll('.case-header').forEach(h => {{
  h.addEventListener('click', () => {{
    const body = h.nextElementSibling;
    const caret = h.querySelector('.caret');
    body.classList.toggle('open');
    caret.textContent = body.classList.contains('open') ? '▾' : '▸';
  }});
}});
document.querySelectorAll('.msg-header').forEach(h => {{
  h.addEventListener('click', () => {{
    const body = h.nextElementSibling;
    body.classList.toggle('open');
  }});
}});
document.querySelectorAll('.tool-call-header').forEach(h => {{
  h.addEventListener('click', (e) => {{
    e.stopPropagation();
    const body = h.nextElementSibling;
    body.classList.toggle('open');
  }});
}});
// Auto-expand failing cases.
document.querySelectorAll('.case-card').forEach(card => {{
  if (card.querySelector('.badge-fail, .badge-flaky')) {{
    const body = card.querySelector('.case-body');
    const caret = card.querySelector('.caret');
    if (body) {{ body.classList.add('open'); }}
    if (caret) {{ caret.textContent = '▾'; }}
  }}
}});
</script>
</body>
</html>
"""


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
    )


def _json_block(obj: Any) -> str:
    try:
        text = json.dumps(obj, indent=2, default=str)
    except Exception:
        text = str(obj)
    return f"<pre>{_esc(text)}</pre>"


def _render_message(msg: dict[str, Any]) -> str:
    role = msg.get("role", "")
    latency = msg.get("latency_ms")
    latency_html = f'<span class="latency">{latency}ms</span>' if latency else ""

    role_class = {
        "system": "role-system",
        "user": "role-user",
        "assistant": "role-assistant",
        "tool": "role-tool",
    }.get(role, "role-tool")

    if role == "tool":
        tool_name = msg.get("name", "tool")
        header_label = f'<span class="tool-name">{_esc(tool_name)}</span> result'
    elif role == "assistant":
        tool_calls = msg.get("tool_calls", [])
        call_names = ", ".join(_esc(c.get("name", "")) for c in tool_calls)
        header_label = f"calls: <span class='tool-name'>{call_names}</span>" if call_names else "text response"
    else:
        header_label = role

    body_parts = []

    if role == "assistant":
        text = msg.get("text", "")
        if text:
            body_parts.append(f"<p style='margin-bottom:8px;color:#94a3b8;font-size:12px;'>TEXT</p><pre>{_esc(text)}</pre>")
        for call in msg.get("tool_calls", []):
            name = _esc(call.get("name", ""))
            args_html = _json_block(call.get("args", {}))
            body_parts.append(
                f'<div class="tool-call-block">'
                f'<div class="tool-call-header"><span class="tool-name">{name}</span><span style="color:var(--muted);font-size:11px;">▸ args</span></div>'
                f'<div class="tool-call-body">{args_html}</div>'
                f'</div>'
            )
    else:
        content = msg.get("content", "")
        if content:
            body_parts.append(_json_block(content))

    body_html = "\n".join(body_parts) if body_parts else '<span class="empty">(empty)</span>'

    return (
        f'<div class="msg">'
        f'<div class="msg-header">'
        f'<span class="role-pill {role_class}">{_esc(role)}</span>'
        f'{header_label}'
        f'{latency_html}'
        f'</div>'
        f'<div class="msg-body">{body_html}</div>'
        f'</div>'
    )


def _render_assertions(results: list[Any]) -> str:
    items = []
    for r in results:
        icon = "✓" if r.passed else "✗"
        css = "assertion-pass" if r.passed else "assertion-fail"
        rationale_html = ""
        if r.rationale and not r.passed:
            rationale_html = f'<span class="assertion-rationale">Judge: {_esc(r.rationale)}</span>'
        items.append(
            f'<div class="assertion {css}">'
            f'<span class="assertion-icon">{icon}</span>'
            f'<div><span class="assertion-type">{_esc(r.assertion_type)}</span>'
            f'<span class="assertion-reason">{_esc(r.reason)}</span>'
            f'{rationale_html}</div>'
            f'</div>'
        )
    return f'<div class="assertions-list">{"".join(items)}</div>'


def _render_case(summary_label: str, case_results: list[CaseResult], is_regression: bool) -> str:
    first = case_results[0]
    case_id = first.case_id

    all_passed = all(r.passed for r in case_results)
    some_passed = any(r.passed for r in case_results)

    if len(case_results) == 1:
        badge_class = "badge-pass" if all_passed else "badge-fail"
        badge_text = "PASS" if all_passed else "FAIL"
    else:
        if all_passed:
            badge_class, badge_text = "badge-pass", f"{len(case_results)}/{len(case_results)} PASS"
        elif some_passed:
            n = sum(1 for r in case_results if r.passed)
            badge_class, badge_text = "badge-flaky", f"{n}/{len(case_results)} FLAKY"
        else:
            badge_class, badge_text = "badge-fail", f"0/{len(case_results)} FAIL"

    regression_marker = " ⚠ REGRESSION" if is_regression else ""
    meta_parts = [
        f"{first.wall_time_ms}ms",
        f"${first.cost_usd:.4f}",
        f"{first.tool_call_count} tools",
        first.stopped_reason,
    ]

    per_repeat_html = ""
    for i, result in enumerate(case_results):
        trace_path = result.trace_path
        messages_html = ""
        try:
            import json as _json
            trace = _json.loads(trace_path.read_text())
            msgs = trace.get("messages", [])
            # Skip system message for brevity — show it collapsed.
            messages_html = "".join(_render_message(m) for m in msgs)
        except Exception as e:
            messages_html = f'<pre class="empty">Could not load trace: {_esc(str(e))}</pre>'

        citations = result.trace_path and []
        try:
            import json as _json2
            trace2 = _json2.loads(result.trace_path.read_text())
            citations = trace2.get("citations", [])
            question = trace2.get("question", "")
            final_answer = trace2.get("final_answer") or ""
        except Exception:
            citations = []
            question = ""
            final_answer = ""

        repeat_label = f"Repeat {i + 1}" if len(case_results) > 1 else ""
        citations_html = (
            "\n".join(f'<div class="citation-url">{_esc(c)}</div>' for c in citations)
            if citations
            else '<span class="empty">(none)</span>'
        )

        per_repeat_html += f"""
        <div class="section">
          {"<div style='font-weight:600;margin-bottom:10px;'>"+repeat_label+"</div>" if repeat_label else ""}
          <div class="section-title">Question</div>
          <div class="question">{_esc(question)}</div>
        </div>
        <div class="section">
          <div class="section-title">Final answer</div>
          <div class="answer">{_esc(final_answer) if final_answer else '<span class="empty">(no answer)</span>'}</div>
        </div>
        <div class="section">
          <div class="section-title">Assertions</div>
          {_render_assertions(result.assertion_results)}
        </div>
        <div class="section">
          <div class="section-title">Citations ({len(citations)})</div>
          <div class="citations-list">{citations_html}</div>
        </div>
        <div class="section">
          <div class="section-title">Message timeline ({len(msgs if "msgs" in dir() else [])} messages)</div>
          <div class="timeline">{messages_html}</div>
        </div>
        """

    return f"""
    <div class="case-card">
      <div class="case-header">
        <span class="badge {badge_class}">{badge_text}</span>
        <span class="case-id">{_esc(case_id)}{_esc(regression_marker)}</span>
        <span class="case-meta">{" &nbsp;|&nbsp; ".join(_esc(p) for p in meta_parts)}</span>
        <span class="caret">▸</span>
      </div>
      <div class="case-body">
        {per_repeat_html}
      </div>
    </div>
    """


def generate_html(report: RunReport) -> Path:
    by_case: dict[str, list[CaseResult]] = {}
    for r in report.all_results:
        by_case.setdefault(r.case_id, []).append(r)

    regression_set = set()
    for reg in report.regressions:
        case_id = reg.split(":")[0].strip()
        regression_set.add(case_id)

    cases_html = "\n".join(
        _render_case(
            summary_label=next((s.label() for s in report.summaries if s.case_id == cid), ""),
            case_results=results,
            is_regression=cid in regression_set,
        )
        for cid, results in by_case.items()
    )

    banners = ""
    if report.regressions:
        items = "".join(f"<div>⚠ {_esc(r)}</div>" for r in report.regressions)
        banners += f'<div class="regression-banner"><strong>Regressions vs previous run:</strong>{items}</div>'
    if report.improvements:
        items = "".join(f"<div>✓ {_esc(i)}</div>" for i in report.improvements)
        banners += f'<div class="improvement-banner"><strong>Improvements vs previous run:</strong>{items}</div>'

    html = _HTML_TEMPLATE.format(
        run_id_short=report.run_id[:8],
        timestamp=report.timestamp[:19],
        model=_esc(report.model),
        total_cases=report.total_cases,
        total_repeats=report.total_repeats,
        pass_rate=f"{report.pass_rate:.1%}",
        total_cost=f"{report.total_cost_usd:.4f}",
        p50=f"{report.p50_latency_ms:.0f}",
        p95=f"{report.p95_latency_ms:.0f}",
        mean_tools=f"{report.mean_tool_calls:.1f}",
        banners=banners,
        cases_html=cases_html,
    )

    path = _REPORTS_DIR / f"{report.run_id}.html"
    path.write_text(html, encoding="utf-8")
    return path
