// Crucible Web Dashboard Client Logic
// Author: Arya Shah (Arya-A-Shah)
// Updated for Phase 4: Full API integration with SSE live streaming

let currentScenario = 'A';

// Agent colour coding for timeline cards
const AGENT_COLORS = {
  orchestrator:     '#6c5ce7',
  logic_reviewer:   '#00b894',
  security_auditor: '#e17055',
  style_doc_agent:  '#74b9ff',
  system:           '#636e72',
};

const MSG_LABELS = {
  plan:              '📋 Plan',
  tool_call:         '🔧 Tool Call',
  tool_result:       '✅ Tool Result',
  finding:           '🔍 Finding',
  fallback:          '⚠️ Fallback',
  review:            '🔄 Review',
  critique_request:  '🗣️ Critique Request',
  critique_response: '💬 Critique Response',
  arbitration:       '⚖️ Arbitration',
  final_report:      '📊 Final Report',
  termination_guard: '🛑 Termination Guard',
  error:             '❌ Error',
  stream_done:       '✔️ Stream Done',
};

const SCENARIOS = {
  python: {
    A: `def login(username, password):
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    result = db.execute(query)
    user = result.fetchone()
    if user:
        return {"token": generate_token(user.id), "status": "success"}
    return {"status": "failure"}

def calculate_discount(items, customer_type):
    total = 0
    for item in items:
        if customer_type == "premium":
            for sub in item.sub_items:
                for detail in sub.details:
                    total += detail.price * 0.8
        elif customer_type == "regular":
            total += item.price * 0.9
    return total`,

    B: `"""Math utility module for positive arithmetic."""

def add_positive_numbers(a: int, b: int) -> int:
    """Calculate the sum of two positive integers."""
    if a < 0 or b < 0:
        raise ValueError("Both numbers must be non-negative.")
    return a + b`,

    C: `This is plain descriptive prose, not Python source code, submitted to test edge-case input handling.`,

    D: `import sqlite3

def run_query(user_id):
    # Simulated Bandit failure will trigger autonomous LLM fallback
    conn = sqlite3.connect("app.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM profiles WHERE id = " + str(user_id))
    return cur.fetchall()`
  },

  javascript: {
    A: `// Authentication service & discount calculation
async function login(username, password) {
  // Vulnerable to SQL Injection (CWE-89) via dynamic string interpolation
  const query = \`SELECT * FROM users WHERE username = '\${username}' AND password = '\${password}'\`;
  const [rows] = await db.query(query);
  if (rows && rows.length > 0) {
    return { token: generateToken(rows[0].id), status: "success" };
  }
  return { status: "failure" };
}

function calculateDiscount(items, customerType) {
  // High cyclomatic complexity with deeply nested loops and branches
  let total = 0;
  for (const item of items) {
    if (customerType === "premium") {
      for (const sub of item.subItems) {
        for (const detail of sub.details) {
          total += detail.price * 0.8;
        }
      }
    } else if (customerType === "regular") {
      total += item.price * 0.9;
    }
  }
  return total;
}`,

    B: `/**
 * Math utility module for positive arithmetic.
 */

/**
 * Calculate the sum of two positive integers.
 * @param {number} a 
 * @param {number} b 
 * @returns {number}
 */
function addPositiveNumbers(a, b) {
  if (a < 0 || b < 0) {
    throw new RangeError("Both numbers must be non-negative.");
  }
  return a + b;
}`,

    C: `This is plain descriptive prose, not JavaScript source code, submitted to test edge-case input handling.`,

    D: `const sqlite3 = require('sqlite3').verbose();

function runQuery(userId) {
  // Direct string concatenation in SQL query (CWE-89)
  const db = new sqlite3.Database('app.db');
  const sql = "SELECT * FROM profiles WHERE id = " + userId;
  return new Promise((resolve, reject) => {
    db.all(sql, [], (err, rows) => {
      if (err) reject(err);
      else resolve(rows);
    });
  });
}`
  },

  go: {
    A: `package auth

import (
	"database/sql"
	"fmt"
)

type Item struct {
	Price    float64
	SubItems []SubItem
}

type SubItem struct {
	Details []Detail
}

type Detail struct {
	Price float64
}

// Login handles user authentication - vulnerable to SQL Injection (CWE-89)
func Login(db *sql.DB, username, password string) (string, error) {
	query := fmt.Sprintf("SELECT id FROM users WHERE username = '%s' AND password = '%s'", username, password)
	row := db.QueryRow(query)
	var id string
	if err := row.Scan(&id); err != nil {
		return "", err
	}
	return "token_" + id, nil
}

// CalculateDiscount calculates order discount with high cyclomatic complexity
func CalculateDiscount(items []Item, customerType string) float64 {
	total := 0.0
	for _, item := range items {
		if customerType == "premium" {
			for _, sub := range item.SubItems {
				for _, detail := range sub.Details {
					total += detail.Price * 0.8
				}
			}
		} else if customerType == "regular" {
			total += item.Price * 0.9
		}
	}
	return total
}`,

    B: `package mathutil

import "errors"

// AddPositiveNumbers calculates the sum of two positive integers.
func AddPositiveNumbers(a, b int) (int, error) {
	if a < 0 || b < 0 {
		return 0, errors.New("both numbers must be non-negative")
	}
	return a + b, nil
}`,

    C: `This is plain descriptive prose, not Go source code, submitted to test edge-case input handling.`,

    D: `package dbutil

import (
	"database/sql"
)

// RunQuery executes query using direct string concatenation (CWE-89)
func RunQuery(db *sql.DB, userID string) (*sql.Rows, error) {
	query := "SELECT * FROM profiles WHERE id = " + userID
	return db.Query(query)
}`
  }
};

