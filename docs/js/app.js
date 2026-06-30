/* app.js — Análisis del discurso de la mañanera */

"use strict";

// ── Paletas ─────────────────────────────────────────────────────────────────

const TOPIC_COLORS = [
  "#1B4332","#2D6A4F","#40916C","#52B788","#74C69D",
  "#95D5B2","#B7E4C7","#6A994E","#386641","#1D3557",
];

const FRAME_COLORS = {
  nosotros:   "#2D6A4F",
  adversario: "#BC4749",
  crisis:     "#E76F51",
  logro:      "#52B788",
  ciencia:    "#4361EE",
};

const FRAME_LABELS = {
  nosotros:   "Nosotros / comunidad",
  adversario: "Adversario / crítica",
  crisis:     "Crisis / problema",
  logro:      "Logro / oportunidad",
  ciencia:    "Ciencia / datos",
};

const VOZ_COLORS = {
  presidenta:  "#2D6A4F",
  pregunta:    "#74C69D",
  funcionario: "#BC4749",
  otro:        "#ADB5BD",
};

const VOZ_LABELS = {
  presidenta:  "Presidenta",
  pregunta:    "Preguntas",
  funcionario: "Funcionarios",
  otro:        "Otros",
};

const ACTOR_COLOR = "#2D6A4F";

// ── Utilidades ───────────────────────────────────────────────────────────────

const $ = id => document.getElementById(id);

async function loadJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`No se pudo cargar ${path}`);
  return res.json();
}

function formatNum(n) { return n.toLocaleString("es-MX"); }

