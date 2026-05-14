"""Render an HTML summary report for a build run."""

from __future__ import annotations

from collections import Counter

from jinja2 import Environment, select_autoescape

from autism_corpus.pipeline import BuildResult

_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Autism Corpus Build Report — {{ result.run_id }}</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       max-width: 960px; margin: 2em auto; padding: 0 1em; color: #222; }
h1 { margin-bottom: 0; }
.meta { color: #666; font-size: 0.9em; }
table { border-collapse: collapse; margin: 1em 0; width: 100%; }
th, td { border-bottom: 1px solid #eee; padding: 6px 10px; text-align: left; }
th { background: #f7f7f7; }
tr:hover { background: #fafafa; }
.flag { color: #b06000; }
.dropped { color: #888; }
code { background: #f3f3f3; padding: 1px 4px; border-radius: 3px; }
</style>
</head>
<body>
<h1>Autism Corpus Build Report</h1>
<p class="meta">
  Run: <code>{{ result.run_id }}</code> ·
  Pipeline: <code>{{ result.manifest.pipeline_version }}</code> ·
  Generated: <code>{{ result.manifest.generated_at.isoformat() }}</code>
</p>

<h2>Totals</h2>
<ul>
  <li>Documents kept: <strong>{{ result.documents | length }}</strong></li>
  <li>Chunks emitted: <strong>{{ result.chunks | length }}</strong></li>
  <li>Dropped by filters: <strong>{{ result.filter_report.dropped | length }}</strong></li>
  <li>Flagged for review:
      <strong>{{ result.filter_report.flagged_for_review | length }}</strong></li>
</ul>

<h2>Per source</h2>
<table>
  <thead><tr>
    <th>Source</th><th>Discovered</th><th>Parse errors</th>
    <th>Documents kept</th><th>Chunks emitted</th>
  </tr></thead>
  <tbody>
    {% for sid, stats in result.per_source.items() | sort %}
    <tr>
      <td><code>{{ sid }}</code></td>
      <td>{{ stats.documents_discovered }}</td>
      <td>{{ stats.parse_errors }}</td>
      <td>{{ stats.documents_kept }}</td>
      <td>{{ stats.chunks_emitted }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>

<h2>Licence breakdown (chunks)</h2>
<table>
  <thead><tr><th>Licence</th><th>Chunks</th></tr></thead>
  <tbody>
    {% for licence, count in licences_sorted %}
    <tr><td><code>{{ licence }}</code></td><td>{{ count }}</td></tr>
    {% endfor %}
  </tbody>
</table>

{% if result.filter_report.dropped %}
<h2>Dropped documents</h2>
<table>
  <thead><tr><th>Source</th><th>Item</th><th>Title</th><th>Reason</th></tr></thead>
  <tbody>
    {% for doc, reason in result.filter_report.dropped %}
    <tr class="dropped">
      <td><code>{{ doc.source_id }}</code></td>
      <td><code>{{ doc.source_item_id }}</code></td>
      <td>{{ doc.title }}</td>
      <td>{{ reason }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endif %}

{% if result.filter_report.flagged_for_review %}
<h2 class="flag">Flagged for review</h2>
<table>
  <thead><tr><th>Source</th><th>Item</th><th>Title</th><th>Reason</th></tr></thead>
  <tbody>
    {% for doc, reason in result.filter_report.flagged_for_review %}
    <tr class="flag">
      <td><code>{{ doc.source_id }}</code></td>
      <td><code>{{ doc.source_item_id }}</code></td>
      <td>{{ doc.title }}</td>
      <td>{{ reason }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endif %}

<h2>Sample documents</h2>
<table>
  <thead><tr><th>Source</th><th>Title</th><th>Licence</th><th>URL</th></tr></thead>
  <tbody>
    {% for doc in result.documents[:25] %}
    <tr>
      <td><code>{{ doc.source_id }}</code></td>
      <td>{{ doc.title }}</td>
      <td><code>{{ doc.licence }}</code></td>
      <td><a href="{{ doc.canonical_url }}">{{ doc.canonical_url }}</a></td>
    </tr>
    {% endfor %}
  </tbody>
</table>

</body>
</html>
"""

_ENV = Environment(autoescape=select_autoescape(["html", "xml"]))
_TEMPLATE_OBJ = _ENV.from_string(_TEMPLATE)


def render_report(result: BuildResult) -> str:
    licence_counter: Counter[str] = Counter(c.licence for c in result.chunks)
    licences_sorted = sorted(licence_counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return _TEMPLATE_OBJ.render(result=result, licences_sorted=licences_sorted)


def write_report(result: BuildResult) -> None:
    result.report_path.write_text(render_report(result), encoding="utf-8")
