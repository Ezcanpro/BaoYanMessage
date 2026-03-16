const state = {
  allRows: [],
  filteredRows: [],
  isImporting: false,
};

const elements = {};

document.addEventListener("DOMContentLoaded", async () => {
  bindElements();
  bindEvents();
  await loadSchools();
});

function bindElements() {
  elements.schoolSearch = document.getElementById("schoolSearch");
  elements.majorSearch = document.getElementById("majorSearch");
  elements.yearFilter = document.getElementById("yearFilter");
  elements.typeFilter = document.getElementById("typeFilter");
  elements.resetButton = document.getElementById("resetButton");
  elements.importButton = document.getElementById("importButton");
  elements.statusText = document.getElementById("statusText");
  elements.resultCount = document.getElementById("resultCount");
  elements.urgentCount = document.getElementById("urgentCount");
  elements.tableBody = document.getElementById("tableBody");
  elements.emptyState = document.getElementById("emptyState");
}

function bindEvents() {
  elements.schoolSearch.addEventListener("input", applyFilters);
  elements.majorSearch.addEventListener("input", applyFilters);
  elements.yearFilter.addEventListener("change", applyFilters);
  elements.typeFilter.addEventListener("change", applyFilters);
  elements.importButton.addEventListener("click", importOfficialCsv);

  elements.resetButton.addEventListener("click", () => {
    elements.schoolSearch.value = "";
    elements.majorSearch.value = "";
    elements.yearFilter.value = "";
    elements.typeFilter.value = "";
    applyFilters();
  });
}

async function loadSchools() {
  setStatus("正在从 /schools 获取数据...");

  try {
    const response = await fetch("/schools");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const payload = await response.json();
    state.allRows = Array.isArray(payload.data) ? payload.data : [];

    populateYearOptions(state.allRows);
    applyFilters();
    setStatus(`已加载 ${state.allRows.length} 条记录`);
  } catch (error) {
    state.allRows = [];
    state.filteredRows = [];
    renderTable();
    renderSummary();
    setStatus(`加载失败：${error.message}`);
  }
}

async function importOfficialCsv() {
  if (state.isImporting) {
    return;
  }

  state.isImporting = true;
  elements.importButton.disabled = true;
  setStatus("正在导入 data/2027_universities_official.csv ...");

  try {
    const response = await fetch("/admin/import-official-csv", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    });

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }

    await loadSchools();
    setStatus(`导入完成：${payload.count ?? 0} 条记录已同步到数据库`);
  } catch (error) {
    setStatus(`导入失败：${error.message}`);
  } finally {
    state.isImporting = false;
    elements.importButton.disabled = false;
  }
}

function populateYearOptions(rows) {
  const currentValue = elements.yearFilter.value;
  const years = [...new Set(rows.map((row) => row.year))]
    .filter((year) => year !== null && year !== undefined)
    .sort((a, b) => a - b);

  elements.yearFilter.innerHTML = '<option value="">全部年份</option>';

  years.forEach((year) => {
    const option = document.createElement("option");
    option.value = String(year);
    option.textContent = String(year);
    elements.yearFilter.appendChild(option);
  });

  if (years.includes(Number(currentValue)) || years.includes(currentValue)) {
    elements.yearFilter.value = currentValue;
  }
}

function applyFilters() {
  const schoolKeyword = elements.schoolSearch.value.trim();
  const majorKeyword = elements.majorSearch.value.trim();
  const yearValue = elements.yearFilter.value;
  const typeValue = elements.typeFilter.value;

  state.filteredRows = state.allRows.filter((row) => {
    const matchSchool = !schoolKeyword || String(row.school || "").includes(schoolKeyword);
    const matchMajor = !majorKeyword || String(row.major || "").includes(majorKeyword);
    const matchYear = !yearValue || String(row.year) === yearValue;
    const matchType = !typeValue || row.type === typeValue;
    return matchSchool && matchMajor && matchYear && matchType;
  });

  renderTable();
  renderSummary();
}

function renderSummary() {
  const urgentRows = state.filteredRows.filter((row) => getDeadlineLevel(row.deadline) === "urgent");
  elements.resultCount.textContent = String(state.filteredRows.length);
  elements.urgentCount.textContent = String(urgentRows.length);
}

function renderTable() {
  elements.tableBody.innerHTML = "";

  if (state.filteredRows.length === 0) {
    elements.emptyState.classList.remove("hidden");
    return;
  }

  elements.emptyState.classList.add("hidden");

  state.filteredRows.forEach((row) => {
    const tr = document.createElement("tr");
    const deadlineLevel = getDeadlineLevel(row.deadline);
    const cleanedNotes = cleanNotes(row.notes);
    const safeUrl = row.url ? escapeHtml(row.url) : "";

    if (deadlineLevel === "urgent" || deadlineLevel === "warning") {
      tr.classList.add(`deadline-${deadlineLevel}`);
    }

    tr.innerHTML = `
      <td class="school-cell">${escapeHtml(row.school)}</td>
      <td class="major-cell">${escapeHtml(row.major || "")}</td>
      <td><span class="type-badge">${escapeHtml(row.type)}</span></td>
      <td>${escapeHtml(String(row.year ?? ""))}</td>
      <td class="title-cell">${renderTitleCell(row.title, safeUrl)}</td>
      <td><span class="deadline-chip ${deadlineLevel}">${escapeHtml(formatDeadline(row.deadline))}</span></td>
      <td>${renderUrlCell(safeUrl)}</td>
      <td class="notes-cell">${escapeHtml(cleanedNotes)}</td>
    `;

    elements.tableBody.appendChild(tr);
  });
}

function renderTitleCell(title, safeUrl) {
  const safeTitle = escapeHtml(title || "");
  if (!safeUrl) {
    return safeTitle;
  }

  return `
    <a class="title-link" href="${safeUrl}" target="_blank" rel="noreferrer">
      ${safeTitle}
    </a>
  `;
}

function renderUrlCell(safeUrl) {
  if (!safeUrl) {
    return "";
  }

  return `
    <a class="url-link" href="${safeUrl}" target="_blank" rel="noreferrer">
      官网链接
    </a>
  `;
}

function getDeadlineLevel(deadline) {
  if (!deadline) {
    return "normal";
  }

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const endDate = new Date(`${deadline}T00:00:00`);
  if (Number.isNaN(endDate.getTime())) {
    return "normal";
  }

  const diffDays = Math.ceil((endDate - today) / 86400000);

  if (diffDays >= 0 && diffDays <= 14) {
    return "urgent";
  }

  if (diffDays > 14 && diffDays <= 30) {
    return "warning";
  }

  return "normal";
}

function formatDeadline(deadline) {
  return deadline || "";
}

function cleanNotes(notes) {
  if (!notes) {
    return "";
  }

  const normalized = String(notes).trim();
  const ignoredValues = new Set(["-", "--", "_No response_", "暂无", "无", "None", "null"]);
  if (ignoredValues.has(normalized)) {
    return "";
  }

  const noisyPhrases = ["示例数据", "用于演示", "适合作为", "适合测试", "可扩展"];
  if (noisyPhrases.some((phrase) => normalized.includes(phrase))) {
    return "";
  }

  return normalized;
}

function setStatus(message) {
  elements.statusText.textContent = message;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
