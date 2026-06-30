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

// ── Stats compactas (barra superior) ─────────────────────────────────────────

function renderTopbarStats(stats) {
  const totalTurnos = Object.values(stats.por_fecha)
    .reduce((a, c) => a + (c.presidenta_turns || 0), 0);
  $("topbar-stats").textContent =
    `${formatNum(stats.total_conferencias)} conferencias · ` +
    `${formatNum(totalTurnos)} turnos · ` +
    `${stats.fecha_inicio.slice(0,7)}–${stats.fecha_fin.slice(0,7)}`;
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
  [corpusPres, stopwordsSet] = await Promise.all([
    loadJSON("json/corpus_presidenta.json"),
    loadJSON("json/stopwords.json").then(arr => new Set(arr)),
  ]);
  $("kwic-status").textContent = "";
}

// Construye un enlace al segmento exacto de la conferencia usando Text
// Fragments de Chrome (#:~:text=). Usa la ORACIÓN que contiene el término:
// las oraciones no cruzan párrafos, y los Text Fragments no casan texto que
// cruza límites de bloque (esa era la causa de que algunos no saltaran).
const SENT_END = /[.?!…]/;

function buildSegmentLink(fecha, texto, idx, termLen) {
  const base = fechaUrl[fecha];
  if (!base) return null;

  // Inicio de la oración: tras el anterior signo de fin de oración
  let s = idx;
  while (s > 0 && !SENT_END.test(texto[s - 1])) s--;
  while (s < idx && /\s/.test(texto[s])) s++;        // saltar espacios
  // Fin de la oración: hasta el siguiente signo (incluido)
  let e = idx + termLen;
  while (e < texto.length && !SENT_END.test(texto[e])) e++;
  if (e < texto.length) e++;

  const frase = texto.slice(s, e).trim();
  if (!frase) return base;

  // Oración corta → fragmento de cadena única. Larga → forma de rango
  // textStart,textEnd (ambos anclajes dentro de la misma oración/bloque),
  // para respetar el límite de longitud de la URL.
  const words = frase.split(/\s+/);
  if (frase.length <= 160 || words.length <= 12) {
    return `${base}#:~:text=${encodeURIComponent(frase)}`;
  }
  const start = words.slice(0, 8).join(" ");
  const end   = words.slice(-6).join(" ");
  return `${base}#:~:text=${encodeURIComponent(start)},${encodeURIComponent(end)}`;
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
    $("kwic-trend").style.display = "none";
    return;
  }

  renderKwicTrend(term, kwicAllResults);
  renderKwicPage();
}

// Tendencia temporal del término: ocurrencias por mes sobre el rango completo
let kwicTrendChart = null;

function renderKwicTrend(term, results) {
  const porMes = {};
  results.forEach(r => { const m = r.fecha.slice(0, 7); porMes[m] = (porMes[m] || 0) + 1; });
  const labels = corpusMeses.map(formatMonth);
  const data   = corpusMeses.map(m => porMes[m] || 0);

  $("kwic-trend-title").textContent = `Menciones de «${term}» por mes (turnos de la presidenta)`;
  $("kwic-trend").style.display = "block";

  if (kwicTrendChart) {
    kwicTrendChart.data.labels = labels;
    kwicTrendChart.data.datasets[0].data = data;
    kwicTrendChart.update();
    return;
  }

  kwicTrendChart = new Chart($("chart-kwic-trend"), {
    type: "bar",
    data: { labels, datasets: [{
      data, backgroundColor: "#2D6A4FCC", borderColor: "#2D6A4F",
      borderWidth: 1, borderRadius: 3,
    }]},
    options: {
      responsive: true,
      plugins: { legend: { display: false },
        tooltip: { callbacks: { label: ctx => `${ctx.parsed.y} menciones` } } },
      scales: {
        x: { grid: { display: false }, ticks: { maxRotation: 45, font: { size: 10 } } },
        y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: "#F0F0F0" } },
      },
    },
  });
}

// ── Actores ──────────────────────────────────────────────────────────────────