function handleLanguageChange(lang) {
  const langScenarios = SCENARIOS[lang] || SCENARIOS.python;
  const code = langScenarios[currentScenario] || '';
  document.getElementById('code-input').value = code;
}

function loadScenario(type) {
  currentScenario = type;
  const lang = document.getElementById('input-language').value || 'python';
  const langScenarios = SCENARIOS[lang] || SCENARIOS.python;
  const code = langScenarios[type] || '';
  document.getElementById('code-input').value = code;
  document.getElementById('fault-toggle').value =
    type === 'D' ? 'bandit_scanner' : '';
}

// ---------------------------------------------------------------------------
// submitReview — POST to /review and render results
// ---------------------------------------------------------------------------
async function submitReview() {
  const code    = document.getElementById('code-input').value.trim();
  const language = document.getElementById('input-language').value;
  const context  = document.getElementById('input-context').value.trim();
  const fault    = document.getElementById('fault-toggle').value;

  if (!code) { alert('Please enter or select source code first.'); return; }

  // Clear UI
  const timeline = document.getElementById('timeline');
  timeline.innerHTML = '';
  document.getElementById('report-panel').classList.add('hidden');
  const autofixPanel = document.getElementById('autofix-panel');
  if (autofixPanel) autofixPanel.classList.add('hidden');

  const submitBtn = document.getElementById('btn-submit');
  submitBtn.disabled = true;
  submitBtn.querySelector('.btn-text').textContent = 'Analyzing…';

  // Update status indicator
  setStatus('running', 'Orchestrator Running…');

  try {
    const response = await fetch('/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        input_code: code,
        language,
        context: context || 'Standard web review',
        fault_injection: fault
      })
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(err.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();

    // Render all trace event cards
    if (Array.isArray(data.events)) {
      data.events.forEach(evt => renderEventCard(evt));
    }

    // Update round indicator
    const roundEvents = (data.events || []).filter(e => e.message_type === 'plan');
    if (roundEvents.length) {
      document.getElementById('round-indicator').textContent =
        `Round ${roundEvents.length}`;
    }

    // Render final report
    if (data.final_report) {
      renderFinalReport(data.final_report);
    }

    setStatus('online', 'Engine Ready');

  } catch (err) {
    renderEventCard({
      from_agent: 'system',
      to_agent: 'user',
      message_type: 'error',
      summary: `Request failed: ${err.message}`,
      timestamp: new Date().toISOString()
    });
    setStatus('online', 'Engine Ready');
  } finally {
    submitBtn.disabled = false;
    submitBtn.querySelector('.btn-text').textContent = 'Execute Multi-Agent Review';
  }
}