function formatMonth(ym) {
  const [y, m] = ym.split("-");
  const names = ["","Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
  return `${names[+m]} ${y}`;
}

// ── Hero stats ───────────────────────────────────────────────────────────────

function renderHeroStats(stats) {
  $("stat-conf").textContent = formatNum(stats.total_conferencias);
  $("stat-meses").textContent = stats.meses.length;
  $("stat-rango").textContent = `${stats.fecha_inicio.slice(0,7)} → ${stats.fecha_fin.slice(0,7)}`;
  const totalTurnos = Object.values(stats.por_fecha)
    .reduce((a, c) => a + (c.presidenta_turns || 0), 0);
  $("stat-turnos").textContent = formatNum(totalTurnos);
}

// ── Distribución de voz ──────────────────────────────────────────────────────

function renderVoz(stats, speakers) {
  const meses = stats.meses;
  const tipos = ["presidenta", "pregunta", "funcionario", "otro"];

  // Usa los ratios REALES de palabras por tipo calculados en el pipeline
  // (speakers.ratio_palabras_por_mes), no estimaciones.
  const ratios = speakers.ratio_palabras_por_mes;

  const datasets = tipos.map(tipo => ({
    label: VOZ_LABELS[tipo],
    data: meses.map(m => ratios[m]?.[tipo] ?? 0),
    backgroundColor: VOZ_COLORS[tipo],
    borderWidth: 0,
  }));

  new Chart($("chart-voz"), {
    type: "bar",
    data: { labels: meses.map(formatMonth), datasets },
    options: {
      responsive: true,
      plugins: { legend: { display: false },
        tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y}%` } }
      },
      scales: {
        x: { stacked: true, grid: { display: false } },
        y: { stacked: true, max: 100, ticks: { callback: v => v + "%" }, grid: { color: "#F0F0F0" } },
      },
    },
  });

  const legend = $("voz-legend");
  tipos.forEach(tipo => {
    const item = document.createElement("div");
    item.className = "legend-item";
    item.innerHTML = `<span class="legend-dot" style="background:${VOZ_COLORS[tipo]}"></span>${VOZ_LABELS[tipo]}`;
    legend.appendChild(item);
  });
}

// ── Tópicos ──────────────────────────────────────────────────────────────────

function renderTopicos(topics, meses) {
  const datasets = topics.topic_labels.map((_, i) => ({
    label: `T${i+1}`,
    data: meses.map(m => {
      const v = topics.por_mes[m];
      return v ? Math.round(v[i] * 100) : 0;
    }),
    backgroundColor: TOPIC_COLORS[i] + "CC",
    borderColor: TOPIC_COLORS[i],
    borderWidth: 1,
    fill: true,
  }));

  new Chart($("chart-topicos"), {
    type: "bar",
    data: { labels: meses.map(formatMonth), datasets },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { stacked: true, grid: { display: false } },
        y: { stacked: true, max: 100, ticks: { callback: v => v + "%" }, grid: { color: "#F0F0F0" } },
      },
    },
  });

  const container = $("topic-words");
  topics.topic_labels.forEach((words, i) => {
    const row = document.createElement("div");
    row.className = "topic-row";
    row.innerHTML = `
      <span class="topic-dot" style="background:${TOPIC_COLORS[i]}"></span>
      <span class="topic-words"><strong>T${i+1}:</strong> ${words.slice(0, 6).join(", ")}</span>`;
    container.appendChild(row);
  });
}

// ── Encuadre ─────────────────────────────────────────────────────────────────

let encuadreChart = null;

function renderEncuadre(speakers, meses, corpus) {
  const framing = corpus === "total" ? speakers.framing_total : speakers.framing_presidenta;
  const frames  = framing.frames;
  const labels  = meses.map(formatMonth);

  const datasets = frames.map(frame => ({
    label: FRAME_LABELS[frame],
    data: meses.map(m => framing.por_mes[m]?.[frame] ?? null),
    borderColor: FRAME_COLORS[frame],
    backgroundColor: FRAME_COLORS[frame] + "22",
    borderWidth: 2,
    pointRadius: 3,
    tension: 0.3,
    fill: false,
  }));

  if (encuadreChart) {
    encuadreChart.data.datasets = datasets;
    encuadreChart.update();
    return;
  }

  encuadreChart = new Chart($("chart-encuadre"), {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false } },
        y: { title: { display: true, text: "ocurrencias / mil palabras" }, grid: { color: "#F0F0F0" } },
      },
    },
  });

  const legend = $("framing-legend");
  frames.forEach(frame => {
    const item = document.createElement("div");
    item.className = "legend-item";
    item.innerHTML = `<span class="legend-dot" style="background:${FRAME_COLORS[frame]}"></span>${FRAME_LABELS[frame]}`;
    legend.appendChild(item);
  });
}

// ── KWIC (búsqueda en cliente sobre el corpus de la presidenta) ──────────────

let corpusPres      = null;   // [[fecha, texto], …] ordenado desc por fecha
let stopwordsSet    = null;   // stopwords funcionales a rechazar
let fechaUrl        = null;   // {fecha: url de gob.mx}
let kwicAllResults  = [];
let kwicCurrentPage = 0;
let kwicTerm        = "";
const KWIC_PER_PAGE = 15;
const KWIC_WINDOW   = 60;     // caracteres de contexto a cada lado

async function loadCorpus() {
  if (corpusPres) return;
  $("kwic-status").textContent = "Cargando corpus (~4 MB, solo la primera vez)…";
  [corpusPres, stopwordsSet, fechaUrl] = await Promise.all([
    loadJSON("json/corpus_presidenta.json"),
    loadJSON("json/stopwords.json").then(arr => new Set(arr)),
    loadJSON("json/fecha_url.json"),
  ]);
  $("kwic-status").textContent = "";
}

// Construye un enlace al segmento exacto de la conferencia usando Text
// Fragments de Chrome (#:~:text=). Toma una frase contigua desde la palabra
// para que el navegador haga scroll y la resalte en la página de gob.mx.
function buildSegmentLink(fecha, texto, idx, termLen) {
  const base = fechaUrl[fecha];
  if (!base) return null;
  const snippet = texto.slice(idx, idx + 170);
  const words = snippet.split(/\s+/).slice(0, 12);
  if (words.length > 6) words.pop();   // descarta la última palabra (cortada)
  const frase = words.join(" ").replace(/[.,;:¿?¡!"]+$/, "").trim();
  if (!frase) return base;
  return `${base}#:~:text=${encodeURIComponent(frase)}`;
}

const escapeRe = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function highlight(text, word) {
  // Resalta la palabra respetando límites de palabra (con acentos)
  const re = new RegExp(`(?<![a-záéíóúüñ])(${escapeRe(word)})(?![a-záéíóúüñ])`, "gi");
  return text.replace(re, "<mark>$1</mark>");
}

function searchCorpus(term) {
  // Límites de palabra que funcionan con vocales acentuadas (JS \b es ASCII)
  const re = new RegExp(`(?<![a-záéíóúüñ])${escapeRe(term)}(?![a-záéíóúüñ])`, "gi");
  const results = [];
  // corpusPres ya viene ordenado de más reciente a más antiguo
  for (const [fecha, texto] of corpusPres) {
    const lower = texto.toLowerCase();
    if (!lower.includes(term)) continue;
    let m;
    re.lastIndex = 0;
    while ((m = re.exec(lower)) !== null) {
      const start = Math.max(0, m.index - KWIC_WINDOW);
      const end   = Math.min(texto.length, m.index + term.length + KWIC_WINDOW);
      results.push({
        fecha,
        ctx: (start > 0 ? "…" : "") + texto.slice(start, end) + (end < texto.length ? "…" : ""),
        link: buildSegmentLink(fecha, texto, m.index, term.length),
      });
    }
  }
  return results;
}

function renderKwicPage() {
  const start = kwicCurrentPage * KWIC_PER_PAGE;
  const end   = Math.min(start + KWIC_PER_PAGE, kwicAllResults.length);
  const total = kwicAllResults.length;
  const pages = Math.ceil(total / KWIC_PER_PAGE);

  $("kwic-results").innerHTML = kwicAllResults.slice(start, end).map(h => `
    <div class="kwic-card">
      <div class="kwic-card-head">
        <span class="kwic-date">${h.fecha}</span>
        ${h.link ? `<a class="kwic-link" href="${h.link}" target="_blank" rel="noopener">Ver en gob.mx ↗</a>` : ""}
      </div>
      <div class="kwic-text">${highlight(h.ctx, kwicTerm)}</div>
    </div>`).join("");

  $("kwic-status").textContent = `${total.toLocaleString("es-MX")} resultado${total !== 1 ? "s" : ""} · mostrando ${start + 1}–${end}`;
  $("kwic-page-info").textContent = `Página ${kwicCurrentPage + 1} de ${pages}`;
  $("kwic-prev").disabled = kwicCurrentPage === 0;
  $("kwic-next").disabled = kwicCurrentPage >= pages - 1;
  $("kwic-pagination").style.display = total > KWIC_PER_PAGE ? "flex" : "none";
}

async function doKwicSearch() {
  const term = $("kwic-input").value.trim().toLowerCase();
  if (!term) return;

  if (/\s/.test(term) === false && term.length < 3) {
    $("kwic-status").textContent = "";
    $("kwic-results").innerHTML = `<p class="kwic-empty">Escribe una palabra de al menos 3 letras.</p>`;
    $("kwic-pagination").style.display = "none";
    return;
  }

  await loadCorpus();

  if (stopwordsSet.has(term)) {
    $("kwic-status").textContent = "";
    $("kwic-results").innerHTML = `<p class="kwic-empty">
      "<strong>${term}</strong>" es una palabra funcional (stopword) y no se indexa.
      Prueba con una palabra de contenido (sustantivo, verbo, adjetivo).</p>`;
    $("kwic-pagination").style.display = "none";
    return;
  }

  kwicTerm = term;
  kwicAllResults = searchCorpus(term);
  kwicCurrentPage = 0;

  if (kwicAllResults.length === 0) {
    $("kwic-status").textContent = "";
    $("kwic-results").innerHTML = `<p class="kwic-empty">Sin resultados para "<strong>${term}</strong>" en los turnos de la presidenta.</p>`;
    $("kwic-pagination").style.display = "none";
    return;
  }

  renderKwicPage();
}

// ── Actores ──────────────────────────────────────────────────────────────────

let actorChart       = null;
let selectedActor    = null;
let currentGran      = "mes";
let currentMetric    = "intervenciones";   // "intervenciones" | "apariciones"
let speakersData     = null;

function parseName(nombre) {
  const parts = nombre.split(",").map(s => s.trim());
  if (parts.length === 1) return { cargo: "", nombre: parts[0] };
  return { cargo: parts[0], nombre: parts.slice(1).join(",").trim() };
}

// Rango temporal completo del corpus (lo fija init desde corpus_stats)
let corpusMeses = [];   // ["2024-10", "2024-11", …]
let corpusAnios = [];   // ["2024", "2025", "2026"]

function buildActorTimeline(fechas, gran, metric) {
  // fechas: una entrada por turno (intervención). Para "apariciones" se
  // cuentan días/conferencias únicos por periodo.
  const buckets = {};
  fechas.forEach(f => {
    const key = gran === "anio" ? f.slice(0, 4) : f.slice(0, 7);
    if (metric === "apariciones") {
      (buckets[key] ||= new Set()).add(f);
    } else {
      buckets[key] = (buckets[key] || 0) + 1;
    }
  });

  // Eje completo y continuo desde octubre 2024 hasta la última actualización,
  // rellenando con cero los periodos sin actividad.
  const ejeKeys = gran === "anio" ? corpusAnios : corpusMeses;
  const labels  = ejeKeys.map(k => gran === "anio" ? k : formatMonth(k));
  const data    = ejeKeys.map(k => {
    const b = buckets[k];
    if (!b) return 0;
    return metric === "apariciones" ? b.size : b;
  });
  return { labels, data };
}

function renderActorChart(nombre, gran, metric) {
  const fechas = speakersData.actor_fechas[nombre];
  if (!fechas) return;

  const { labels, data } = buildActorTimeline(fechas, gran, metric);
  const parsed = parseName(nombre);
  const metricLabel = metric === "apariciones" ? "Apariciones (conferencias)" : "Intervenciones (turnos)";

  $("actors-chart-title").textContent = parsed.nombre || nombre;
  $("actors-hint").style.display = "none";
  $("actors-chart-wrap").style.display = "block";

  if (actorChart) {
    actorChart.data.labels   = labels;
    actorChart.data.datasets[0].data = data;
    actorChart.data.datasets[0].label = metricLabel;
    actorChart.options.scales.y.title.text = metricLabel;
    actorChart.update();
    return;
  }

  actorChart = new Chart($("chart-actor"), {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: metricLabel,
        data,
        backgroundColor: ACTOR_COLOR + "CC",
        borderColor: ACTOR_COLOR,
        borderWidth: 1,
        borderRadius: 3,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { maxRotation: 45, font: { size: 11 } } },
        y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: "#F0F0F0" },
             title: { display: true, text: metricLabel } },
      },
    },
  });
}

