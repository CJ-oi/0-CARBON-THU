(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const fmt = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });
  const svgNS = "http://www.w3.org/2000/svg";

  const state = {
    data: null,
    archive: [],
    reportIndex: { reports: [] },
    geometry: null,
    runtime: {},
    mapFilter: "全国",
    selectedPark: null,
    updateTopic: "全部",
    updateLimit: 9,
    selectedFields: new Set(loadStored("zcp_checked_fields", [])),
    tasks: [],
    lens: "管委会",
    gapRows: [],
    reductionAdvice: [],
    selectedMeasures: new Set(),
    measureLimit: 12,
    dbLimit: 25,
    dbRows: [],
    projects: [],
    lastFeasibility: null,
    leafletMap: null,
    leafletMarkerLayer: null,
    leafletMarkers: new Map(),
    leafletTileErrors: 0,
    mapMode: "svg",
  };

  const stakeholderLenses = {
    "管委会": ["确认法定建设边界、纳入企业和基准年", "建立跨部门数据责任表和版本台账", "以项目清单跟踪投资、减排、责任主体和验收材料"],
    "园区企业": ["先做计量、设备效率和工艺运行优化", "提供与园区边界一致的能源和排放活动数据", "核实项目投资、停产影响、年度节省和测量验证边界"],
    "能源运营": ["形成电、热、冷、气和可再生能源平衡", "核对负荷曲线、网架约束和供能可靠性", "明确计量结算、偏差责任、交易责任和环境属性"],
    "公共设施": ["核查污水、再生水、蒸汽、固废和余热协同", "识别园区内可共享的资源流和公共设施能力", "建立公共项目收益分配与节能量验证规则"],
    "监管评估": ["核对指标适用范围、统计边界和因子版本", "区分建设名单、过程监测和验收结论", "保留原始材料、复核记录和版本差异"],
    "研究评估": ["公开数据用于结构比较和假设提出，不替代园区台账", "不以采集频次替代建设绩效", "对关键技术和经济参数开展敏感性分析"],
  };

  const noRegretTerms = ["计量", "能碳管理", "电机", "泵", "风机", "空压", "蒸汽", "凝结水", "余热", "余压", "水回用", "维护", "工业共生"];
  const conditionalTerms = ["光伏", "绿电", "储能", "微电网", "热泵", "电锅炉", "电窑炉", "氢"];
  const categoryOrder = ["园区建设", "技术与设施", "项目与投融资", "政策与标准", "数据与评估", "其他重要动态"];

  function loadStored(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key) || JSON.stringify(fallback)); }
    catch (_) { return fallback; }
  }

  function saveStored(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) { /* local storage is optional */ }
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
  }

  function toast(message) {
    const el = $("#toast");
    if (!el) return;
    el.textContent = message;
    el.classList.add("show");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => el.classList.remove("show"), 2400);
  }

  function csvCell(value) {
    const text = String(value ?? "");
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }

  function downloadText(filename, text, mime = "text/plain;charset=utf-8") {
    const blob = new Blob(["\ufeff", text], { type: mime });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    toast(`已生成 ${filename}`);
  }

  function downloadCsv(filename, headers, rows) {
    downloadText(filename, [headers, ...rows].map(row => row.map(csvCell).join(",")).join("\n"), "text/csv;charset=utf-8");
  }

  function n(value, fallback = null) {
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  }

  function fieldValue(id) {
    const el = $("#" + id);
    return el ? n(el.value, null) : null;
  }

  function priorityClass(value) {
    const text = String(value || "P2");
    if (text.startsWith("P0")) return "P0";
    if (text.startsWith("P1")) return "P1";
    return "P2";
  }

  function measureType(row) {
    const text = [row["一级方向"], row["二级措施"], row["对象/工艺"], row["主要约束"], row["备注"]].join(" ");
    if (conditionalTerms.some(term => text.includes(term))) return "条件型";
    if (noRegretTerms.some(term => text.includes(term))) return "无悔型";
    return "战略型";
  }

  async function fetchJson(url, fallback = null) {
    if (window.__ZCP_EMBEDDED__ && Object.prototype.hasOwnProperty.call(window.__ZCP_EMBEDDED__, url)) return window.__ZCP_EMBEDDED__[url];
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) return fallback;
      return await response.json();
    } catch (_) {
      return fallback;
    }
  }

  async function loadData() {
    const [dashboard, curatedArchive, rawArchive, reportIndex, geometry, runtime] = await Promise.all([
      fetchJson("data/dashboard.json"),
      fetchJson("data/curated_archive.json"),
      fetchJson("data/archive.json", []),
      fetchJson("data/report_index.json", { reports: [] }),
      fetchJson("assets/maps/map_geometry.json"),
      fetchJson("data/runtime_config.json", {}),
    ]);
    if (!dashboard) throw new Error("dashboard.json 未能加载");
    state.data = dashboard;
    state.archive = Array.isArray(curatedArchive) ? curatedArchive : (Array.isArray(rawArchive) ? rawArchive : dashboard.updates || []);
    state.reportIndex = reportIndex || { reports: [] };
    state.geometry = geometry;
    state.runtime = runtime || {};
    state.data.updates = state.archive;
  }

  function initMeta() {
    const meta = state.data.meta || {};
    const counts = meta.counts || {};
    const version = meta.latest_record_date || meta.data_version || "—";
    $("#dataVersion").textContent = version;
    $("#footerVersion").textContent = version;
    $("#updateSchedule").textContent = `本次数据生成于 ${String(meta.generated_at || "—").replace("T", " ").slice(0, 19)}；公开来源按计划自动检查。`;
    const kpis = [
      ["国内园区", counts.domestic_parks],
      ["国际案例", counts.international_cases],
      ["有效公开记录", counts.archive_records],
      ["待准备字段", counts.required_fields],
      ["减排设施指南", counts.technology_measures],
      ["可正式核算园区", counts.formal_accounting_ready],
    ];
    $("#kpiGrid").innerHTML = kpis.map(([label, value]) => `<div class="kpi"><strong>${fmt.format(value || 0)}</strong><span>${escapeHtml(label)}</span></div>`).join("");

    const curation = meta.curation || {};
    const qualityRows = [
      ["进入公开页", counts.archive_records || curation.included || 0],
      ["合并重复", counts.duplicates_collapsed || curation.duplicates_collapsed || 0],
      ["排除低相关", counts.excluded_low_relevance || curation.excluded_low_relevance || 0],
      ["可正式核算", counts.formal_accounting_ready || 0],
    ];
    $("#qualityStrip").innerHTML = qualityRows.map(([label, value]) => `<div class="quality-item"><strong>${fmt.format(value)}</strong><span>${escapeHtml(label)}</span></div>`).join("");
    configureLinks();
  }

  function configureLinks() {
    const issues = state.runtime.issues_url || "https://github.com/CJ-oi/0-CARBON-THU/issues/new/choose";
    [$("#issueLink"), $("#coordinateIssue")].filter(Boolean).forEach(link => { link.href = issues; link.target = "_blank"; link.rel = "noopener"; });
  }

  // ---------------------------------------------------------------------------
  // Map: one projection for land geometry and markers
  // ---------------------------------------------------------------------------
  function mercatorY(lat) {
    const limited = Math.max(-85, Math.min(85, Number(lat)));
    const rad = limited * Math.PI / 180;
    return Math.log(Math.tan(Math.PI / 4 + rad / 2));
  }

  function currentMapBounds() {
    const key = state.mapFilter === "全球" ? "全球" : state.mapFilter;
    const fallback = key === "全球"
      ? { west: -180, east: 180, south: -58, north: 84 }
      : key === "广东"
        ? { west: 108.8, east: 118.2, south: 19, north: 26.2 }
        : { west: 72, east: 136.5, south: 17, north: 54.5 };
    return (state.geometry && state.geometry.views && state.geometry.views[key]) || fallback;
  }

  function projectPoint(lon, lat, bounds = currentMapBounds()) {
    const padX = 24, padY = 20, width = 1000 - padX * 2, height = 600 - padY * 2;
    const west = Number(bounds.west), east = Number(bounds.east);
    const yNorth = mercatorY(bounds.north), ySouth = mercatorY(bounds.south), y = mercatorY(lat);
    return {
      x: padX + ((Number(lon) - west) / (east - west)) * width,
      y: padY + ((yNorth - y) / (yNorth - ySouth)) * height,
    };
  }

  function ringToPath(ring, bounds) {
    let path = "", previousLon = null, segmentOpen = false;
    ring.forEach(([lon, lat]) => {
      const p = projectPoint(lon, lat, bounds);
      const crossesDateline = previousLon !== null && Math.abs(Number(lon) - previousLon) > 180;
      if (crossesDateline && segmentOpen) {
        path += "Z";
        segmentOpen = false;
      }
      if (!segmentOpen) {
        path += `M${p.x.toFixed(2)},${p.y.toFixed(2)}`;
        segmentOpen = true;
      } else {
        path += `L${p.x.toFixed(2)},${p.y.toFixed(2)}`;
      }
      previousLon = Number(lon);
    });
    return segmentOpen ? path + "Z" : path;
  }

  function geometryToPath(geometry, bounds) {
    if (!geometry) return "";
    if (geometry.type === "Polygon") return geometry.coordinates.map(ring => ringToPath(ring, bounds)).join("");
    if (geometry.type === "MultiPolygon") return geometry.coordinates.flatMap(polygon => polygon.map(ring => ringToPath(ring, bounds))).join("");
    return "";
  }

  function featureIntersectsView(feature, bounds) {
    const geometry = feature && feature.geometry;
    if (!geometry) return false;
    const points = geometry.type === "Polygon" ? geometry.coordinates.flat(1) : geometry.coordinates.flat(2);
    return points.some(([lon, lat]) => lon >= bounds.west - 12 && lon <= bounds.east + 12 && lat >= bounds.south - 8 && lat <= bounds.north + 8);
  }

  function renderMapGraticule(base, bounds) {
    const spacing = state.mapFilter === "全球" ? { lon: 30, lat: 20 } : state.mapFilter === "广东" ? { lon: 2, lat: 1 } : { lon: 10, lat: 5 };
    const startLon = Math.ceil(bounds.west / spacing.lon) * spacing.lon;
    const startLat = Math.ceil(bounds.south / spacing.lat) * spacing.lat;
    for (let lon = startLon; lon <= bounds.east; lon += spacing.lon) {
      const top = projectPoint(lon, bounds.north, bounds);
      const bottom = projectPoint(lon, bounds.south, bounds);
      const line = document.createElementNS(svgNS, "line");
      line.setAttribute("x1", top.x); line.setAttribute("y1", top.y); line.setAttribute("x2", bottom.x); line.setAttribute("y2", bottom.y);
      line.setAttribute("class", "map-gridline"); base.appendChild(line);
    }
    for (let lat = startLat; lat <= bounds.north; lat += spacing.lat) {
      const left = projectPoint(bounds.west, lat, bounds);
      const right = projectPoint(bounds.east, lat, bounds);
      const line = document.createElementNS(svgNS, "line");
      line.setAttribute("x1", left.x); line.setAttribute("y1", left.y); line.setAttribute("x2", right.x); line.setAttribute("y2", right.y);
      line.setAttribute("class", "map-gridline"); base.appendChild(line);
    }
  }

  function renderMapBase() {
    const base = $("#mapBase");
    base.replaceChildren();
    if (!state.geometry) {
      const text = document.createElementNS(svgNS, "text");
      text.setAttribute("x", "500"); text.setAttribute("y", "300"); text.setAttribute("text-anchor", "middle");
      text.textContent = "地图边界数据未加载";
      base.appendChild(text);
      return;
    }
    const bounds = currentMapBounds();
    const globalMode = state.mapFilter === "全球";
    renderMapGraticule(base, bounds);
    const features = (state.geometry.world && state.geometry.world.features) || [];
    features.filter(feature => globalMode || featureIntersectsView(feature, bounds)).forEach(feature => {
      const pathData = geometryToPath(feature.geometry, bounds);
      if (!pathData) return;
      const path = document.createElementNS(svgNS, "path");
      path.setAttribute("d", pathData);
      const isChina = ["China", "CHN"].includes(feature.properties && (feature.properties.name || feature.properties.iso_a3));
      if (isChina && !globalMode) return;
      path.setAttribute("class", `map-land ${isChina ? "china" : "neighbor"}`);
      base.appendChild(path);
    });
    if (!globalMode && state.geometry.china) {
      const path = document.createElementNS(svgNS, "path");
      path.setAttribute("d", geometryToPath(state.geometry.china.geometry, bounds));
      path.setAttribute("class", "map-land china");
      base.appendChild(path);
    }
  }

  function mapParks() {
    const query = $("#mapSearch").value.trim().toLowerCase();
    return state.data.parks.filter(park => {
      const domestic = park.scope === "国内园区";
      let inView = false;
      if (state.mapFilter === "全国") inView = domestic;
      else if (state.mapFilter === "国家级") inView = domestic && park.level === "国家级";
      else if (state.mapFilter === "广东") inView = domestic && String(park.province).includes("广东");
      else inView = !domestic;
      const text = [park.name, park.province, park.city, park.country, park.industry].join(" ").toLowerCase();
      return inView && (!query || text.includes(query));
    });
  }

  function parkEvidence(id) {
    return (state.data.evidence && state.data.evidence[id]) || [];
  }

  function markerClass(park) {
    if (park.scope !== "国内园区") return "international";
    return park.level === "国家级" ? "national" : "provincial";
  }

  function renderSvgMapMarkers() {
    const rows = mapParks();
    const markers = $("#mapMarkers");
    markers.replaceChildren();
    $("#mapCount").textContent = `${rows.length} 个园区点位`;
    const labelIds = new Set();
    if (rows.length <= 18) rows.forEach(row => labelIds.add(row.park_id));
    if (state.selectedPark) labelIds.add(state.selectedPark);

    rows.forEach(park => {
      const p = projectPoint(park.lon, park.lat);
      if (p.x < 0 || p.x > 1000 || p.y < 0 || p.y > 600) return;
      const group = document.createElementNS(svgNS, "g");
      group.setAttribute("class", `map-marker-group ${state.selectedPark === park.park_id ? "active" : ""}`);
      group.dataset.parkId = park.park_id;
      group.setAttribute("tabindex", "0");
      group.setAttribute("role", "button");
      group.setAttribute("aria-label", `查看${park.name}`);
      group.setAttribute("transform", `translate(${p.x.toFixed(2)} ${p.y.toFixed(2)})`);

      const halo = document.createElementNS(svgNS, "circle");
      halo.setAttribute("r", state.selectedPark === park.park_id ? "11" : "8");
      halo.setAttribute("class", "map-marker-halo");
      const dot = document.createElementNS(svgNS, "circle");
      dot.setAttribute("r", state.selectedPark === park.park_id ? "5.2" : "4");
      dot.setAttribute("class", `map-marker-dot ${markerClass(park)}`);
      group.append(halo, dot);

      if (labelIds.has(park.park_id)) {
        const label = document.createElementNS(svgNS, "text");
        label.setAttribute("x", "8"); label.setAttribute("y", "-7"); label.setAttribute("class", "map-label");
        label.textContent = park.name.length > 13 ? park.name.slice(0, 13) + "…" : park.name;
        group.appendChild(label);
      }

      group.addEventListener("click", () => selectPark(park.park_id, true));
      group.addEventListener("keydown", event => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); selectPark(park.park_id, true); } });
      group.addEventListener("mousemove", event => showMapTooltip(event, park));
      group.addEventListener("mouseleave", hideMapTooltip);
      markers.appendChild(group);
    });
  }

  function leafletColor(park) {
    if (park.scope !== "国内园区") return "#426d7d";
    return park.level === "国家级" ? "#2f6650" : "#9a6b2f";
  }

  function ensureLeafletMap() {
    const mapElement = $("#leafletMap");
    const fallback = $("#svgMapFallback");
    const loading = $("#mapLoading");

    // 公共网站统一使用仓库内置矢量底图。这样不会依赖第三方瓦片服务，
    // 也不会因网络、区域限制或占位图而出现异常色块。
    if (state.leafletMap && typeof state.leafletMap.remove === "function") {
      state.leafletMap.remove();
      state.leafletMap = null;
      state.leafletMarkerLayer = null;
      state.leafletMarkers.clear();
    }
    if (mapElement) mapElement.hidden = true;
    if (fallback) fallback.hidden = false;
    if (loading) loading.hidden = true;
    state.mapMode = "svg";
    return false;
  }

  function fitLeafletView(rows) {
    if (!state.leafletMap) return;
    const query = $("#mapSearch").value.trim();
    if (query && rows.length === 1) {
      state.leafletMap.setView([Number(rows[0].lat), Number(rows[0].lon)], state.mapFilter === "全球" ? 7 : 10, { animate: false });
      return;
    }
    const bounds = currentMapBounds();
    const viewBounds = window.L.latLngBounds([[bounds.south, bounds.west], [bounds.north, bounds.east]]);
    state.leafletMap.fitBounds(viewBounds, { padding: [14, 14], animate: false, maxZoom: state.mapFilter === "广东" ? 8 : state.mapFilter === "全球" ? 3 : 5 });
  }

  function renderLeafletMarkers(fitView = false) {
    if (!ensureLeafletMap()) return;
    const rows = mapParks();
    state.leafletMarkerLayer.clearLayers();
    state.leafletMarkers.clear();
    const permanentLabels = rows.length <= 18;
    rows.forEach(park => {
      const lat = Number(park.lat), lon = Number(park.lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
      const active = state.selectedPark === park.park_id;
      const marker = window.L.circleMarker([lat, lon], {
        radius: active ? 8 : 6,
        color: active ? "#1f2b26" : "#ffffff",
        weight: active ? 3 : 2,
        fillColor: leafletColor(park),
        fillOpacity: 0.94,
        className: "park-leaflet-marker",
      }).addTo(state.leafletMarkerLayer);
      marker.bindTooltip(`<strong>${escapeHtml(park.name)}</strong><br>${escapeHtml([park.province || park.country, park.city, park.industry].filter(Boolean).join(" · "))}`, {
        direction: "top", offset: [0, -7], opacity: 0.98, className: "park-tooltip", permanent: permanentLabels,
      });
      marker.on("click", () => selectPark(park.park_id, true));
      state.leafletMarkers.set(park.park_id, marker);
    });
    if (fitView) fitLeafletView(rows);
    const loading = $("#mapLoading");
    if (loading && state.leafletTileErrors < 6) setTimeout(() => { loading.hidden = true; }, 1800);
  }

  function renderMapMarkers(_fitView = false) {
    ensureLeafletMap();
    renderSvgMapMarkers();
  }

  function showMapTooltip(event, park) {
    const tooltip = $("#mapTooltip");
    const canvas = $("#mapCanvas").getBoundingClientRect();
    tooltip.innerHTML = `<strong>${escapeHtml(park.name)}</strong><br>${escapeHtml([park.province || park.country, park.city, park.industry].filter(Boolean).join(" · "))}`;
    tooltip.style.left = `${Math.min(canvas.width - 260, Math.max(8, event.clientX - canvas.left + 12))}px`;
    tooltip.style.top = `${Math.min(canvas.height - 90, Math.max(8, event.clientY - canvas.top + 12))}px`;
    tooltip.hidden = false;
  }

  function hideMapTooltip() {
    $("#mapTooltip").hidden = true;
  }

  function renderMap() {
    renderMapBase();
    renderMapMarkers(true);
  }

  function selectPark(id, scroll = false) {
    const park = state.data.parks.find(item => item.park_id === id);
    if (!park) return;
    state.selectedPark = id;
    renderMapMarkers(false);
    if (state.leafletMap) {
      const targetZoom = Math.max(state.leafletMap.getZoom(), state.mapFilter === "全球" ? 6 : 8);
      state.leafletMap.flyTo([Number(park.lat), Number(park.lon)], targetZoom, { duration: 0.45 });
    }
    const evidence = parkEvidence(id);
    const source = park.source_url
      ? `<a class="source-link" href="${escapeHtml(park.source_url)}" target="_blank" rel="noopener">查看名录或原始来源 ↗</a>`
      : "<span>暂无公开来源链接</span>";
    const issueBase = state.runtime.issues_url || "https://github.com/CJ-oi/0-CARBON-THU/issues/new/choose";
    $("#parkDetail").innerHTML = `
      <span class="eyebrow">${escapeHtml(park.list_level || park.scope)}</span>
      <h2>${escapeHtml(park.name)}</h2>
      <p>${escapeHtml([park.country, park.province, park.city, park.industry].filter(Boolean).join(" · "))}</p>
      <div class="detail-meta">
        <div class="meta-cell"><span>建设范围</span><strong>${escapeHtml(park.boundary_type || "待核实")}</strong></div>
        <div class="meta-cell"><span>建设周期</span><strong>${escapeHtml(park.period || "待核实")}</strong></div>
        <div class="meta-cell"><span>坐标精度</span><strong>${escapeHtml(park.coordinate_precision || "近似中心")}</strong></div>
        <div class="meta-cell"><span>坐标复核</span><strong>${escapeHtml(park.coordinate_status || "待复核")}</strong></div>
        <div class="meta-cell"><span>经度</span><strong>${fmt.format(Number(park.lon))}°</strong></div>
        <div class="meta-cell"><span>纬度</span><strong>${fmt.format(Number(park.lat))}°</strong></div>
      </div>
      <div class="detail-block"><h4>当前可用信息</h4><p>${escapeHtml(park.note || "已有名录和位置资料，定量数据仍需核验。")}</p></div>
      <div class="detail-block"><h4>建议先做</h4><p>${escapeHtml(park.focus || "优先确认边界、企业清单和基准年数据。")}</p></div>
      <div class="detail-block"><h4>园区公开事实</h4>${evidence.length ? `<ul>${evidence.slice(0, 5).map(item => `<li>${escapeHtml(item.statement)}<br><span class="caveat">限制：${escapeHtml(item.caveat)}</span>${item.url ? `<br><a class="source-link" href="${escapeHtml(item.url)}" target="_blank" rel="noopener">来源 ↗</a>` : ""}</li>`).join("")}</ul>` : "<p>当前没有可直接关联到该园区的定量公开事实。</p>"}</div>
      <div class="detail-block"><p class="caveat">坐标来源：${escapeHtml(park.coordinate_source || "公开位置整理")}；复核日期：${escapeHtml(park.coordinate_review_date || "—")}。点位不代表法定四至边界。</p>${source}<br><a class="source-link" href="${escapeHtml(issueBase)}" target="_blank" rel="noopener">提交该园区坐标或边界更正 ↗</a></div>`;
    if (scroll && window.innerWidth < 1050) $("#parkDetail").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function initMap() {
    $$(".map-filter").forEach(button => button.addEventListener("click", () => {
      state.mapFilter = button.dataset.mapFilter;
      state.selectedPark = null;
      $$(".map-filter").forEach(item => item.classList.toggle("active", item === button));
      renderMap();
    }));
    $("#mapSearch").addEventListener("input", () => renderMapMarkers(true));
    $("#mapReset").addEventListener("click", () => {
      state.mapFilter = "全国";
      state.selectedPark = null;
      $("#mapSearch").value = "";
      $$(".map-filter").forEach(item => item.classList.toggle("active", item.dataset.mapFilter === "全国"));
      $("#parkDetail").innerHTML = '<div class="detail-placeholder"><span class="eyebrow">园区资料卡</span><h3>选择地图点位</h3><p>这里显示园区层级、产业类型、建设周期、公开事实、坐标精度和资料来源。</p></div>';
      renderMap();
      toast("地图已复位");
    });
    renderMap();
  }

  // ---------------------------------------------------------------------------
  // Curated updates and data quality
  // ---------------------------------------------------------------------------
  function updateCategory(row) {
    return row.category || row.topic || "其他重要动态";
  }

  function renderUpdateFilters() {
    const present = new Set(state.archive.map(updateCategory));
    const categories = ["全部", ...categoryOrder.filter(item => present.has(item)), ...[...present].filter(item => !categoryOrder.includes(item))];
    $("#updateFilters").innerHTML = categories.map(category => `<button type="button" class="topic-filter ${category === state.updateTopic ? "active" : ""}" data-topic="${escapeHtml(category)}">${escapeHtml(category)}</button>`).join("");
    $$(".topic-filter").forEach(button => button.addEventListener("click", () => {
      state.updateTopic = button.dataset.topic;
      state.updateLimit = 9;
      renderUpdateFilters();
      renderUpdates();
    }));
  }

  function filteredUpdates() {
    return state.archive
      .filter(row => state.updateTopic === "全部" || updateCategory(row) === state.updateTopic)
      .sort((a, b) => String(b.published_date || "").localeCompare(String(a.published_date || "")) || n(b.quality_score, 0) - n(a.quality_score, 0));
  }

  function renderUpdates() {
    const all = filteredUpdates();
    const rows = all.slice(0, state.updateLimit);
    $("#updatesGrid").innerHTML = rows.length ? rows.map((row, index) => {
      const related = Array.isArray(row.related_materials) ? row.related_materials.length : 0;
      return `<article class="update-card ${index === 0 && state.updateTopic === "全部" ? "featured" : ""}">
        <div class="meta"><span class="category-badge">${escapeHtml(updateCategory(row))}</span><time>${escapeHtml(row.published_date || "—")}</time></div>
        <h3>${escapeHtml(row.title)}</h3>
        <p>${escapeHtml(row.summary || "")}</p>
        <div class="update-footer"><span>${related ? `已合并 ${related} 条相关转载` : escapeHtml(row.source_level || "公开来源")}</span><a class="source-link" href="${escapeHtml(row.url)}" target="_blank" rel="noopener">${escapeHtml(row.publisher || row.source_name || "原始来源")} ↗</a></div>
      </article>`;
    }).join("") : '<div class="empty-state">当前分类没有通过相关性和去重检查的记录。</div>';
    $("#showMoreUpdates").style.display = state.updateLimit < all.length ? "flex" : "none";
  }

  function initUpdates() {
    renderUpdateFilters();
    renderUpdates();
    $("#showMoreUpdates").addEventListener("click", () => { state.updateLimit += 9; renderUpdates(); });
  }

  function renderBars(target, rows, limit = 12) {
    const slice = (rows || []).slice(0, limit);
    const max = Math.max(1, ...slice.map(row => Number(row.value) || 0));
    $(target).innerHTML = slice.length ? slice.map(row => `<div class="bar-row"><span class="label" title="${escapeHtml(row.name)}">${escapeHtml(row.name)}</span><span class="bar-track"><i class="bar-fill" style="width:${((Number(row.value) || 0) / max * 100).toFixed(1)}%"></i></span><span class="bar-value">${fmt.format(row.value || 0)}</span></div>`).join("") : '<div class="empty-state">暂无数据。</div>';
  }

  function initAnalytics() {
    const analytics = state.data.analytics || {};
    renderBars("#provinceChart", analytics.province, 12);
    renderBars("#industryChart", analytics.industry, 10);
    const topicRows = categoryOrder.map(name => ({ name, value: state.archive.filter(row => updateCategory(row) === name).length })).filter(row => row.value);
    renderBars("#topicChart", topicRows, 10);
    const health = (state.data.source_health && state.data.source_health.counts) || {};
    const labels = { healthy: "正常", failed: "失败", watch: "观察", quarantined: "隔离", unknown: "未检查" };
    $("#sourceHealth").innerHTML = Object.keys(labels).filter(key => health[key] || key === "healthy").map(key => `<div class="health-item"><strong>${fmt.format(health[key] || 0)}</strong><span>${labels[key]}</span></div>`).join("");
    const funnel = analytics.funnel || [];
    const max = Math.max(1, ...funnel.map(row => Number(row.value) || 0));
    $("#funnelChart").innerHTML = funnel.map(row => `<div class="funnel-step" title="${escapeHtml(row.meaning || "")}"><div class="funnel-bar" style="height:${Math.max(5, (Number(row.value) || 0) / max * 155)}px"></div><strong>${fmt.format(row.value || 0)}</strong><span>${escapeHtml(row.name)}</span></div>`).join("");
  }

  // ---------------------------------------------------------------------------
  // Five practical questions
  // ---------------------------------------------------------------------------
  function activatePanel(id) {
    $$(".five-tab").forEach(button => button.classList.toggle("active", button.dataset.panel === id));
    $$(".diagnosis-panel").forEach(panel => panel.classList.toggle("active", panel.id === id));
  }

  function initTabs() {
    $$(".five-tab").forEach(button => button.addEventListener("click", () => activatePanel(button.dataset.panel)));
    $$('[data-open-panel]').forEach(link => link.addEventListener("click", () => {
      activatePanel(link.dataset.openPanel);
      setTimeout(() => $("#workbench").scrollIntoView({ behavior: "smooth", block: "start" }), 40);
    }));
  }

  // Data readiness
  function fieldId(row) { return row.field_id || row["字段ID"] || ""; }
  function fieldPriority(row) { return priorityClass(row["优先级"] || row.priority || "P2"); }
  function fieldName(row) { return row["字段"] || row.name || fieldId(row); }
  function fieldOwner(row) { return row["建议提供部门"] || row.owner || "待明确"; }
  function fieldMinimum(row) { return row["最低口径"] || row.minimum_material || "需提供可追溯材料"; }
  function fieldPurpose(row) { return row["用途"] || row.purpose || "数据核验"; }
  function fieldWeight(row) { return fieldPriority(row) === "P0" ? 3 : fieldPriority(row) === "P1" ? 2 : 1; }

  function updateReadiness() {
    const fields = state.data.fields || [];
    const total = fields.reduce((sum, row) => sum + fieldWeight(row), 0);
    const have = fields.reduce((sum, row) => sum + (state.selectedFields.has(fieldId(row)) ? fieldWeight(row) : 0), 0);
    const score = total ? Math.round(have / total * 100) : 0;
    const missingP0 = fields.filter(row => fieldPriority(row) === "P0" && !state.selectedFields.has(fieldId(row))).length;
    $("#readinessScore").textContent = `${score}%`;
    $("#readinessNote").textContent = missingP0 ? `仍缺 ${missingP0} 项P0字段` : "P0字段已勾选，仍需核验年份、边界、单位和原始凭证";
    saveStored("zcp_checked_fields", [...state.selectedFields]);
  }

  function renderFieldChecklist() {
    $("#fieldChecklist").innerHTML = (state.data.fields || []).map(row => {
      const id = fieldId(row), priority = fieldPriority(row);
      return `<label class="field-row"><input type="checkbox" data-field-id="${escapeHtml(id)}" ${state.selectedFields.has(id) ? "checked" : ""}><span class="priority ${priority}">${priority}</span><span class="field-main"><strong>${escapeHtml(fieldName(row))}</strong><small>${escapeHtml(fieldMinimum(row))} · 用途：${escapeHtml(fieldPurpose(row))}</small></span><span class="field-owner">${escapeHtml(fieldOwner(row))}</span></label>`;
    }).join("");
    $$("#fieldChecklist input").forEach(check => check.addEventListener("change", () => {
      if (check.checked) state.selectedFields.add(check.dataset.fieldId);
      else state.selectedFields.delete(check.dataset.fieldId);
      updateReadiness();
    }));
    updateReadiness();
  }

  function generateTasks() {
    state.tasks = (state.data.fields || []).filter(row => !state.selectedFields.has(fieldId(row))).map((row, index) => ({
      no: index + 1,
      id: fieldId(row),
      priority: fieldPriority(row),
      task: `补充${fieldName(row)}`,
      owner: fieldOwner(row),
      material: fieldMinimum(row),
      purpose: fieldPurpose(row),
      deadline: fieldPriority(row) === "P0" ? "3个工作日" : "5个工作日",
      status: "待提供",
    }));
    $("#taskList").innerHTML = state.tasks.length ? state.tasks.map(task => `<div class="task-item"><strong>${task.no}. [${task.priority}] ${escapeHtml(task.task)}</strong><span>责任：${escapeHtml(task.owner)} · 最低材料：${escapeHtml(task.material)}</span><span>建议时限：${task.deadline} · 用途：${escapeHtml(task.purpose)}</span></div>`).join("") : '<div class="empty-state">当前清单无缺失项。仍需核验统计年份、空间边界、单位和原始凭证。</div>';
    toast(`已生成 ${state.tasks.length} 项补数任务`);
  }

  function initDataReady() {
    renderFieldChecklist();
    $("#checkAllP0").addEventListener("click", () => { (state.data.fields || []).filter(row => fieldPriority(row) === "P0").forEach(row => state.selectedFields.add(fieldId(row))); renderFieldChecklist(); toast("已标记全部P0字段"); });
    $("#clearChecklist").addEventListener("click", () => { state.selectedFields.clear(); state.tasks = []; renderFieldChecklist(); $("#taskList").innerHTML = '<div class="empty-state">点击“生成补数任务”后显示。</div>'; toast("已清空勾选"); });
    $("#generateTasks").addEventListener("click", generateTasks);
    $("#exportTasks").addEventListener("click", () => {
      if (!state.tasks.length) generateTasks();
      downloadCsv("园区数据补齐任务.csv", ["序号", "字段ID", "优先级", "任务", "责任部门", "最低材料", "用途", "建议时限", "状态"], state.tasks.map(task => [task.no, task.id, task.priority, task.task, task.owner, task.material, task.purpose, task.deadline, task.status]));
    });
  }

  // Current state and peers
  function similarity(a, b) {
    let score = 0;
    const reasons = [];
    if (a.industry && a.industry === b.industry) { score += 5; reasons.push("产业类型相同"); }
    if (a.boundary_type && a.boundary_type === b.boundary_type) { score += 2; reasons.push("建设边界相同"); }
    if (a.level && a.level === b.level) { score += 2; reasons.push("名单层级相同"); }
    if (a.province && a.province === b.province) { score += 1; reasons.push("同省"); }
    if (a.period && b.period && String(a.period).slice(0, 4) === String(b.period).slice(0, 4)) { score += 1; reasons.push("启动年份接近"); }
    return { score, reasons };
  }

  function renderStateProfile() {
    const domestic = state.data.parks.filter(park => park.scope === "国内园区");
    const park = state.data.parks.find(item => item.park_id === state.selectedPark) || domestic[0];
    if (!park) return;
    state.selectedPark = park.park_id;
    const evidence = parkEvidence(park.park_id);
    const lens = stakeholderLenses[state.lens] || [];
    $("#currentProfile").innerHTML = `<h3 class="profile-title">${escapeHtml(park.name)}</h3><div class="profile-sub">${escapeHtml([park.province, park.city, park.list_level].filter(Boolean).join(" · "))}</div>
      <div class="profile-facts"><div><span>建设范围</span><strong>${escapeHtml(park.boundary_type || "待核实")}</strong></div><div><span>建设周期</span><strong>${escapeHtml(park.period || "待核实")}</strong></div><div><span>产业类型</span><strong>${escapeHtml(park.industry || "待确认")}</strong></div></div>
      <p>${escapeHtml(park.note || "已登记名录和结构信息，定量绩效仍需园区台账。")}</p>
      <h4>公开事实</h4>${evidence.length ? evidence.map(item => `<div class="evidence-item"><p>${escapeHtml(item.statement)}</p><span class="caveat">${escapeHtml(item.caveat)}</span>${item.url ? `<br><a class="source-link" href="${escapeHtml(item.url)}" target="_blank" rel="noopener">原始来源 ↗</a>` : ""}</div>`).join("") : '<div class="empty-state">暂无完成园区对象关联的定量公开事实。</div>'}
      <div class="lens-content"><strong>${escapeHtml(state.lens)}视角下的下一步</strong><ul>${lens.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>`;
    const peers = domestic.filter(item => item.park_id !== park.park_id).map(item => ({ park: item, ...similarity(park, item) })).sort((a, b) => b.score - a.score || a.park.name.localeCompare(b.park.name, "zh-CN")).slice(0, 5);
    $("#similarParks").innerHTML = `<h4>结构相似园区</h4><p class="profile-sub">仅用于安排调研和案例检索，不是绩效排名。</p>${peers.map(item => `<div class="similar-row"><strong>${escapeHtml(item.park.name)}</strong><br><span>${item.score}分 · ${escapeHtml(item.reasons.join("、") || "基础属性接近")}</span><br><button type="button" class="source-link similar-open" data-id="${escapeHtml(item.park.park_id)}">查看资料卡</button></div>`).join("")}`;
    $$(".similar-open").forEach(button => button.addEventListener("click", () => { state.selectedPark = button.dataset.id; $("#stateParkSelect").value = state.selectedPark; renderStateProfile(); }));
  }

  function initCurrent() {
    const domestic = state.data.parks.filter(park => park.scope === "国内园区");
    $("#stateParkSelect").innerHTML = domestic.map(park => `<option value="${escapeHtml(park.park_id)}">${escapeHtml(park.name)}</option>`).join("");
    state.selectedPark = state.selectedPark || domestic[0]?.park_id || null;
    $("#lensButtons").innerHTML = Object.keys(stakeholderLenses).map(name => `<button type="button" class="lens-button ${name === state.lens ? "active" : ""}" data-lens="${escapeHtml(name)}">${escapeHtml(name)}</button>`).join("");
    $("#stateParkSelect").value = state.selectedPark || "";
    $("#stateParkSelect").addEventListener("change", event => { state.selectedPark = event.target.value; renderStateProfile(); });
    $$(".lens-button").forEach(button => button.addEventListener("click", () => { state.lens = button.dataset.lens; $$(".lens-button").forEach(item => item.classList.toggle("active", item === button)); renderStateProfile(); }));
    $("#exportParkProfile").addEventListener("click", () => {
      const park = state.data.parks.find(item => item.park_id === state.selectedPark);
      if (!park) return;
      const evidence = parkEvidence(park.park_id);
      let markdown = `# ${park.name}公开资料卡\n\n- 地区：${[park.province, park.city].filter(Boolean).join(" ")}\n- 名单层级：${park.list_level || "—"}\n- 建设范围：${park.boundary_type || "待核实"}\n- 建设周期：${park.period || "待核实"}\n- 产业类型：${park.industry || "待确认"}\n- 数据状态：${park.status || "公开信息"}\n- 坐标精度：${park.coordinate_precision || "近似中心"}\n- 坐标说明：${park.coordinate_status || "待复核"}\n- 建议先做：${park.focus || "—"}\n- 名录来源：${park.source_url || "—"}\n\n## 公开事实\n`;
      markdown += evidence.length ? evidence.map(item => `- ${item.statement}\n  - 限制：${item.caveat}\n  - 来源：${item.url || "—"}`).join("\n") : "- 暂无完成对象关联的定量事实。";
      downloadText(`${park.name}_公开资料卡.md`, markdown, "text/markdown;charset=utf-8");
    });
    renderStateProfile();
  }

  // Gap calculation
  function runGap(showToast = true) {
    const missing = [];
    if (!$("#boundaryConfirmed").checked) missing.push("同一园区边界和同一自然年");
    [["energyTotal", "综合能源消费量"], ["scope1Total", "范围一排放"], ["scope2Total", "范围二排放"], ["processTotal", "工业过程排放"]].forEach(([id, label]) => { if (fieldValue(id) === null) missing.push(label); });
    if (missing.length) {
      state.gapRows = [];
      $("#gapResult").innerHTML = `<div class="empty-state"><strong>暂不形成达标结论</strong><br>还需补充：${escapeHtml(missing.join("、"))}。<br>请先回到“数据够不够”形成补数任务。</div>`;
      if (showToast) toast("输入不足，已停止正式核算");
      return null;
    }
    const energy = fieldValue("energyTotal");
    if (!(energy > 0)) { if (showToast) toast("综合能源消费量必须大于0"); return null; }
    const scope1 = fieldValue("scope1Total") || 0;
    const scope2 = fieldValue("scope2Total") || 0;
    const process = fieldValue("processTotal") || 0;
    const emissions = scope1 + scope2 + process;
    const intensity = emissions / energy;
    let coreTarget = null, targetNote = "请按园区类别和能源消费规模核对适用阈值";
    if (energy >= 200000 && energy < 1000000) { coreTarget = 0.2; targetNote = "20万—100万吨标准煤区间示例阈值；正式申报时核对适用类别"; }
    else if (energy >= 1000000) { coreTarget = 0.3; targetNote = "100万吨标准煤及以上区间示例阈值；正式申报时核对适用类别"; }

    const rows = [
      { metric: "单位综合能耗碳排放", current: intensity, target: coreTarget, unit: "tCO₂/tce", direction: "lower", note: targetNote },
      { metric: "清洁能源消费占比", current: fieldValue("cleanEnergy"), target: 90, unit: "%", direction: "higher", note: "引导指标" },
      { metric: "产品单位能耗", current: $("#productEnergy").value || null, target: "达到或优于二级能耗限额", unit: "", direction: "text", note: "按主要产品逐项核对" },
      { metric: "工业固废综合利用率", current: fieldValue("solidWaste"), target: 80, unit: "%", direction: "higher", note: "引导指标" },
      { metric: "余热/余冷/余压综合利用率", current: fieldValue("wasteEnergy"), target: 50, unit: "%", direction: "higher", note: "客观条件不具备时需说明" },
      { metric: "工业用水重复利用率", current: fieldValue("waterReuse"), target: 80, unit: "%", direction: "higher", note: "引导指标" },
    ].map(row => {
      let status = "缺数据", gap = null;
      if (row.direction === "text") status = row.current === "达标" ? "达到" : row.current === "未达标" ? "未达到" : row.current === "不适用" ? "需说明不适用条件" : "缺数据";
      else if (row.current !== null && row.target !== null) {
        gap = row.direction === "higher" ? Math.max(0, row.target - row.current) : Math.max(0, row.current - row.target);
        status = gap <= 1e-12 ? "达到" : "未达到";
      } else if (row.current !== null) status = "需确认适用阈值";
      return { ...row, status, gap };
    });
    state.gapRows = rows;
    const unresolved = rows.filter(row => row.status !== "达到").length;
    $("#gapResult").innerHTML = `<div class="gap-summary"><div><span>年度总排放</span><strong>${fmt.format(emissions)}</strong><small>tCO₂</small></div><div><span>单位能耗排放</span><strong>${fmt.format(intensity)}</strong><small>tCO₂/tce</small></div><div><span>待处理指标</span><strong>${unresolved}</strong><small>项</small></div></div><table class="gap-table"><thead><tr><th>指标</th><th>现状</th><th>目标</th><th>差距/状态</th></tr></thead><tbody>${rows.map(row => `<tr><td>${escapeHtml(row.metric)}<br><small>${escapeHtml(row.note)}</small></td><td>${row.current === null ? "—" : escapeHtml(typeof row.current === "number" ? fmt.format(row.current) + row.unit : row.current)}</td><td>${row.target === null ? "待确认" : escapeHtml(typeof row.target === "number" ? fmt.format(row.target) + row.unit : row.target)}</td><td class="${row.status === "达到" ? "status-ok" : "status-gap"}">${escapeHtml(row.status)}${row.gap ? `；差 ${fmt.format(row.gap)}${row.unit}` : ""}</td></tr>`).join("")}</tbody></table><p class="profile-sub">核算结果只对当前输入边界和年度有效，正式使用前复核活动数据、排放因子、绿电凭证和产品口径。</p>`;
    generateReductionAdvice(false);
    if (showToast) toast("差距核算完成，减排建议已同步更新");
    return { energy, scope1, scope2, process, emissions, intensity, rows };
  }

  function clearGap() {
    ["energyTotal", "scope1Total", "scope2Total", "processTotal", "cleanEnergy", "solidWaste", "wasteEnergy", "waterReuse"].forEach(id => $("#" + id).value = "");
    $("#productEnergy").value = "";
    $("#boundaryConfirmed").checked = false;
    state.gapRows = [];
    state.reductionAdvice = [];
    $("#gapResult").innerHTML = '<div class="empty-state">填入数据并确认边界后开始核算。</div>';
    $("#reductionAdvice").className = "advice-board empty-state";
    $("#reductionAdvice").textContent = "尚未生成减排建议。";
  }

  function initGap() {
    $("#loadGapDemo").addEventListener("click", () => {
      $("#boundaryConfirmed").checked = true;
      $("#energyTotal").value = 800000;
      $("#scope1Total").value = 160000;
      $("#scope2Total").value = 110000;
      $("#processTotal").value = 15000;
      $("#cleanEnergy").value = 62;
      $("#productEnergy").value = "未达标";
      $("#solidWaste").value = 76;
      $("#wasteEnergy").value = 32;
      $("#waterReuse").value = 72;
      toast("已载入演示值，不能作为真实园区结论");
    });
    $("#clearGap").addEventListener("click", clearGap);
    $("#runGap").addEventListener("click", () => runGap(true));
    $("#exportGap").addEventListener("click", () => {
      if (!state.gapRows.length && !runGap(false)) { toast("请先完成差距核算"); return; }
      downloadCsv("园区指标差距.csv", ["指标", "现状", "目标", "单位", "状态", "差距", "说明"], state.gapRows.map(row => [row.metric, row.current ?? "", row.target ?? "", row.unit, row.status, row.gap ?? "", row.note]));
    });
  }

  // Measures and automatic recommendations
  function normalizedMeasures() {
    return (state.data.measures || []).map((row, index) => ({
      id: row.tech_id || `T${index + 1}`,
      name: row["二级措施"] || row.name || `措施${index + 1}`,
      direction: row["一级方向"] || row.direction || "其他",
      park: row["适用园区"] || row.park || "全部",
      object: row["对象/工艺"] || row.object || "待确认",
      inputs: row["关键输入参数"] || row.inputs || "待补",
      calculation: row["减排计算逻辑"] || row.calculation || "需建立基准线",
      economics: row["经济性指标"] || row.economics || "CAPEX、OPEX、节省、寿命",
      constraints: row["主要约束"] || row.constraints || "需专项核实",
      maturity: row["成熟度"] || row.maturity || "待确认",
      status: row["参数状态"] || "指南级参数",
      type: measureType(row),
    }));
  }

  function renderMeasures(resetLimit = false) {
    if (resetLimit) state.measureLimit = 12;
    const type = $("#measureType").value;
    const direction = $("#measureDirection").value;
    const query = $("#measureSearch").value.trim().toLowerCase();
    const allRows = normalizedMeasures().filter(row => (type === "全部" || row.type === type) && (direction === "全部" || row.direction === direction) && (!query || [row.name, row.direction, row.object, row.constraints].join(" ").toLowerCase().includes(query)));
    const rows = allRows.slice(0, state.measureLimit);
    $("#measuresGrid").innerHTML = rows.length ? rows.map(row => `<label class="measure-card ${state.selectedMeasures.has(row.id) ? "selected" : ""}"><input type="checkbox" data-measure-id="${escapeHtml(row.id)}" ${state.selectedMeasures.has(row.id) ? "checked" : ""}><span class="measure-type">${escapeHtml(row.type)}</span><h4>${escapeHtml(row.name)}</h4><p><strong>适用：</strong>${escapeHtml(row.park)}；${escapeHtml(row.object)}</p><p><strong>前置：</strong>${escapeHtml(row.inputs)}</p><p><strong>约束：</strong>${escapeHtml(row.constraints)}</p><p class="caveat">${escapeHtml(row.status)}</p></label>`).join("") : '<div class="empty-state">当前筛选条件没有措施。</div>';
    const more = $("#moreMeasures");
    if (more) {
      more.style.display = rows.length < allRows.length ? "flex" : "none";
      more.textContent = `显示更多措施（${rows.length}/${allRows.length}）`;
    }
    $$("#measuresGrid input").forEach(check => check.addEventListener("change", () => {
      if (check.checked) state.selectedMeasures.add(check.dataset.measureId);
      else state.selectedMeasures.delete(check.dataset.measureId);
      renderMeasures();
      updateMeasureSummary();
    }));
  }

  function updateMeasureSummary() {
    const selected = normalizedMeasures().filter(row => state.selectedMeasures.has(row.id));
    const counts = selected.reduce((acc, row) => { acc[row.type] = (acc[row.type] || 0) + 1; return acc; }, {});
    $("#measureSummary").textContent = selected.length ? `已选 ${selected.length} 项：无悔型 ${counts["无悔型"] || 0}、条件型 ${counts["条件型"] || 0}、战略型 ${counts["战略型"] || 0}。` : "尚未选择措施。";
  }

  const gapMeasureMap = [
    { metric: "单位综合能耗碳排放", terms: ["电机", "泵", "风机", "空压", "蒸汽", "余热", "能碳管理"], reason: "先降低单位能源消耗和高耗能系统损失" },
    { metric: "清洁能源消费占比", terms: ["光伏", "绿电", "储能", "微电网"], reason: "在源荷、网架和结算条件核清后提高低碳供能比例" },
    { metric: "产品单位能耗", terms: ["电机", "空压", "工艺", "数字", "余热"], reason: "围绕主要产品基准线开展设备与工艺改造" },
    { metric: "工业固废综合利用率", terms: ["固废", "副产物", "工业共生", "资源"], reason: "建立副产物流向、品质和稳定需求清单" },
    { metric: "余热/余冷/余压综合利用率", terms: ["余热", "余压", "热泵", "蒸汽"], reason: "先做热源—热汇匹配和年度运行小时核算" },
    { metric: "工业用水重复利用率", terms: ["水回用", "再生水", "污水", "循环水"], reason: "从水量平衡和水质分级利用入手" },
  ];

  function generateReductionAdvice(showToast = true) {
    const measures = normalizedMeasures();
    const unresolved = state.gapRows.filter(row => row.status !== "达到");
    const candidates = new Map();
    const add = (measure, reason, metric) => {
      const current = candidates.get(measure.id) || { ...measure, reasons: new Set(), metrics: new Set() };
      current.reasons.add(reason);
      current.metrics.add(metric);
      candidates.set(measure.id, current);
    };
    if (unresolved.length) {
      unresolved.forEach(gap => {
        const mapping = gapMeasureMap.find(item => item.metric === gap.metric);
        if (!mapping) return;
        measures.filter(measure => mapping.terms.some(term => [measure.name, measure.direction, measure.object].join(" ").includes(term))).forEach(measure => add(measure, mapping.reason, gap.metric));
      });
    }
    if (!candidates.size) {
      measures.filter(measure => measure.type === "无悔型").slice(0, 9).forEach(measure => add(measure, "在正式差距数据形成前，先核查低风险、低制度依赖的基础工作", "数据前置"));
    }
    const typeRank = { "无悔型": 0, "条件型": 1, "战略型": 2 };
    state.reductionAdvice = [...candidates.values()].map(item => ({ ...item, reasons: [...item.reasons], metrics: [...item.metrics] })).sort((a, b) => typeRank[a.type] - typeRank[b.type] || a.name.localeCompare(b.name, "zh-CN")).slice(0, 12);
    state.reductionAdvice.forEach(item => state.selectedMeasures.add(item.id));
    $("#reductionAdvice").className = "advice-board";
    $("#reductionAdvice").innerHTML = `<div class="advice-grid">${state.reductionAdvice.map(item => `<article class="advice-card"><span class="advice-tier ${item.type === "无悔型" ? "no-regret" : item.type === "条件型" ? "conditional" : "strategic"}">${escapeHtml(item.type)}</span><h4>${escapeHtml(item.name)}</h4><p><strong>对应问题：</strong>${escapeHtml(item.metrics.join("、"))}</p><p>${escapeHtml(item.reasons.join("；"))}</p><p><strong>先核实：</strong>${escapeHtml(item.inputs)}</p><p class="caveat">不在缺少项目参数时给出确定减排量和收益。</p></article>`).join("")}</div>`;
    renderMeasures();
    updateMeasureSummary();
    if (showToast) toast(`已形成 ${state.reductionAdvice.length} 项分级建议`);
  }

  function initMeasures() {
    const directions = [...new Set(normalizedMeasures().map(row => row.direction))].sort((a, b) => a.localeCompare(b, "zh-CN"));
    $("#measureDirection").innerHTML = '<option value="全部">全部方向</option>' + directions.map(direction => `<option value="${escapeHtml(direction)}">${escapeHtml(direction)}</option>`).join("");
    ["measureType", "measureDirection"].forEach(id => $("#" + id).addEventListener("change", () => renderMeasures(true)));
    $("#measureSearch").addEventListener("input", () => renderMeasures(true));
    $("#moreMeasures").addEventListener("click", () => { state.measureLimit += 12; renderMeasures(); });
    $("#selectNoRegret").addEventListener("click", () => { normalizedMeasures().filter(row => row.type === "无悔型").forEach(row => state.selectedMeasures.add(row.id)); renderMeasures(); updateMeasureSummary(); toast("已勾选全部无悔型措施"); });
    $("#clearMeasures").addEventListener("click", () => { state.selectedMeasures.clear(); renderMeasures(); updateMeasureSummary(); toast("已清空措施选择"); });
    $("#exportMeasures").addEventListener("click", () => {
      const selected = normalizedMeasures().filter(row => state.selectedMeasures.has(row.id));
      if (!selected.length) { toast("请先选择措施"); return; }
      downloadCsv("园区减排措施清单.csv", ["编号", "措施", "类型", "方向", "适用园区", "对象/工艺", "关键输入", "减排计算逻辑", "经济性指标", "主要约束", "参数状态"], selected.map(row => [row.id, row.name, row.type, row.direction, row.park, row.object, row.inputs, row.calculation, row.economics, row.constraints, row.status]));
    });
    $("#generateReductionAdvice").addEventListener("click", generateReductionAdvice);
    $("#exportReductionAdvice").addEventListener("click", () => {
      if (!state.reductionAdvice.length) generateReductionAdvice();
      downloadCsv("园区自动减排建议.csv", ["编号", "措施", "分级", "对应问题", "建议理由", "前置数据", "计算逻辑", "经济性", "主要约束"], state.reductionAdvice.map(item => [item.id, item.name, item.type, item.metrics.join("；"), item.reasons.join("；"), item.inputs, item.calculation, item.economics, item.constraints]));
    });
    renderMeasures();
    updateMeasureSummary();
  }

  // Cost and feasibility
  function defaultProjects() {
    return [
      { project_id: "P01", name: "重点用能设备计量与诊断", category: "管理基础", capex: 800, abatement: 3200, saving: 720, opex: 60, life: 8, start: 2027, evidence: "演示参数" },
      { project_id: "P02", name: "空压系统群控与泄漏治理", category: "节能降碳", capex: 1300, abatement: 6100, saving: 980, opex: 90, life: 10, start: 2027, evidence: "演示参数" },
      { project_id: "P03", name: "蒸汽管网与凝结水回收", category: "节能降碳", capex: 2600, abatement: 9800, saving: 1460, opex: 120, life: 12, start: 2028, evidence: "演示参数" },
      { project_id: "P04", name: "低品位余热回收", category: "节能降碳", capex: 4800, abatement: 13800, saving: 1820, opex: 210, life: 15, start: 2028, evidence: "演示参数" },
      { project_id: "P05", name: "再生水分级回用", category: "资源循环", capex: 3500, abatement: 2600, saving: 460, opex: 150, life: 15, start: 2029, evidence: "演示参数" },
      { project_id: "P06", name: "园区分布式光伏", category: "绿色供能", capex: 15000, abatement: 18500, saving: 2100, opex: 260, life: 25, start: 2029, evidence: "演示参数" },
    ];
  }

  function blankProject() {
    return { project_id: `U${Date.now()}`, name: "新增项目", category: "节能降碳", capex: 0, abatement: 0, saving: 0, opex: 0, life: 10, start: 2027, evidence: "待核实" };
  }

  function renderProjects() {
    $("#projectTableBody").innerHTML = state.projects.map((project, index) => `<tr data-index="${index}">
      <td><input data-key="name" value="${escapeHtml(project.name)}"></td>
      <td><select data-key="category">${["管理基础", "节能降碳", "绿色供能", "资源循环", "工艺改造"].map(item => `<option ${item === project.category ? "selected" : ""}>${item}</option>`).join("")}</select></td>
      <td><input data-key="capex" type="number" min="0" value="${project.capex}"></td>
      <td><input data-key="abatement" type="number" min="0" value="${project.abatement}"></td>
      <td><input data-key="saving" type="number" min="0" value="${project.saving}"></td>
      <td><input data-key="opex" type="number" min="0" value="${project.opex}"></td>
      <td><input data-key="life" type="number" min="1" value="${project.life}"></td>
      <td><input data-key="start" type="number" min="2026" max="2050" value="${project.start}"></td>
      <td><select data-key="evidence">${["待核实", "演示参数", "供应商报价", "园区可研", "审计/验收材料"].map(item => `<option ${item === project.evidence ? "selected" : ""}>${item}</option>`).join("")}</select></td>
      <td><button class="btn btn-line project-delete" type="button" data-index="${index}">删除</button></td>
    </tr>`).join("");
    $$("#projectTableBody input, #projectTableBody select").forEach(input => input.addEventListener("change", () => {
      const index = Number(input.closest("tr").dataset.index);
      const key = input.dataset.key;
      state.projects[index][key] = ["capex", "abatement", "saving", "opex", "life", "start"].includes(key) ? n(input.value, 0) : input.value;
    }));
    $$(".project-delete").forEach(button => button.addEventListener("click", () => { state.projects.splice(Number(button.dataset.index), 1); renderProjects(); toast("项目已删除"); }));
  }

  function annuityFactor(rate, years) {
    return rate === 0 ? years : (1 - Math.pow(1 + rate, -years)) / rate;
  }

  function projectMetrics(project, rate) {
    const factor = annuityFactor(rate, project.life);
    const netAnnual = project.saving - project.opex;
    const npvCost = project.capex - netAnnual * factor;
    const lifeAbatement = project.abatement * project.life;
    return { ...project, net: netAnnual, npvCost, lifeAbatement, macc: lifeAbatement > 0 ? npvCost * 10000 / lifeAbatement : Infinity, payback: netAnnual > 0 ? project.capex / netAnnual : null };
  }

  function compareKeys(a, b) {
    for (let index = 0; index < a.length; index++) {
      if (a[index] < b[index]) return -1;
      if (a[index] > b[index]) return 1;
    }
    return 0;
  }

  function optimizeProjects(projects, budget, target, rate) {
    const rows = projects.map(project => projectMetrics(project, rate));
    if (rows.length > 22) throw new Error("浏览器精确组合最多支持22个项目，请先筛选候选项目");
    let best = null;
    for (let mask = 0; mask < (1 << rows.length); mask++) {
      const selected = [];
      let capex = 0, abatement = 0, net = 0, npvCost = 0;
      for (let index = 0; index < rows.length; index++) {
        if ((mask >> index) & 1) {
          const row = rows[index];
          selected.push(row); capex += row.capex; abatement += row.abatement; net += row.net; npvCost += row.npvCost;
        }
      }
      if (capex > budget + 1e-9) continue;
      const meets = abatement >= target;
      const key = meets ? [0, npvCost, capex, -abatement] : [1, -abatement, npvCost, capex];
      if (!best || compareKeys(key, best.key) < 0) best = { key, selected, capex, abatement, net, npvCost, meets, gap: Math.max(0, target - abatement), budget, target };
    }
    return best || { selected: [], capex: 0, abatement: 0, net: 0, npvCost: 0, meets: false, gap: target, budget, target };
  }

  function gateTasks() {
    const tasks = [];
    if (!$("#feasBoundary").checked) tasks.push(["法定边界", "园区管委会/自然资源", "边界图、批复文件和纳入范围说明"]);
    if (!$("#feasEnterprise").checked) tasks.push(["纳入企业清单", "园区管委会/市场监管", "企业名称、统一社会信用代码、行业和纳入状态"]);
    if (!n($("#feasYear").value, 0)) tasks.push(["基准年", "园区统计/发改", "与全部活动数据一致的自然年"]);
    [["energyTotal", "综合能源消费量", "发改/统计/园区", "分品种台账与折标底稿"], ["scope1Total", "范围一排放", "重点企业/园区", "燃料活动数据与因子"], ["scope2Total", "范围二排放", "供电/供热/园区", "购售电热、绿电凭证和因子版本"], ["processTotal", "工业过程排放", "重点企业", "过程活动数据；无过程排放时填0并说明"]].forEach(([id, name, owner, material]) => { if (fieldValue(id) === null) tasks.push([name, owner, material]); });
    return tasks.map((task, index) => ({ no: index + 1, name: task[0], owner: task[1], material: task[2], due: "3个工作日" }));
  }

  function stakeholderSummary(selected) {
    const result = {};
    selected.forEach(project => {
      const group = project.category === "绿色供能" ? "能源运营方/用能企业" : project.category === "资源循环" ? "公共设施运营方/园区企业" : project.category === "管理基础" ? "园区管委会/园区企业" : "园区企业";
      const names = group.split("/");
      names.forEach(name => {
        const row = result[name] ||= { count: 0, capex: 0, net: 0, abatement: 0 };
        row.count += 1; row.capex += project.capex / names.length; row.net += project.net / names.length; row.abatement += project.abatement / names.length;
      });
    });
    return result;
  }

  function annualPath(selected, baseline, endYear = 2030) {
    if (!selected.length) return [];
    const first = Math.min(...selected.map(project => project.start));
    const rows = [];
    for (let year = first; year <= endYear; year++) {
      const abatement = selected.filter(project => project.start <= year).reduce((sum, project) => sum + project.abatement, 0);
      const remaining = Math.max(0, baseline - abatement);
      let stage = "减碳";
      if (baseline > 0 && remaining / baseline <= 0.1) stage = "近零碳";
      if (remaining <= 0) stage = "零碳（需核验剩余排放与抵消）";
      rows.push({ year, abatement, remaining, stage });
    }
    return rows;
  }

  function portfolioSensitivity(selected, rate) {
    const scenarios = [
      { name: "保守情景", capex: 1.15, saving: 0.80, opex: 1.10, abatement: 0.90, note: "投资上浮15%，节省下降20%，运维上浮10%，减排下降10%" },
      { name: "基准情景", capex: 1.00, saving: 1.00, opex: 1.00, abatement: 1.00, note: "按当前录入参数" },
      { name: "改善情景", capex: 0.95, saving: 1.10, opex: 1.00, abatement: 1.05, note: "投资下降5%，节省上升10%，减排上升5%" },
    ];
    return scenarios.map(scenario => {
      let capex = 0, abatement = 0, annualNet = 0, npvCost = 0;
      selected.forEach(project => {
        const adjustedCapex = project.capex * scenario.capex;
        const adjustedNet = project.saving * scenario.saving - project.opex * scenario.opex;
        capex += adjustedCapex;
        abatement += project.abatement * scenario.abatement;
        annualNet += adjustedNet;
        npvCost += adjustedCapex - adjustedNet * annuityFactor(rate, project.life);
      });
      return { name: scenario.name, note: scenario.note, capex, abatement, annualNet, npvCost, payback: annualNet > 0 ? capex / annualNet : null };
    });
  }

  function runFeasibility() {
    const tasks = gateTasks();
    const parkName = $("#feasParkName").value.trim() || "未命名园区";
    if (tasks.length) {
      state.lastFeasibility = { parkName, mode: "data_completion", conclusion: "暂不具备正式可行性测算条件", tasks, gap: null, portfolio: null, risks: [{ dimension: "数据与边界", level: "高", finding: `缺少${tasks.length}项正式测算前置数据`, action: "先完成补数任务" }], recommendations: state.reductionAdvice };
      $("#feasibilityResult").innerHTML = `<div class="empty-state"><strong>暂不具备正式可行性测算条件</strong><br>系统没有生成排名或投资结论，而是形成 ${tasks.length} 项补数任务。</div>${tasks.map(task => `<div class="task-item"><strong>${task.no}. ${escapeHtml(task.name)}</strong><span>责任：${escapeHtml(task.owner)} · 最低材料：${escapeHtml(task.material)}</span><span>建议时限：${task.due}</span></div>`).join("")}`;
      $("#pathResult").innerHTML = '<div class="empty-state">数据门槛通过后再生成项目组合、利益相关方分配和年度路径。</div>';
      toast("数据门槛未通过，已生成补数任务");
      return;
    }
    const gap = runGap(false);
    if (!gap) { activatePanel("gap"); toast("请先补齐差距核算输入"); return; }
    if (!state.reductionAdvice.length) generateReductionAdvice();
    const valid = state.projects.filter(project => project.name && project.capex >= 0 && project.abatement >= 0 && project.life > 0);
    if (!valid.length) { toast("请至少提供一个项目参数"); return; }
    const budget = n($("#budgetLimit").value, 0), target = n($("#abatementTarget").value, 0), rate = n($("#discountRate").value, 5) / 100;
    let portfolio;
    try { portfolio = optimizeProjects(valid, budget, target, rate); }
    catch (error) { toast(error.message); return; }
    const demoEvidence = portfolio.selected.filter(project => project.evidence === "演示参数").length;
    const pendingEvidence = portfolio.selected.filter(project => project.evidence === "待核实").length;
    const risks = [];
    if (demoEvidence) risks.push({ dimension: "演示数据", level: "高", finding: `${demoEvidence}个入选项目使用演示参数，当前结果只用于验证计算链路`, action: "用园区台账、供应商报价、可研参数和测量验证边界替换后重新运行" });
    if (pendingEvidence) risks.push({ dimension: "项目参数", level: "中", finding: `${pendingEvidence}个入选项目参数仍待核实`, action: "取得报价、能量平衡和节能量测量边界" });
    if (!portfolio.meets) risks.push({ dimension: "目标缺口", level: "高", finding: `当前预算内仍有 ${fmt.format(portfolio.gap)} tCO₂/年缺口`, action: "增加候选项目、调整预算或分期目标" });
    const unresolved = gap.rows.filter(row => ["未达到", "缺数据", "需确认适用阈值"].includes(row.status)).length;
    if (unresolved) risks.push({ dimension: "指标差距", level: "中", finding: `${unresolved}项指标仍有差距或缺数据`, action: "核心指标优先，引导指标逐项推进" });
    if (!risks.length) risks.push({ dimension: "初步筛查", level: "低", finding: "当前输入未触发高、中风险规则", action: "继续开展工程可研和法定审查" });
    const conclusion = demoEvidence ? "演示场景仅用于验证计算链路，不构成园区可行性结论" : risks.some(risk => risk.level === "高") ? "具备初步测算基础，但关键风险尚未关闭" : risks.some(risk => risk.level === "中") ? "具备初步可行性，需专项可研和参数核验" : "具备较完整的初步可行性条件";
    const stakeholders = stakeholderSummary(portfolio.selected);
    const path = annualPath(portfolio.selected, gap.emissions, 2030);
    const sensitivity = portfolioSensitivity(portfolio.selected, rate);
    state.lastFeasibility = { parkName, year: $("#feasYear").value, mode: demoEvidence ? "demonstration" : "formal", conclusion, tasks: [], gap, portfolio, risks, stakeholders, path, sensitivity, recommendations: state.reductionAdvice };
    $("#feasibilityResult").innerHTML = `<div class="portfolio-kpis"><div><span>组合投资</span><strong>${fmt.format(portfolio.capex)}</strong><small>万元</small></div><div><span>年度减排</span><strong>${fmt.format(portfolio.abatement)}</strong><small>tCO₂</small></div><div><span>年度净收益</span><strong>${fmt.format(portfolio.net)}</strong><small>万元</small></div><div><span>目标缺口</span><strong>${fmt.format(portfolio.gap)}</strong><small>tCO₂/年</small></div></div><p><strong>初筛结论：</strong>${escapeHtml(conclusion)}</p>${portfolio.selected.length ? portfolio.selected.map(project => `<div class="portfolio-item"><span>${escapeHtml(project.name)}<br><small>${escapeHtml(project.category)} · ${escapeHtml(project.evidence)}</small></span><strong>${fmt.format(project.capex)}万元 / ${fmt.format(project.abatement)}t</strong></div>`).join("") : '<div class="empty-state">预算内没有入选项目。</div>'}<h5>关键参数敏感性</h5><table class="path-table"><thead><tr><th>情景</th><th>投资/万元</th><th>年减排/tCO₂</th><th>年净收益/万元</th><th>回收期/年</th></tr></thead><tbody>${sensitivity.map(row => `<tr><td>${escapeHtml(row.name)}<br><small>${escapeHtml(row.note)}</small></td><td>${fmt.format(row.capex)}</td><td>${fmt.format(row.abatement)}</td><td>${fmt.format(row.annualNet)}</td><td>${row.payback === null ? "—" : fmt.format(row.payback)}</td></tr>`).join("")}</tbody></table><div class="risk-list">${risks.map(risk => `<div class="risk-item ${risk.level === "高" ? "high" : risk.level === "中" ? "medium" : "low"}"><strong>${escapeHtml(risk.dimension)} · ${escapeHtml(risk.level)}</strong><br>${escapeHtml(risk.finding)}<br><span>${escapeHtml(risk.action)}</span></div>`).join("")}</div><p class="profile-sub">本结果属于前期筛查和项目排序，不替代节能审查、环评、接入系统审查、工程可研或投资决策。</p>`;
    $("#pathResult").innerHTML = `<h5>利益相关方</h5>${Object.entries(stakeholders).map(([name, row]) => `<div class="stakeholder-line"><strong>${escapeHtml(name)}</strong><br><span>${row.count}个项目；分摊投资口径 ${fmt.format(row.capex)} 万元；年净收益口径 ${fmt.format(row.net)} 万元；年减排 ${fmt.format(row.abatement)} tCO₂。</span></div>`).join("")}<h5>年度路径</h5><table class="path-table"><thead><tr><th>年度</th><th>年减排</th><th>剩余排放</th><th>阶段</th></tr></thead><tbody>${path.map(row => `<tr><td>${row.year}</td><td>${fmt.format(row.abatement)}</td><td>${fmt.format(row.remaining)}</td><td>${escapeHtml(row.stage)}</td></tr>`).join("")}</tbody></table>`;
    toast(portfolio.meets ? "已形成满足目标的项目组合" : "已形成预算内最大减排组合");
  }

  function feasibilityMarkdown() {
    const result = state.lastFeasibility;
    if (!result) return "";
    const modeLabel = result.mode === "demonstration" ? "演示场景" : result.mode === "data_completion" ? "数据补齐" : "正式初筛";
    let markdown = `# ${result.parkName}零碳建设可行性初筛报告\n\n- 基准年：${result.year || "待确认"}\n- 生成模式：${modeLabel}\n- 初筛结论：${result.conclusion}\n- 生成时间：${new Date().toLocaleString("zh-CN")}\n\n> 本报告用于前期筛查和项目排序，不替代法定节能审查、环评、接入系统审查、工程可研或投资决策。\n\n## 1. 数据够不够\n\n`;
    if (result.tasks.length) return markdown + `数据尚不完整，当前只生成补数任务。\n\n|序号|字段|责任部门|最低材料|时限|\n|---|---|---|---|---|\n${result.tasks.map(task => `|${task.no}|${task.name}|${task.owner}|${task.material}|${task.due}|`).join("\n")}\n`;
    markdown += `数据门槛字段已提供；正式提交前仍应复核原始凭证、因子版本和复核记录。\n\n## 2. 现状是什么\n\n- 园区排放：${fmt.format(result.gap.emissions)} tCO₂\n- 综合能源消费：${fmt.format(result.gap.energy)} tce\n- 单位能耗碳排放：${fmt.format(result.gap.intensity)} tCO₂/tce\n\n## 3. 差距在哪里\n\n|指标|现状|目标|状态|\n|---|---:|---:|---|\n${result.gap.rows.map(row => `|${row.metric}|${row.current ?? "—"}|${row.target ?? "待确认"}|${row.status}|`).join("\n")}\n\n## 4. 怎么减\n\n`;
    markdown += result.recommendations.length ? result.recommendations.map((item, index) => `${index + 1}. **${item.name}（${item.type}）**：${item.reasons.join("；")}。前置数据：${item.inputs}。`).join("\n") : "先从计量、设备效率、蒸汽与余热、水循环和工业协同等无悔工作开始。";
    markdown += `\n\n## 5. 花多少钱\n\n- 预算：${fmt.format(result.portfolio.budget)} 万元\n- 入选投资：${fmt.format(result.portfolio.capex)} 万元\n- 年减排：${fmt.format(result.portfolio.abatement)} tCO₂\n- 年净收益：${fmt.format(result.portfolio.net)} 万元\n- 目标缺口：${fmt.format(result.portfolio.gap)} tCO₂/年\n\n|项目|投资/万元|年减排/tCO₂|年净收益/万元|参数证据|\n|---|---:|---:|---:|---|\n${result.portfolio.selected.map(project => `|${project.name}|${project.capex}|${project.abatement}|${project.net}|${project.evidence}|`).join("\n")}\n\n### 关键参数敏感性\n\n|情景|投资/万元|年减排/tCO₂|年净收益/万元|回收期/年|\n|---|---:|---:|---:|---:|\n${(result.sensitivity || []).map(row => `|${row.name}|${fmt.format(row.capex)}|${fmt.format(row.abatement)}|${fmt.format(row.annualNet)}|${row.payback === null ? "—" : fmt.format(row.payback)}|`).join("\n")}\n\n## 关键风险\n\n${result.risks.map(item => `- **${item.dimension}（${item.level}）**：${item.finding}；建议：${item.action}`).join("\n")}\n`;
    return markdown;
  }

  function printableFeasibilityHtml() {
    const result = state.lastFeasibility;
    if (!result) return "";
    const mapSvg = $("#mapSvg").outerHTML;
    const recommendationRows = (result.recommendations || []).map(item => `<li><strong>${escapeHtml(item.name)}（${escapeHtml(item.type)}）</strong>：${escapeHtml(item.reasons.join("；"))}</li>`).join("");
    const taskRows = result.tasks.length ? `<table><tr><th>字段</th><th>责任部门</th><th>最低材料</th></tr>${result.tasks.map(task => `<tr><td>${escapeHtml(task.name)}</td><td>${escapeHtml(task.owner)}</td><td>${escapeHtml(task.material)}</td></tr>`).join("")}</table>` : "<p>数据门槛已通过，正式使用前仍需复核原始材料。</p>";
    const gapRows = result.gap ? `<table><tr><th>指标</th><th>现状</th><th>目标</th><th>状态</th></tr>${result.gap.rows.map(row => `<tr><td>${escapeHtml(row.metric)}</td><td>${escapeHtml(row.current ?? "—")}</td><td>${escapeHtml(row.target ?? "待确认")}</td><td>${escapeHtml(row.status)}</td></tr>`).join("")}</table>` : "<p>数据不全，未开展指标核算。</p>";
    const projectRows = result.portfolio ? `<table><tr><th>项目</th><th>投资/万元</th><th>年减排/tCO₂</th><th>年净收益/万元</th></tr>${result.portfolio.selected.map(project => `<tr><td>${escapeHtml(project.name)}</td><td>${fmt.format(project.capex)}</td><td>${fmt.format(project.abatement)}</td><td>${fmt.format(project.net)}</td></tr>`).join("")}</table>` : "<p>数据不全，未形成项目组合。</p>";
    const sensitivityRows = result.sensitivity?.length ? `<h2>关键参数敏感性</h2><table><tr><th>情景</th><th>投资/万元</th><th>年减排/tCO₂</th><th>年净收益/万元</th><th>回收期/年</th></tr>${result.sensitivity.map(row => `<tr><td>${escapeHtml(row.name)}</td><td>${fmt.format(row.capex)}</td><td>${fmt.format(row.abatement)}</td><td>${fmt.format(row.annualNet)}</td><td>${row.payback === null ? "—" : fmt.format(row.payback)}</td></tr>`).join("")}</table>` : "";
    const modeLabel = result.mode === "demonstration" ? "演示场景" : result.mode === "data_completion" ? "数据补齐" : "正式初筛";
    return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>${escapeHtml(result.parkName)}可行性初筛报告</title><style>body{max-width:940px;margin:30px auto;font:15px/1.7 SimSun,serif;color:#202824}h1,h2{font-family:"Microsoft YaHei",sans-serif}small,.note{color:#657067}table{width:100%;border-collapse:collapse;margin:12px 0}th,td{border:1px solid #ccd4ce;padding:8px;text-align:left;vertical-align:top}svg{width:100%;height:360px;background:#eef2ee;border:1px solid #d7ded8}.actions{position:sticky;top:0;padding:10px 0;background:#fff}.actions button{padding:8px 14px}@media print{.actions{display:none}}</style></head><body><div class="actions"><button onclick="window.print()">打印或另存为PDF</button></div><h1>${escapeHtml(result.parkName)}零碳建设可行性初筛报告</h1><p><strong>生成模式：</strong>${escapeHtml(modeLabel)}　<strong>结论：</strong>${escapeHtml(result.conclusion)}</p><p class="note">生成时间：${new Date().toLocaleString("zh-CN")}。本报告用于前期筛查，不替代法定审查和工程可研。</p><h2>参考界面：园区空间位置</h2>${mapSvg}<h2>1. 数据够不够</h2>${taskRows}<h2>2. 现状是什么</h2><p>${result.gap ? `年度排放 ${fmt.format(result.gap.emissions)} tCO₂，综合能源消费 ${fmt.format(result.gap.energy)} tce，单位能耗碳排放 ${fmt.format(result.gap.intensity)} tCO₂/tce。` : "数据尚未达到现状核算门槛。"}</p><h2>3. 差距在哪里</h2>${gapRows}<h2>4. 怎么减</h2><ol>${recommendationRows || "<li>先完成数据补齐和无悔型排查。</li>"}</ol><h2>5. 花多少钱</h2>${projectRows}${sensitivityRows}</body></html>`;
  }

  function initFeasibility() {
    state.projects = [];
    renderProjects();
    $("#loadProjectDemo").addEventListener("click", () => { state.projects = defaultProjects(); renderProjects(); toast("已载入演示项目，正式使用前必须替换参数"); });
    $("#addProject").addEventListener("click", () => { state.projects.push(blankProject()); renderProjects(); });
    $("#projectFile").addEventListener("change", async event => {
      const file = event.target.files[0];
      if (!file) return;
      try {
        const value = JSON.parse(await file.text());
        const rows = Array.isArray(value) ? value : value.projects;
        if (!Array.isArray(rows)) throw new Error("JSON需为项目数组或包含projects数组");
        state.projects = rows.map((project, index) => ({ project_id: project.project_id || `I${index + 1}`, name: project.name || project.project_name || `项目${index + 1}`, category: project.category || "节能降碳", capex: n(project.capex_10k_cny ?? project.capex, 0), abatement: n(project.annual_abatement_tco2 ?? project.abatement, 0), saving: n(project.annual_saving_10k_cny ?? project.saving, 0), opex: n(project.annual_opex_10k_cny ?? project.opex, 0), life: n(project.lifetime_years ?? project.life, 10), start: n(project.start_year ?? project.start, 2027), evidence: project.evidence_level || project.evidence || "待核实" }));
        renderProjects();
        toast(`已导入 ${state.projects.length} 个项目`);
      } catch (error) { toast(`导入失败：${error.message}`); }
      event.target.value = "";
    });
    $("#downloadProjectTemplate").addEventListener("click", () => downloadText("项目可行性参数模板.json", JSON.stringify({ projects: [{ project_id: "P001", name: "示例：空压系统优化", category: "节能降碳", capex_10k_cny: 0, annual_abatement_tco2: 0, annual_saving_10k_cny: 0, annual_opex_10k_cny: 0, lifetime_years: 10, start_year: 2027, evidence_level: "待核实" }] }, null, 2), "application/json;charset=utf-8"));
    $("#runFeasibility").addEventListener("click", runFeasibility);
    $("#downloadFeasibilityReport").addEventListener("click", () => { if (!state.lastFeasibility) { toast("请先运行可行性分析"); return; } downloadText(`${state.lastFeasibility.parkName}_可行性初筛报告.md`, feasibilityMarkdown(), "text/markdown;charset=utf-8"); });
    $("#printFeasibilityReport").addEventListener("click", () => {
      if (!state.lastFeasibility) { toast("请先运行可行性分析"); return; }
      const url = URL.createObjectURL(new Blob([printableFeasibilityHtml()], { type: "text/html;charset=utf-8" }));
      const win = window.open(url, "_blank", "noopener,noreferrer");
      if (!win) { URL.revokeObjectURL(url); toast("浏览器阻止了新窗口，请允许弹窗后重试"); return; }
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    });
  }

  // ---------------------------------------------------------------------------
  // Searchable public database
  // ---------------------------------------------------------------------------
  function buildDatabaseRows() {
    const rows = [];
    state.data.parks.forEach(park => rows.push({ type: "园区", date: [park.province, park.city].filter(Boolean).join("/"), title: park.name, description: `${park.list_level || ""}；${park.industry || ""}；${park.boundary_type || ""}；${park.period || ""}`, limit: park.note || "公开名录资料", url: park.source_url, source: park.source_title || "园区名录" }));
    state.archive.forEach(update => rows.push({ type: "动态", date: update.published_date || "—", title: update.title, description: update.summary, limit: update.why || "正式判断前核对原文", url: update.url, source: update.publisher || update.source_name }));
    (state.data.rules || []).forEach(rule => rows.push({ type: "标准", date: rule.category || "政策标准", title: rule.item || rule.rule_id, description: rule.rule, limit: rule.nature || "按适用范围使用", url: rule.source_url, source: rule.source }));
    normalizedMeasures().forEach(measure => rows.push({ type: "措施", date: measure.type, title: measure.name, description: `${measure.direction}；适用：${measure.park}；对象：${measure.object}`, limit: `${measure.constraints}；${measure.status}`, url: "data/technology_guidance.csv", source: "减排设施指南" }));
    return rows;
  }

  function runDatabase(reset = true) {
    if (reset) state.dbLimit = 25;
    const query = $("#dbSearch").value.trim().toLowerCase();
    const type = $("#dbType").value;
    state.dbRows = buildDatabaseRows().filter(row => (type === "全部" || row.type === type) && (!query || [row.title, row.description, row.limit, row.date, row.source].join(" ").toLowerCase().includes(query)));
    renderDatabase();
  }

  function renderDatabase() {
    const rows = state.dbRows.slice(0, state.dbLimit);
    $("#dbStatus").textContent = `找到 ${state.dbRows.length} 条，当前显示 ${rows.length} 条。`;
    $("#archiveTable").innerHTML = rows.map(row => `<tr><td>${escapeHtml(row.type)}</td><td>${escapeHtml(row.date)}</td><td><strong>${escapeHtml(row.title)}</strong><br><span>${escapeHtml(row.description)}</span></td><td>${escapeHtml(row.limit)}</td><td>${row.url ? `<a href="${escapeHtml(row.url)}" ${/^https?:/.test(row.url) ? 'target="_blank" rel="noopener"' : "download"}>${escapeHtml(row.source || "来源")} ↗</a>` : escapeHtml(row.source || "—")}</td></tr>`).join("");
    $("#dbMore").style.display = state.dbLimit < state.dbRows.length ? "flex" : "none";
  }

  function initDatabase() {
    $("#dbRun").addEventListener("click", () => runDatabase(true));
    $("#dbClear").addEventListener("click", () => { $("#dbSearch").value = ""; $("#dbType").value = "全部"; runDatabase(true); });
    $("#dbSearch").addEventListener("keydown", event => { if (event.key === "Enter") runDatabase(true); });
    $("#dbMore").addEventListener("click", () => { state.dbLimit += 25; renderDatabase(); });
    $("#downloadArchive").addEventListener("click", () => downloadText("零碳园区公开动态档案.json", JSON.stringify(state.archive, null, 2), "application/json;charset=utf-8"));
    runDatabase(true);
  }

  // ---------------------------------------------------------------------------
  // Reports and email delivery
  // ---------------------------------------------------------------------------
  function reportForType(type) {
    return (state.reportIndex.reports || []).find(row => row.type === type);
  }

  function initReports() {
    const labels = {
      daily: ["日报", "当天及近期园区、技术、项目和政策线索"],
      weekly: ["周报", "近7天事件归并、机会约束、补数任务和无悔工作"],
      feasibility: ["可行性初筛报告", "示范场景的数据门槛、指标差距、减排建议和项目组合"],
    };
    const rows = state.reportIndex.reports || [];
    $("#reportLinks").innerHTML = rows.length ? rows.map(row => {
      const [title, description] = labels[row.type] || [row.type, "自动生成报告"];
      return `<article class="report-card"><span class="report-type">${escapeHtml(title)}</span><h3>${escapeHtml(title)}</h3><p>${escapeHtml(description)}。报告日期：${escapeHtml(row.date || "—")}；记录：${escapeHtml(row.record_count ?? "—")}。</p><div class="report-actions"><a class="btn btn-dark" href="${escapeHtml(row.html)}">网页报告</a>${row.pdf ? `<a class="btn btn-line" href="${escapeHtml(row.pdf)}" target="_blank" rel="noopener">PDF</a>` : ""}<a class="btn btn-line" href="${escapeHtml(row.markdown)}" download>Markdown</a><a class="btn btn-line" href="${escapeHtml(row.json)}" download>JSON</a></div></article>`;
    }).join("") : '<div class="empty-state">报告索引尚未生成。运行构建命令后自动出现。</div>';
    $("#sendReportEmail").addEventListener("click", sendReportEmail);
  }

  async function sendReportEmail() {
    const email = $("#reportEmail").value.trim();
    const type = $("#reportEmailType").value;
    const consent = $("#reportConsent").checked;
    const status = $("#mailStatus");
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { status.textContent = "请填写有效邮箱。"; return; }
    if (!consent) { status.textContent = "请先勾选本次发送授权。"; return; }
    const report = reportForType(type);
    if (!report) { status.textContent = "所选报告尚未生成。"; return; }
    const base = new URL(".", location.href);
    const reportUrl = new URL(report.pdf || report.html, base).href;
    const endpoint = String(state.runtime.mail_endpoint || "").trim();
    status.textContent = "正在准备发送…";
    if (endpoint) {
      try {
        const response = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email, report_type: type, report_url: reportUrl,
            site_url: location.origin + location.pathname.replace(/[^/]*$/, ""),
            consent: true,
            feasibility_summary: type === "feasibility" && state.lastFeasibility ? {
              park_name: state.lastFeasibility.park_name || "园区",
              conclusion: state.lastFeasibility.feasibility?.conclusion || "",
              decision_boundary: state.lastFeasibility.feasibility?.decision_boundary || "",
              selected_projects: state.lastFeasibility.five_questions?.["花多少钱"]?.portfolio?.selected_projects?.map(project => project.name).slice(0, 12) || [],
              capex_10k_cny: state.lastFeasibility.five_questions?.["花多少钱"]?.portfolio?.capex_10k_cny ?? null,
              annual_abatement_tco2: state.lastFeasibility.five_questions?.["花多少钱"]?.portfolio?.annual_abatement_tco2 ?? null,
            } : null,
          }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
        status.textContent = "报告发送请求已受理，请检查收件箱和垃圾邮件。";
        toast("报告发送请求已提交");
        return;
      } catch (error) {
        status.textContent = `直接发送未完成：${error.message}。已转为本机邮件方式。`;
      }
    }
    const subject = encodeURIComponent(`园区碳观察：${type === "weekly" ? "本周报告" : type === "daily" ? "今日报告" : "可行性初筛报告"}`);
    const body = encodeURIComponent(`您好：\n\n请查收园区碳观察报告：\n${reportUrl}\n\n该链接来自公开网站，不含邮箱信息。`);
    location.href = `mailto:${encodeURIComponent(email)}?subject=${subject}&body=${body}`;
    status.textContent = "已打开本机邮件客户端，并填入报告链接。若未弹出，请复制报告链接后手动发送。";
    try { await navigator.clipboard.writeText(reportUrl); toast("报告链接已复制"); } catch (_) { /* clipboard optional */ }
  }

  function installServiceWorker() {
    if ("serviceWorker" in navigator && location.protocol.startsWith("http")) navigator.serviceWorker.register("sw.js").catch(() => {});
  }

  function runSelfTest() {
    if (!new URLSearchParams(location.search).has("selftest") && !window.__ZCP_SELFTEST__) return;
    const checks = [];
    const add = (name, pass) => checks.push({ name, pass: Boolean(pass) });
    add("dashboard loaded", Boolean(state.data));
    add("parks loaded", state.data.parks.length >= 1);
    add("archive loaded", state.archive.length >= 1);
    add("map geometry loaded", Boolean(state.geometry));
    add("all five panels", $$(".five-tab").length === 5 && $$(".diagnosis-panel").length === 5);
    add("all visible buttons bound", $$('button').every(button => button.id || button.dataset.panel || button.dataset.mapFilter || button.dataset.openPanel || button.classList.contains("project-delete") || button.classList.contains("similar-open") || button.classList.contains("lens-button") || button.classList.contains("topic-filter")));
    add("report links", $$("#reportLinks a").length >= 2);
    add("mail button", Boolean($("#sendReportEmail")));
    document.documentElement.dataset.selftest = checks.every(check => check.pass) ? "pass" : "fail";
    console.table(checks);
  }

  async function start() {
    try {
      await loadData();
      initMeta();
      initMap();
      initUpdates();
      initAnalytics();
      initTabs();
      initDataReady();
      initCurrent();
      initGap();
      initMeasures();
      initFeasibility();
      initDatabase();
      initReports();
      installServiceWorker();
      runSelfTest();
    } catch (error) {
      console.error(error);
      document.querySelector("main").innerHTML = `<div class="error-banner"><h1>网站数据未能加载</h1><p>${escapeHtml(error.message)}</p><p>请通过本地HTTP服务、GitHub Pages或其他静态站点访问。Windows可运行 <code>run.bat</code>。</p></div>`;
    }
  }

  start();
})();