let actorChart       = null;
let selectedActor    = null;
let currentGran      = "mes";
let currentMetric    = "intervenciones";   // "intervenciones" | "apariciones"
let currentCat       = "todos";            // filtro por tipo de funcionario
let currentActorKeys = [];                 // claves del eje del chart actual
let speakersData     = null;

const CAT_LABEL = {
  todos: "funcionarios", secretarios: "secretarios",
  gobernadores: "gobernadores", directores: "directores", otros: "otros",
};

function parseName(nombre) {
  const parts = nombre.split(",").map(s => s.trim());
  if (parts.length === 1) return { cargo: "", nombre: parts[0] };
  return { cargo: parts[0], nombre: parts.slice(1).join(",").trim() };
}

// Funcionarios de la categoría activa
function actoresDeCategoria(cat) {
  return speakersData.top_funcionarios.filter(a => cat === "todos" || a.categoria === cat);
}

// Fechas (una por turno) del objeto activo: un actor concreto o el AGREGADO
// de toda la categoría seleccionada.
function getActiveFechas() {
  if (selectedActor) return speakersData.actor_fechas[selectedActor] || [];
  return actoresDeCategoria(currentCat).flatMap(a => speakersData.actor_fechas[a.nombre] || []);
}

function getActiveTitle() {
  if (selectedActor) return parseName(selectedActor).nombre || selectedActor;
  const n = actoresDeCategoria(currentCat).length;
  return `Todos los ${CAT_LABEL[currentCat]} (${n}) — agregado`;
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
  return { labels, data, keys: ejeKeys };
}

// Dibuja la gráfica del objeto activo (actor o agregado de la categoría)
function renderActorChart() {
  const fechas = getActiveFechas();
  const { labels, data, keys } = buildActorTimeline(fechas, currentGran, currentMetric);
  currentActorKeys = keys;
  const metricLabel = currentMetric === "apariciones" ? "Apariciones (conferencias)" : "Intervenciones (turnos)";

  $("actors-chart-title").textContent = getActiveTitle();
  $("actors-tip").style.display = "block";
  $("actors-chart-wrap").style.display = "block";
  $("actor-detail").innerHTML = "";   // limpiar detalle previo

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
      onClick: (evt, els) => {
        if (els.length) showActorDetail(currentActorKeys[els[0].index]);
      },
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { maxRotation: 45, font: { size: 11 } } },
        y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: "#F0F0F0" },
             title: { display: true, text: metricLabel } },
      },
    },
  });
}

// Al hacer clic en una barra: lista las fechas (conferencias) de ese periodo
// con enlace a la versión estenográfica en gob.mx. Sirve para un actor o para
// el agregado de la categoría.
function showActorDetail(periodKey) {
  if (!periodKey) return;
  const fechas = getActiveFechas()
    .filter(f => (currentGran === "anio" ? f.slice(0, 4) : f.slice(0, 7)) === periodKey);

  const porFecha = {};
  fechas.forEach(f => { porFecha[f] = (porFecha[f] || 0) + 1; });
  const dias = Object.keys(porFecha).sort().reverse();

  const periodoLabel = currentGran === "anio" ? periodKey : formatMonth(periodKey);
  const totalInterv = fechas.length;
  const resumen = currentMetric === "apariciones"
    ? `${dias.length} conferencia${dias.length !== 1 ? "s" : ""}`
    : `${totalInterv} intervencion${totalInterv !== 1 ? "es" : ""} en ${dias.length} conferencia${dias.length !== 1 ? "s" : ""}`;

  $("actor-detail").innerHTML = `
    <div class="detail-head">${periodoLabel} · ${resumen}</div>
    <div class="detail-list">
      ${dias.map(f => {
        const url = fechaUrl[f];
        const cnt = porFecha[f] > 1 ? `<span class="detail-count">${porFecha[f]} intervenciones</span>` : "";
        return `<div class="detail-row">
          <span class="detail-fecha">${f}${cnt}</span>
          ${url ? `<a class="detail-link" href="${url}" target="_blank" rel="noopener">Ver en gob.mx ↗</a>` : ""}
        </div>`;
      }).join("")}
    </div>`;
}