// ---------------------------------------------------------------------------
// renderEventCard — adds a single trace event to the live timeline
// ---------------------------------------------------------------------------
function renderEventCard(evt) {
  const timeline = document.getElementById('timeline');

  // Remove empty-state placeholder on first card
  const emptyState = document.getElementById('empty-state');
  if (emptyState) emptyState.remove();

  const card = document.createElement('div');
  const msgType = evt.message_type || 'plan';
  card.className = `event-card ${msgType}`;

  const color = AGENT_COLORS[evt.from_agent] || '#b2bec3';
  const label = MSG_LABELS[msgType] || msgType;
  const time  = evt.timestamp ? evt.timestamp.split('T')[1]?.slice(0, 8) : '';

  // Highlight arbitration and critique cards with amber accent
  const isConflict = ['arbitration', 'critique_request', 'critique_response'].includes(msgType);

  card.innerHTML = `
    <div class="card-header" style="border-left: 3px solid ${color}; ${isConflict ? 'background: rgba(253,203,110,0.08);' : ''}">
      <span class="card-sender" style="color:${color}">${evt.from_agent || '?'} ➔ ${evt.to_agent || '?'}</span>
      <span class="card-badge">${label}</span>
      <span class="card-time">${time}</span>
    </div>
    <div class="card-body">
      ${evt.summary || ''}
      ${evt.decision_rationale ? `<div class="card-rationale">💡 ${evt.decision_rationale.slice(0, 180)}</div>` : ''}
    </div>
  `;

  timeline.appendChild(card);

  // Smooth scroll to latest card
  card.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

// ---------------------------------------------------------------------------
// renderFinalReport — populates the bottom report panel
// ---------------------------------------------------------------------------
function renderFinalReport(report) {
  const panel      = document.getElementById('report-panel');
  const summaryEl  = document.getElementById('report-summary');
  const findingsEl = document.getElementById('report-findings');
  const verdictBadge = document.getElementById('report-verdict');

  panel.classList.remove('hidden');

  // Verdict badge
  const verdict = report.overall_verdict || report.status || 'complete';
  const isCritical = report.overall_severity === 'critical' || report.overall_severity === 'high';
  verdictBadge.textContent = isCritical ? '🔴 CRITICAL ISSUES FOUND' : '🟢 REVIEW COMPLETE';
  verdictBadge.className   = `badge ${isCritical ? 'badge-critical' : 'badge-info'}`;

  // Executive summary
  const summary = report.executive_summary || report.synthesis_summary || '';
  summaryEl.innerHTML = `<p>${summary}</p>`;
  if (report.metrics) {
    const m = report.metrics;
    summaryEl.innerHTML += `
      <div class="metrics-row">
        <span class="metric critical">🔴 Critical: ${m.critical ?? 0}</span>
        <span class="metric high">🟠 High: ${m.high ?? 0}</span>
        <span class="metric medium">🟡 Medium: ${m.medium ?? 0}</span>
        <span class="metric low">🟢 Low: ${m.low ?? 0}</span>
        <span class="metric info">ℹ️ Info: ${m.info ?? 0}</span>
        <span class="metric rounds">🔄 Rounds: ${m.total_rounds ?? 1}</span>
      </div>
    `;
  }

  // Findings list
  const findings = report.ranked_findings || report.all_issues || [];
  if (findings.length === 0) {
    findingsEl.innerHTML = '<p style="color: var(--success); padding: 8px 0;">✅ No significant issues detected.</p>';
  } else {
    const SCOLOR = { critical: '#ff7675', high: '#e17055', medium: '#fdcb6e', low: '#55efc4', info: '#74b9ff' };
    let html = '<ul class="findings-list">';
    findings.forEach(f => {
      const sev = (f.severity || 'info').toLowerCase();
      const color = SCOLOR[sev] || '#b2bec3';
      html += `
        <li class="finding-item">
          <span class="finding-badge" style="background:${color}20; color:${color}; border:1px solid ${color}40">
            ${sev.toUpperCase()}
          </span>
          <span class="finding-location">L${f.line_start}–${f.line_end}</span>
          <span class="finding-category">[${f.category || ''}]</span>
          <span class="finding-evidence">${f.evidence || ''}</span>
          ${f.recommendation ? `<div class="finding-rec">💡 ${f.recommendation}</div>` : ''}
          ${f.cwe_id ? `<span class="finding-cwe">${f.cwe_id}</span>` : ''}
        </li>
      `;
    });
    html += '</ul>';
    findingsEl.innerHTML = html;
  }

  panel.scrollIntoView({ behavior: 'smooth' });
}

// ---------------------------------------------------------------------------
// setStatus — update top-right status indicator
// ---------------------------------------------------------------------------
function setStatus(state, text) {
  const dot  = document.querySelector('.status-indicator');
  const span = document.getElementById('system-status-text');
  dot.className  = `status-indicator ${state}`;
  span.textContent = text;
}

// ---------------------------------------------------------------------------
// On load: check /health and update indicator
// ---------------------------------------------------------------------------
window.addEventListener('DOMContentLoaded', async () => {
  const langSelect = document.getElementById('input-language');
  if (langSelect) {
    langSelect.addEventListener('change', (e) => {
      handleLanguageChange(e.target.value);
    });
  }

  try {
    const res = await fetch('/health');
    if (res.ok) {
      const d = await res.json();
      setStatus('online', d.mock_mode ? 'Mock Mode — Ready' : 'Engine Ready');
    }
  } catch {
    setStatus('offline', 'Server Unreachable');
  }
});

// ---------------------------------------------------------------------------
// Auto-Fix & Refactor functionality
// ---------------------------------------------------------------------------
let currentFixedCode = '';

async function generateAutoFix() {
  const code = document.getElementById('code-input').value.trim();
  const language = document.getElementById('input-language').value;
  const context = document.getElementById('input-context').value.trim();
  const btn = document.getElementById('btn-autofix');
  const panel = document.getElementById('autofix-panel');
  const explanationEl = document.getElementById('autofix-explanation');
  const codeContentEl = document.getElementById('autofix-code-content');

  if (!code) {
    alert('Please enter or select source code first.');
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Generating Patch...';

  try {
    const response = await fetch('/autofix', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, language, context })
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    currentFixedCode = data.fixed_code || code;

    explanationEl.textContent = data.explanation || 'Refactored code addressing identified vulnerabilities.';
    codeContentEl.textContent = currentFixedCode;
    panel.classList.remove('hidden');
    panel.scrollIntoView({ behavior: 'smooth' });

  } catch (err) {
    alert('Failed to generate auto-fix: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '✨ Auto-Fix & Refactor';
  }
}

function applyFixedCode() {
  if (!currentFixedCode) return;
  document.getElementById('code-input').value = currentFixedCode;
  alert('Refactored code applied to editor! You can now click "Execute Multi-Agent Review" to verify that all findings are resolved.');
}

function copyFixedCode() {
  if (!currentFixedCode) return;
  navigator.clipboard.writeText(currentFixedCode).then(() => {
    alert('Refactored code copied to clipboard!');
  }).catch(() => {
    alert('Failed to copy to clipboard.');
  });
}

