/* app.js — Análisis del discurso de la mañanera */

"use strict";

// ── Paletas ─────────────────────────────────────────────────────────────────

const TOPIC_COLORS = [
  "#1B4332","#2D6A4F","#40916C","#52B788","#74C69D",
  "#95D5B2","#B7E4C7","#6A994E","#386641","#BC4749",
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

// ── Utilidades ───────────────────────────────────────────────────────────────

const $ = id => document.getElementById(id);

async function loadJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`No se pudo cargar ${path}`);
  return res.json();
}

function formatNum(n) {
  return n.toLocaleString("es-MX");
}

function formatMonth(ym) {
  const [y, m] = ym.split("-");
  const names = ["","Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
  return `${names[+m]} ${y}`;
}

// ── Hero stats ───────────────────────────────────────────────────────────────

function renderHeroStats(stats, topics) {
  $("stat-conf").textContent   = formatNum(stats.total_conferencias);
  $("stat-meses").textContent  = stats.meses.length;
  $("stat-rango").textContent  = `${stats.fecha_inicio.slice(0,7)} → ${stats.fecha_fin.slice(0,7)}`;

  // Conteo de turnos presidenta desde topics (por_fecha keys ≈ conferencias con turno pres)
  const totalTurnos = Object.values(stats.por_fecha)
    .reduce((a, c) => a + (c.presidenta_turns || 0), 0);
  $("stat-turnos").textContent = formatNum(totalTurnos);
}

// ── Distribución de voz ──────────────────────────────────────────────────────

function renderVoz(stats) {
  const meses = stats.meses;
  const tipos = ["presidenta", "pregunta", "funcionario", "otro"];

  // Agrega palabras por tipo por mes
  const porMes = {};
  meses.forEach(m => { porMes[m] = { presidenta: 0, pregunta: 0, funcionario: 0, otro: 0 }; });

  Object.entries(stats.por_fecha).forEach(([fecha, d]) => {
    const m = fecha.slice(0, 7);
    if (!porMes[m]) return;
    porMes[m].presidenta  += d.presidenta_words || 0;
    porMes[m].pregunta    += (d.pregunta_turns || 0) * 30;   // estimación ~30 palabras/pregunta
    porMes[m].funcionario += (d.funcionario_turns || 0) * 60;
    porMes[m].otro        += (d.otro_turns || 0) * 20;
  });

  // Normaliza a porcentaje
  const datasets = tipos.map(tipo => ({
    label: VOZ_LABELS[tipo],
    data: meses.map(m => {
      const total = Object.values(porMes[m]).reduce((a, b) => a + b, 0);
      return total ? Math.round(porMes[m][tipo] / total * 100) : 0;
    }),
    backgroundColor: VOZ_COLORS[tipo],
    borderWidth: 0,
  }));

  new Chart($("chart-voz"), {
    type: "bar",
    data: { labels: meses.map(formatMonth), datasets },
    options: {
      responsive: true,
      plugins: { legend: { position: "bottom" }, tooltip: {
        callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y}%` }
      }},
      scales: {
        x: { stacked: true, grid: { display: false } },
        y: { stacked: true, max: 100, ticks: {
          callback: v => v + "%"
        }, grid: { color: "#F0F0F0" } },
      },
    },
  });
}

// ── Tópicos ──────────────────────────────────────────────────────────────────

function renderTopicos(topics, meses) {
  const labels = meses.map(formatMonth);

  const datasets = topics.topic_labels.map((words, i) => ({
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
    data: { labels, datasets },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { stacked: true, grid: { display: false } },
        y: { stacked: true, max: 100, ticks: { callback: v => v + "%" },
             grid: { color: "#F0F0F0" } },
      },
    },
  });

  // Tabla lateral
  const container = $("topic-words");
  topics.topic_labels.forEach((words, i) => {
    const row = document.createElement("div");
    row.className = "topic-row";
    row.innerHTML = `
      <span class="topic-dot" style="background:${TOPIC_COLORS[i]}"></span>
      <span class="topic-words"><strong>T${i+1}:</strong> ${words.slice(0,6).join(", ")}</span>
    `;
    container.appendChild(row);
  });
}

// ── Heatmap TF-IDF (D3) ──────────────────────────────────────────────────────

function renderHeatmap(tfidf, meses) {
  $("heatmap-loading").remove();

  // Selecciona los 35 términos con mayor varianza temporal (los que más cambian)
  const termFreq = {};
  meses.forEach(m => {
    (tfidf[m] || []).forEach(({ termino, score }) => {
      if (!termFreq[termino]) termFreq[termino] = {};
      termFreq[termino][m] = score;
    });
  });

  // Calcula varianza de cada término
  const termVariance = Object.entries(termFreq).map(([term, scores]) => {
    const vals = meses.map(m => scores[m] || 0);
    const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
    const variance = vals.reduce((a, v) => a + (v - mean) ** 2, 0) / vals.length;
    return { term, variance, scores };
  });

  termVariance.sort((a, b) => b.variance - a.variance);
  const topTerms = termVariance.slice(0, 35).map(t => t.term);

  // Construir matriz
  const data = [];
  topTerms.forEach(term => {
    meses.forEach(m => {
      data.push({ term, mes: m, score: termFreq[term]?.[m] || 0 });
    });
  });

  const margin = { top: 20, right: 20, bottom: 80, left: 160 };
  const cellW = 36, cellH = 20;
  const width  = cellW * meses.length + margin.left + margin.right;
  const height = cellH * topTerms.length + margin.top + margin.bottom;

  const svg = d3.select("#heatmap-container")
    .append("svg")
    .attr("width", width)
    .attr("height", height);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);

  const xScale = d3.scaleBand().domain(meses).range([0, cellW * meses.length]).padding(0.05);
  const yScale = d3.scaleBand().domain(topTerms).range([0, cellH * topTerms.length]).padding(0.05);

  const maxScore = d3.max(data, d => d.score) || 1;
  const color = d3.scaleSequential()
    .domain([0, maxScore])
    .interpolator(d3.interpolate("#F0F9F4", "#1B4332"));

  // Celdas
  g.selectAll("rect")
    .data(data)
    .enter().append("rect")
    .attr("x", d => xScale(d.mes))
    .attr("y", d => yScale(d.term))
    .attr("width", xScale.bandwidth())
    .attr("height", yScale.bandwidth())
    .attr("rx", 2)
    .style("fill", d => d.score > 0 ? color(d.score) : "#F8F9FA");

  // Tooltip básico
  const tip = d3.select("body").append("div")
    .style("position","absolute").style("background","rgba(0,0,0,.78)")
    .style("color","#fff").style("padding","4px 8px").style("border-radius","4px")
    .style("font-size","12px").style("pointer-events","none").style("display","none");

  g.selectAll("rect")
    .on("mouseover", (event, d) => {
      tip.style("display","block")
        .html(`<strong>${d.term}</strong><br>${formatMonth(d.mes)}: ${d.score.toFixed(3)}`);
    })
    .on("mousemove", event => {
      tip.style("left", (event.pageX + 10) + "px").style("top", (event.pageY - 20) + "px");
    })
    .on("mouseout", () => tip.style("display","none"));

  // Eje Y (términos)
  g.append("g").call(d3.axisLeft(yScale).tickSize(0))
    .select(".domain").remove();
  g.selectAll(".tick text").style("font-size","11px").style("fill","#495057");

  // Eje X (meses)
  g.append("g")
    .attr("transform", `translate(0,${cellH * topTerms.length + 4})`)
    .call(d3.axisBottom(xScale).tickFormat(formatMonth).tickSize(0))
    .select(".domain").remove();
  g.selectAll(".tick:last-child text, .tick text")
    .style("font-size","10px").style("fill","#495057")
    .attr("transform","rotate(-45)").attr("text-anchor","end");
}

// ── Encuadre ─────────────────────────────────────────────────────────────────

function renderEncuadre(speakers, meses) {
  const framing = speakers.framing;
  const frames = framing.frames;
  const labels = meses.map(formatMonth);

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

  new Chart($("chart-encuadre"), {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false } },
        y: { title: { display: true, text: "ocurrencias / mil palabras" },
             grid: { color: "#F0F0F0" } },
      },
    },
  });

  // Leyenda manual
  const legend = $("framing-legend");
  frames.forEach(frame => {
    const item = document.createElement("div");
    item.className = "legend-item";
    item.innerHTML = `<span class="legend-dot" style="background:${FRAME_COLORS[frame]}"></span>${FRAME_LABELS[frame]}`;
    legend.appendChild(item);
  });
}

// ── KWIC ─────────────────────────────────────────────────────────────────────

let kwicData = null;

async function loadKwic() {
  if (kwicData) return kwicData;
  $("kwic-results").innerHTML = `<p class="kwic-loading">Cargando índice…</p>`;
  kwicData = await loadJSON("json/kwic.json");
  return kwicData;
}

function highlight(text, word) {
  const re = new RegExp(`(${word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi");
  return text.replace(re, "<mark>$1</mark>");
}

async function doKwicSearch() {
  const term = $("kwic-input").value.trim().toLowerCase();
  const results = $("kwic-results");
  if (!term) return;

  const data = await loadKwic();
  const hits = data[term];

  if (!hits || hits.length === 0) {
    // Buscar términos parecidos
    const similar = Object.keys(data)
      .filter(k => k.startsWith(term.slice(0, 3)))
      .slice(0, 5);
    results.innerHTML = `
      <p class="kwic-empty">No hay ejemplos para "<strong>${term}</strong>".
      ${similar.length ? `Prueba con: ${similar.map(s => `<em>${s}</em>`).join(", ")}.` : ""}
      </p>`;
    return;
  }

  results.innerHTML = hits.map(h => `
    <div class="kwic-card">
      <div class="kwic-date">${h.fecha}</div>
      <div class="kwic-text">${highlight(h.ctx, term)}</div>
    </div>
  `).join("");
}

// ── Actores ──────────────────────────────────────────────────────────────────

function renderSpeakers(speakers) {
  const grid = $("speakers-grid");
  const top = speakers.top_funcionarios;
  const maxCount = top[0]?.apariciones || 1;

  top.forEach(({ nombre, apariciones }) => {
    const pct = Math.round(apariciones / maxCount * 100);
    const div = document.createElement("div");
    div.className = "speaker-bar-wrap";
    div.innerHTML = `
      <div class="speaker-name">${nombre.split(",").slice(0,2).join(",")}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
      <div class="bar-count">${apariciones} apariciones</div>
    `;
    grid.appendChild(div);
  });
}

// ── Bootstrap ────────────────────────────────────────────────────────────────

async function init() {
  try {
    const [stats, wordFreq, tfidf, topics, speakers] = await Promise.all([
      loadJSON("json/corpus_stats.json"),
      loadJSON("json/word_freq_monthly.json"),
      loadJSON("json/tfidf_monthly.json"),
      loadJSON("json/topics.json"),
      loadJSON("json/speakers.json"),
    ]);

    const meses = stats.meses;

    renderHeroStats(stats, topics);
    renderVoz(stats);
    renderTopicos(topics, meses);
    renderHeatmap(tfidf, meses);
    renderEncuadre(speakers, meses);
    renderSpeakers(speakers);

  } catch (err) {
    console.error("Error cargando datos:", err);
  }
}

// KWIC events
document.addEventListener("DOMContentLoaded", () => {
  init();

  $("kwic-btn").addEventListener("click", doKwicSearch);
  $("kwic-input").addEventListener("keydown", e => {
    if (e.key === "Enter") doKwicSearch();
  });
});
