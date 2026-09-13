"""Bonus: a tiny dependency-free HTML dashboard for eyeballing registered
patients without needing a DB client. Served at GET /dashboard."""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Patients Dashboard</title>
<style>
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem; color: #1a1a1a; background: #fafafa; }
  h1 { font-size: 1.4rem; }
  table { border-collapse: collapse; width: 100%; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  th, td { text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid #eee; font-size: 0.9rem; }
  th { background: #f2f2f2; position: sticky; top: 0; }
  input { padding: 0.4rem 0.6rem; margin-bottom: 1rem; width: 260px; border: 1px solid #ccc; border-radius: 4px; }
  .empty { color: #888; padding: 1rem; }
</style>
</head>
<body>
  <h1>Registered Patients</h1>
  <input id="search" placeholder="Filter by last name..." />
  <table id="tbl">
    <thead>
      <tr>
        <th>Name</th><th>DOB</th><th>Sex</th><th>Phone</th><th>City, State</th><th>Created</th>
      </tr>
    </thead>
    <tbody id="rows"></tbody>
  </table>
  <div id="empty" class="empty" style="display:none">No patients found.</div>

<script>
async function load(lastName) {
  const url = lastName ? `/patients?last_name=${encodeURIComponent(lastName)}` : "/patients";
  const res = await fetch(url);
  const json = await res.json();
  const rows = document.getElementById("rows");
  rows.innerHTML = "";
  const patients = json.data || [];
  document.getElementById("empty").style.display = patients.length ? "none" : "block";
  for (const p of patients) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${p.first_name} ${p.last_name}</td>
      <td>${p.date_of_birth}</td>
      <td>${p.sex}</td>
      <td>${p.phone_number}</td>
      <td>${p.city}, ${p.state}</td>
      <td>${new Date(p.created_at).toLocaleString()}</td>
    `;
    rows.appendChild(tr);
  }
}
document.getElementById("search").addEventListener("input", (e) => load(e.target.value));
load();
</script>
</body>
</html>
"""
