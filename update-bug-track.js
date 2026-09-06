#!/usr/bin/env node
/**
 * Rewrite bug_track.json with stable PR links, severity + state labels,
 * and a top-level summary block. Self-contained — no network calls,
 * no Python, no PowerShell. Run from repo root: node update-bug-track.js
 *
 * Source-of-truth for which bug maps to which PR lives in PR_MAP below.
 * To pick up a newly-merged PR, just edit the row and re-run.
 */

const fs = require('fs');

const REPO = 'however-yir/knowledgeops-agent';
const FILE = 'bug_track.json';

// bug id -> [PR number, state, fallback title]
// state: 'merged' | 'open' | 'not-fix' (recorded but not fixed in this cycle)
const PR_MAP = {
  1:  [135, 'merged',  'fix(harness): harden workspace process lifecycle, fail orphaned stream tasks, persist step input tokens'],
  2:  [135, 'merged',  'fix(harness): harden workspace process lifecycle, fail orphaned stream tasks, persist step input tokens'],
  3:  [135, 'merged',  'fix(harness): harden workspace process lifecycle, fail orphaned stream tasks, persist step input tokens'],
  4:  [135, 'merged',  'fix(harness): harden workspace process lifecycle, fail orphaned stream tasks, persist step input tokens'],
  5:  [139, 'merged',  'fix(backend): scope ingestion job claim to the owning tenant'],
  6:  [161, 'merged',  'fix(backend): add tenant_id to course/school/course_reservation'],
  7:  [null, 'not-fix', 'ChatController/CustomerServiceController skip cost billing — business policy decision'],
  8:  [139, 'merged',  'fix(backend): cap feedback dataset growth and filter expired memories'],
  9:  [140, 'merged',  'fix(frontend): satisfy Prettier CI check'],
  10: [null, 'not-fix', 'Frontend stores API key / JWT refresh token in localStorage — needs Set-Cookie refactor'],
  11: [141, 'merged',  'fix(backend): thread-safe RestTemplate init in web search backends'],
  12: [143, 'merged',  'fix(backend): handle missing multipart Content-Type in /ai/chat'],
  13: [144, 'merged',  'fix(backend): cap feedback dataset growth and filter expired memories'],
  14: [144, 'merged',  'fix(backend): cap feedback dataset growth and filter expired memories'],
  15: [145, 'merged',  'fix(backend): reject private/loopback MCP baseUrls to close SSRF'],
  16: [146, 'merged',  'fix(security): derive rate-limit IP from X-Forwarded-For behind proxies'],
  17: [147, 'merged',  'fix(harness): cap workspace propose_patch/apply_patch content size'],
  18: [148, 'merged',  'fix(harness): reject ripgrep flags that execute commands or read host files'],
  19: [149, 'merged',  'fix(harness): stop walking candidates once maxMatches is hit'],
  20: [150, 'merged',  'fix(harness): also sweep expired trusted-action tokens on execute'],
  21: [152, 'merged',  'fix(harness): restrict mvn test -D properties to a safe allow-list'],
  22: [154, 'merged',  'fix(harness): reject ripgrep flags that execute commands or read host files'],
  23: [156, 'merged',  'fix(graph): scope findByEntityId by tenant to close cross-tenant leak'],
  24: [null, 'not-fix', '(reserved; originally #24 audit-log XSS persisted — kept as a placeholder)'],
  25: [158, 'merged',  'fix(harness): cap MCP HTTP response body size'],
};

const SEVERITY_EMOJI = {
  high:   '🔴 high',
  medium: '🟡 medium',
  low:    '🟢 low',
  info:   'ℹ️ info',
};
const STATE_MARKER = {
  merged:  '✅ merged',
  open:    '🟠 open',
  'not-fix': '🟣 tracked (not fixed)',
};

function main() {
  const data = JSON.parse(fs.readFileSync(FILE, 'utf8'));

  const severityCount = { high: 0, medium: 0, low: 0, info: 0 };
  const stateCount = { merged: 0, open: 0, 'not-fix': 0 };
  const openPrs = [];

  for (const bug of data.bugs) {
    const entry = PR_MAP[bug.id];
    const pr = entry ? entry[0] : null;
    const state = entry ? entry[1] : 'not-fix';
    const title = entry ? entry[2] : '';

    const sevKey = SEVERITY_EMOJI[bug.severity] ? bug.severity : 'info';
    bug.severity_label = SEVERITY_EMOJI[sevKey];
    bug.state = state;
    bug.state_label = STATE_MARKER[state];

    if (pr !== null) {
      bug.pr = pr;
      bug.pr_url = `https://github.com/${REPO}/pull/${pr}`;
      bug.pr_title = title;
      openPrs.push({ pr, title, url: bug.pr_url });
    } else {
      bug.pr = null;
      bug.pr_url = null;
      bug.pr_title = null;
    }

    severityCount[sevKey] += 1;
    stateCount[state] += 1;
  }

  data.summary = {
    generated_at: new Date().toISOString(),
    total_bugs: data.bugs.length,
    by_severity: severityCount,
    by_state: stateCount,
    open_prs: openPrs,
    severity_legend: SEVERITY_EMOJI,
    state_legend: STATE_MARKER,
  };

  // Write raw UTF-8 bytes to bypass any PowerShell / shell codepage
  // round-trip that scrambled earlier manual rewrites.
  fs.writeFileSync(FILE, JSON.stringify(data, null, 2) + '\n');
  console.log(
    `wrote ${FILE} (${fs.statSync(FILE).size} bytes) — ` +
    `bugs=${data.bugs.length} merged=${stateCount.merged} ` +
    `not-fix=${stateCount['not-fix']}`
  );
}

main();