function renderActorsList(speakers) {
  speakersData = speakers;
  const list   = $("actors-list");
  list.innerHTML = "";

  speakers.top_funcionarios.forEach((actor, i) => {
    const { cargo, nombre } = parseName(actor.nombre);
    const item = document.createElement("div");
    item.className = "actor-item";
    item.dataset.nombre = actor.nombre;
    item.innerHTML = `
      <span class="actor-rank">${i + 1}</span>
      <div class="actor-info">
        <div class="actor-name" title="${actor.nombre}">${nombre || actor.nombre}</div>
        ${cargo ? `<div class="actor-cargo">${cargo}</div>` : ""}
      </div>
      <span class="actor-count">${actor.apariciones}</span>`;

    item.addEventListener("click", () => {
      document.querySelectorAll(".actor-item").forEach(el => el.classList.remove("selected"));
      item.classList.add("selected");
      selectedActor = actor.nombre;
      renderActorChart(actor.nombre, currentGran, currentMetric);
    });

    list.appendChild(item);
  });

  // Seleccionar el primero por defecto
  const firstItem = list.querySelector(".actor-item");
  if (firstItem) firstItem.click();
}

// ── Bootstrap ────────────────────────────────────────────────────────────────

async function init() {
  try {
    const [stats, topics, speakers] = await Promise.all([
      loadJSON("json/corpus_stats.json"),
      loadJSON("json/topics.json"),
      loadJSON("json/speakers.json"),
    ]);

    const meses = stats.meses;
    corpusMeses = meses;
    corpusAnios = [...new Set(meses.map(m => m.slice(0, 4)))].sort();

    renderHeroStats(stats);
    renderVoz(stats, speakers);
    renderTopicos(topics, meses);
    renderEncuadre(speakers, meses, "presidenta");
    renderActorsList(speakers);

    // Corpus selector (encuadre)
    document.querySelectorAll(".pill").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".pill").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        renderEncuadre(speakers, meses, btn.dataset.corpus);
      });
    });

    // Granularidad actores
    document.querySelectorAll(".gran-pill").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".gran-pill").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        currentGran = btn.dataset.gran;
        if (selectedActor) renderActorChart(selectedActor, currentGran, currentMetric);
      });
    });

    // Métrica actores (intervenciones vs apariciones)
    document.querySelectorAll(".metric-pill").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".metric-pill").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        currentMetric = btn.dataset.metric;
        if (selectedActor) renderActorChart(selectedActor, currentGran, currentMetric);
      });
    });

  } catch (err) {
    console.error("Error cargando datos:", err);
  }
}

// KWIC events
document.addEventListener("DOMContentLoaded", () => {
  init();

  $("kwic-btn").addEventListener("click", doKwicSearch);
  $("kwic-input").addEventListener("keydown", e => { if (e.key === "Enter") doKwicSearch(); });
  $("kwic-prev").addEventListener("click", () => { kwicCurrentPage--; renderKwicPage(); window.scrollTo({top: $("kwic").offsetTop - 60, behavior: "smooth"}); });
  $("kwic-next").addEventListener("click", () => { kwicCurrentPage++; renderKwicPage(); window.scrollTo({top: $("kwic").offsetTop - 60, behavior: "smooth"}); });
});