// Cambia de categoría: rellena la lista y muestra el AGREGADO por defecto.
function selectCategoria(cat) {
  currentCat = cat;
  selectedActor = null;
  const actores = actoresDeCategoria(cat);

  $("actors-list-head").textContent =
    `${actores.length} ${CAT_LABEL[cat]} · clic para uno`;

  const list = $("actors-list");
  list.innerHTML = "";
  actores.forEach((actor, i) => {
    const { cargo, nombre } = parseName(actor.nombre);
    const item = document.createElement("div");
    item.className = "actor-item";
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
      renderActorChart();
    });

    list.appendChild(item);
  });

  // Por defecto: agregado de toda la categoría (ningún actor seleccionado)
  renderActorChart();
}

// ── Bootstrap ────────────────────────────────────────────────────────────────

// Router de vistas: cada gráfica se inicializa solo la primera vez que se
// muestra su vista (Chart.js necesita un canvas visible para medir tamaño).
const viewInitializers = {};
const viewsReady = new Set(["kwic"]);   // KWIC no necesita init previo

function showView(name) {
  document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === name));
  document.querySelectorAll("nav a").forEach(a => a.classList.toggle("active", a.dataset.view === name));
  if (!viewsReady.has(name) && viewInitializers[name]) {
    viewInitializers[name]();
    viewsReady.add(name);
  }
  window.scrollTo({ top: 0, behavior: "auto" });
}

async function init() {
  try {
    const [stats, topics, speakers, fu] = await Promise.all([
      loadJSON("json/corpus_stats.json"),
      loadJSON("json/topics.json"),
      loadJSON("json/speakers.json"),
      loadJSON("json/fecha_url.json"),
    ]);
    fechaUrl = fu;   // disponible para KWIC y para el detalle de Actores

    const meses = stats.meses;
    corpusMeses = meses;
    corpusAnios = [...new Set(meses.map(m => m.slice(0, 4)))].sort();

    renderTopbarStats(stats);

    // Inicializadores diferidos por vista
    viewInitializers.voz      = () => renderVoz(stats, speakers);
    viewInitializers.topicos  = () => renderTopicos(topics, meses);
    viewInitializers.encuadre = () => {
      renderEncuadre(speakers, meses, "presidenta");
      document.querySelectorAll(".pill").forEach(btn => {
        btn.addEventListener("click", () => {
          document.querySelectorAll(".pill").forEach(b => b.classList.remove("active"));
          btn.classList.add("active");
          renderEncuadre(speakers, meses, btn.dataset.corpus);
        });
      });
    };
    viewInitializers.actores = () => {
      speakersData = speakers;
      selectCategoria(currentCat);   // muestra el agregado de "Todos" por defecto
      document.querySelectorAll(".cat-pill").forEach(btn => {
        btn.addEventListener("click", () => {
          document.querySelectorAll(".cat-pill").forEach(b => b.classList.remove("active"));
          btn.classList.add("active");
          selectCategoria(btn.dataset.cat);   // agregado de la categoría por defecto
        });
      });
      document.querySelectorAll(".gran-pill").forEach(btn => {
        btn.addEventListener("click", () => {
          document.querySelectorAll(".gran-pill").forEach(b => b.classList.remove("active"));
          btn.classList.add("active");
          currentGran = btn.dataset.gran;
          renderActorChart();
        });
      });
      document.querySelectorAll(".metric-pill").forEach(btn => {
        btn.addEventListener("click", () => {
          document.querySelectorAll(".metric-pill").forEach(b => b.classList.remove("active"));
          btn.classList.add("active");
          currentMetric = btn.dataset.metric;
          renderActorChart();
        });
      });
    };

    // Navegación entre vistas
    document.querySelectorAll("nav a[data-view]").forEach(a => {
      a.addEventListener("click", e => { e.preventDefault(); showView(a.dataset.view); });
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
  $("kwic-prev").addEventListener("click", () => { kwicCurrentPage--; renderKwicPage(); window.scrollTo({top: 0, behavior: "smooth"}); });
  $("kwic-next").addEventListener("click", () => { kwicCurrentPage++; renderKwicPage(); window.scrollTo({top: 0, behavior: "smooth"}); });
});
