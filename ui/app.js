// Crucible Web Dashboard Client Logic
// Author: Arya Shah (Arya-A-Shah)

const SCENARIOS = {
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
};

function loadScenario(type) {
  const code = SCENARIOS[type] || "";
  document.getElementById("code-input").value = code;
  if (type === "D") {
    document.getElementById("fault-toggle").value = "bandit_scanner";
  } else {
    document.getElementById("fault-toggle").value = "";
  }
}

async function submitReview() {
  const code = document.getElementById("code-input").value.trim();
  const language = document.getElementById("input-language").value;
  const context = document.getElementById("input-context").value.trim();
  const fault = document.getElementById("fault-toggle").value;

  if (!code) {
    alert("Please enter or select source code first.");
    return;
  }

  const timeline = document.getElementById("timeline");
  timeline.innerHTML = "";
  document.getElementById("report-panel").classList.add("hidden");
  const submitBtn = document.getElementById("btn-submit");
  submitBtn.disabled = true;
  submitBtn.innerHTML = "<span>Analyzing Multi-Agent Graph...</span>";

  try {
    const response = await fetch("/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        input_code: code,
        input_language: language,
        input_context: context || "Standard web review",
        fault_injection: fault
      })
    });

    const data = await response.json();
    if (data.events) {
      data.events.forEach(evt => renderEventCard(evt));
    }
    if (data.final_report) {
      renderFinalReport(data.final_report);
    }
  } catch (err) {
    renderEventCard({
      from_agent: "system",
      message_type: "error",
      summary: `Request failed: ${err.message}`,
      timestamp: new Date().toISOString()
    });
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerHTML = "<span>Execute Multi-Agent Review</span>";
  }
}

function renderEventCard(evt) {
  const timeline = document.getElementById("timeline");
  const card = document.createElement("div");
  card.className = `event-card ${evt.message_type || ''}`;

  const time = evt.timestamp ? evt.timestamp.split("T")[1]?.slice(0, 8) : "";

  card.innerHTML = `
    <div class="card-header">
      <span class="card-sender">${evt.from_agent} ➔ ${evt.to_agent}</span>
      <span class="card-time">${time}</span>
    </div>
    <div class="card-body">
      <strong>[${evt.message_type}]</strong> ${evt.summary}
    </div>
  `;
  timeline.appendChild(card);
  timeline.scrollTop = timeline.scrollHeight;
}

function renderFinalReport(report) {
  const panel = document.getElementById("report-panel");
  const summaryEl = document.getElementById("report-summary");
  const findingsEl = document.getElementById("report-findings");
  const verdictBadge = document.getElementById("report-verdict");

  panel.classList.remove("hidden");
  verdictBadge.textContent = (report.overall_verdict || "COMPLETE").toUpperCase();
  verdictBadge.className = `badge ${report.overall_verdict === "critical_issues_found" ? "badge-critical" : "badge-info"}`;

  summaryEl.innerHTML = `<p>${report.synthesis_summary || ''}</p>`;

  let html = "<ul style='margin-top: 10px; padding-left: 20px;'>";
  (report.ranked_findings || []).forEach(f => {
    html += `<li><strong>[${f.severity.toUpperCase()}] line ${f.line_start}:</strong> ${f.evidence} <em>(${f.recommendation})</em></li>`;
  });
  html += "</ul>";
  findingsEl.innerHTML = html;
}
