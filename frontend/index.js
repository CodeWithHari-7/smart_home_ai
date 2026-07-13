// Global state
let currentLoadId = 1;
let historyData = [];
let chartInstance = null;
let liveInterval = null;
let isLive = true;

// Initialize elements
document.addEventListener("DOMContentLoaded", () => {
    initClock();
    initSidebar();
    initTabs();
    initPredictionForm();
    initFilters();
    
    // Parse URL query parameters
    const urlParams = new URLSearchParams(window.location.search);
    const hall = urlParams.get('hall');
    const loadParam = urlParams.get('load');
    if (loadParam) {
        const loadVal = parseInt(loadParam);
        // Map odd loads (1, 3, 5) to Load 1 and even loads (2, 4) to Load 2
        currentLoadId = (loadVal % 2 === 0) ? 2 : 1;
        
        // Highlight active sidebar item
        const submenuItems = document.querySelectorAll(".submenu-item");
        submenuItems.forEach(item => {
            const dataLoad = parseInt(item.getAttribute("data-load"));
            if (dataLoad === currentLoadId) {
                item.classList.add("active");
            } else {
                item.classList.remove("active");
            }
        });
        
        // Update UI label
        const nodeLabel = document.querySelector(".active-node-label");
        if (nodeLabel) {
            nodeLabel.innerHTML = `${hall || "RengaIllamHall1"} &mdash; Load ${currentLoadId}`;
        }
    }
    
    // Fetch initial data
    loadDashboardData();
    
    // Set default dates for prediction to tomorrow at current time
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    document.getElementById("pred-date").value = tomorrow.toISOString().split('T')[0];
    
    const timeString = tomorrow.toTimeString().split(' ')[0].substring(0, 5);
    document.getElementById("pred-time").value = timeString;
    
    // Start Live updates polling by default (every 8 seconds, matching sensor frequency)
    toggleLive(true);
});

// 1. Real-time Clock
function initClock() {
    const clockEl = document.getElementById("header-clock");
    const timeEl = clockEl.querySelector(".time");
    const dateEl = clockEl.querySelector(".date");
    
    function updateClock() {
        const now = new Date();
        
        // Time format: HH:MM:SS PM
        let hours = now.getHours();
        const minutes = String(now.getMinutes()).padStart(2, '0');
        const seconds = String(now.getSeconds()).padStart(2, '0');
        const ampm = hours >= 12 ? 'PM' : 'AM';
        hours = hours % 12;
        hours = hours ? hours : 12; // 0 should be 12
        const hoursStr = String(hours).padStart(2, '0');
        
        timeEl.textContent = `${hoursStr}:${minutes}:${seconds} ${ampm}`;
        
        // Date format: Mon, 13 July 2026
        const options = { weekday: 'short', day: 'numeric', month: 'long', year: 'numeric' };
        dateEl.textContent = now.toLocaleDateString('en-US', options);
    }
    
    updateClock();
    setInterval(updateClock, 1000);
}

// 2. Sidebar load toggling
function initSidebar() {
    const dropdownTriggers = document.querySelectorAll(".dropdown-trigger");
    dropdownTriggers.forEach(trigger => {
        trigger.addEventListener("click", () => {
            const dropdown = trigger.parentElement;
            dropdown.classList.toggle("open");
        });
    });
    
    // Switch between Load 1 and Load 2
    const submenuItems = document.querySelectorAll(".submenu-item");
    submenuItems.forEach(item => {
        item.addEventListener("click", (e) => {
            e.preventDefault();
            submenuItems.forEach(i => i.classList.remove("active"));
            item.classList.add("active");
            
            currentLoadId = parseInt(item.getAttribute("data-load"));
            
            // Update UI label
            const nodeLabel = document.querySelector(".active-node-label");
            nodeLabel.innerHTML = `RengaiillamHall1 &mdash; Load ${currentLoadId}`;
            
            // Clear prediction results since we switched loads
            document.getElementById("prediction-results").classList.add("hidden");
            
            loadDashboardData();
        });
    });
    
    // Sidebar toggle for mobile devices
    const menuBtn = document.querySelector(".menu-toggle-btn");
    const closeBtn = document.querySelector(".sidebar-toggle-btn.mobile-only");
    const sidebar = document.querySelector(".sidebar");
    
    if (menuBtn && sidebar) {
        menuBtn.addEventListener("click", () => sidebar.classList.add("active"));
    }
    if (closeBtn && sidebar) {
        closeBtn.addEventListener("click", () => sidebar.classList.remove("active"));
    }
}

// 3. Load dashboard data from API
async function loadDashboardData() {
    try {
        const fromVal = document.getElementById("filter-from").value;
        const toVal = document.getElementById("filter-to").value;
        
        let url = `/api/history?load_id=${currentLoadId}&limit=100`;
        if (fromVal) url += `&from_date=${encodeURIComponent(fromVal)}`;
        if (toVal) url += `&to_date=${encodeURIComponent(toVal)}`;
        
        const response = await fetch(url);
        if (!response.ok) throw new Error("Database fetch error");
        
        historyData = await response.json();
        
        if (historyData.length === 0) {
            console.warn("No records returned from history API.");
            return;
        }
        
        updateLiveCards();
        updateSummaryMetrics();
        drawChart();
        updateTable();
        
    } catch (err) {
        console.error("Error loading dashboard data:", err);
    }
}

// Update the 6 top live cards with the latest record
function updateLiveCards() {
    const latest = historyData[historyData.length - 1];
    
    document.getElementById("val-voltage").innerHTML = `${latest.Voltage.toFixed(1)} <span class="unit">V</span>`;
    document.getElementById("val-current").innerHTML = `${latest.Current.toFixed(2)} <span class="unit">A</span>`;
    document.getElementById("val-power").innerHTML = `${latest.Power.toFixed(1)} <span class="unit">W</span>`;
    document.getElementById("val-pf").innerHTML = latest.PowerFactor.toFixed(2);
    document.getElementById("val-frequency").innerHTML = `${latest.Frequency.toFixed(1)} <span class="unit">Hz</span>`;
    document.getElementById("val-energy").innerHTML = `${latest.Energy.toFixed(2)} <span class="unit">kWh</span>`;
}

// Update the 4 middle cards (Peak Demand, Today's Energy, Cost, Status)
function updateSummaryMetrics() {
    // 1. Peak Demand (max power in historyData)
    const powers = historyData.map(d => d.Power);
    const peakPower = Math.max(...powers);
    document.getElementById("metric-peak").textContent = `${peakPower.toFixed(1)} W`;
    
    // 2. Today's Energy (max - min energy in the last 24h/records)
    const energies = historyData.map(d => d.Energy);
    const maxEnergy = Math.max(...energies);
    const minEnergy = Math.min(...energies);
    const energyConsumed = maxEnergy - minEnergy;
    document.getElementById("metric-today").textContent = `${energyConsumed.toFixed(2)} kWh`;
    
    // 3. Estimated Cost (energyConsumed * ₹ 8.00 per kWh tariff, matches screenshot costs)
    const cost = energyConsumed * 8.00;
    document.getElementById("metric-cost").textContent = `₹ ${cost.toFixed(2)}`;
    
    // 4. Status (ON if latest power > 10W)
    const latest = historyData[historyData.length - 1];
    const statusEl = document.getElementById("metric-status");
    if (latest.Power > 10.0) {
        statusEl.textContent = "ON";
        statusEl.className = "metric-value status-on";
    } else {
        statusEl.textContent = "OFF";
        statusEl.className = "metric-value";
    }
}

// Populate the historical table
function updateTable() {
    const tbody = document.getElementById("table-data-body");
    tbody.innerHTML = "";
    
    // Show newest first in table
    const tableRows = [...historyData].reverse().slice(0, 100);
    
    tableRows.forEach(row => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${row.Date_Time}</td>
            <td>${row.Voltage.toFixed(1)}</td>
            <td>${row.Current.toFixed(2)}</td>
            <td>${row.Power.toFixed(1)}</td>
            <td>${row.Frequency.toFixed(1)}</td>
            <td>${row.PowerFactor.toFixed(2)}</td>
            <td>${row.Energy.toFixed(2)}</td>
        `;
        tbody.appendChild(tr);
    });
}

// 4. Chart Visualization Tabs
function initTabs() {
    const tabs = document.querySelectorAll("#chart-metric-tabs .tab-btn");
    tabs.forEach(tab => {
        tab.addEventListener("click", () => {
            tabs.forEach(t => t.classList.remove("active"));
            tab.classList.add("active");
            drawChart();
        });
    });
}

// Get currently active chart metric
function getActiveChartMetric() {
    const activeTab = document.querySelector("#chart-metric-tabs .tab-btn.active");
    return activeTab ? activeTab.getAttribute("data-metric") : "all";
}

// Render chart using Chart.js
function drawChart(predictedPoint = null) {
    const ctx = document.getElementById("energyChart").getContext("2d");
    const activeMetric = getActiveChartMetric();
    
    if (chartInstance) {
        chartInstance.destroy();
    }
    
    const labels = historyData.map(d => d.Date_Time);
    
    // Datasets mapping
    const metricsConfig = {
        Voltage: { label: "Voltage (V)", data: historyData.map(d => d.Voltage), color: "#ffd600", yAxis: "y" },
        Current: { label: "Current (A)", data: historyData.map(d => d.Current), color: "#ff1744", yAxis: "y" },
        Power: { label: "Power (W)", data: historyData.map(d => d.Power), color: "#ff9100", yAxis: "y" },
        Frequency: { label: "Frequency (Hz)", data: historyData.map(d => d.Frequency), color: "#e040fb", yAxis: "y" },
        PowerFactor: { label: "Power Factor", data: historyData.map(d => d.PowerFactor), color: "#2979ff", yAxis: "y" },
        Energy: { label: "Energy (kWh)", data: historyData.map(d => d.Energy), color: "#00e676", yAxis: "y" }
    };
    
    let datasets = [];
    
    // Helper to format chart lines beautifully
    function getLineConfig(label, data, color, yAxis, isPredicted = false) {
        return {
            label: label + (isPredicted ? " (AI Predicted)" : ""),
            data: data,
            borderColor: color,
            backgroundColor: isPredicted ? "transparent" : `${color}1A`, // 10% opacity area fill
            borderWidth: isPredicted ? 2 : 2.5,
            borderDash: isPredicted ? [6, 4] : [], // Dotted line for forecast
            tension: 0.2,
            pointRadius: isPredicted ? 5 : 2,
            pointBackgroundColor: color,
            fill: !isPredicted,
            yAxisID: yAxis
        };
    }
    
    if (activeMetric === "all") {
        // Show all series
        Object.keys(metricsConfig).forEach(key => {
            const config = metricsConfig[key];
            
            let dataArr = [...config.data];
            // If predicted point is supplied, append it
            if (predictedPoint) {
                // If it's the target parameter
                const metricKeyLower = key === "PowerFactor" ? "power_factor" : key.toLowerCase();
                dataArr.push(predictedPoint.predictions[metricKeyLower]);
            }
            
            datasets.push(getLineConfig(config.label, dataArr, config.color, config.yAxis));
        });
    } else {
        // Show single active series
        const config = metricsConfig[activeMetric];
        let dataArr = [...config.data];
        
        if (predictedPoint) {
            const metricKeyLower = activeMetric === "PowerFactor" ? "power_factor" : activeMetric.toLowerCase();
            dataArr.push(predictedPoint.predictions[metricKeyLower]);
        }
        
        // Push actual line
        datasets.push(getLineConfig(config.label, dataArr, config.color, config.yAxis));
    }
    
    // Add vertical line marker or dynamic label for prediction
    if (predictedPoint) {
        labels.push(predictedPoint.time);
    }
    
    // Chart Options
    const chartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                position: 'top',
                labels: {
                    color: '#8f9cae',
                    font: { family: 'Outfit', size: 12 }
                }
            },
            tooltip: {
                backgroundColor: '#161920',
                titleColor: '#ffffff',
                bodyColor: '#c9d1d9',
                borderColor: '#222636',
                borderWidth: 1,
                callbacks: {
                    label: function(context) {
                        let label = context.dataset.label || '';
                        if (label) label += ': ';
                        if (context.parsed.y !== null) {
                            label += context.parsed.y.toFixed(2);
                        }
                        return label;
                    }
                }
            }
        },
        scales: {
            x: {
                grid: { color: '#161920' },
                ticks: {
                    color: '#8f9cae',
                    font: { family: 'Outfit', size: 10 },
                    maxRotation: 45,
                    minRotation: 45
                }
            },
            y: {
                grid: { color: '#161920' },
                ticks: {
                    color: '#8f9cae',
                    font: { family: 'Roboto', size: 11 }
                }
            }
        }
    };
    
    chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: datasets
        },
        options: chartOptions
    });
}

// 5. Prediction Form Logic
function initPredictionForm() {
    const form = document.getElementById("prediction-form");
    const btnPredict = document.getElementById("btn-predict");
    const btnText = btnPredict.querySelector(".btn-text");
    const spinner = btnPredict.querySelector(".spinner");
    const resultsContainer = document.getElementById("prediction-results");
    const errorContainer = document.getElementById("prediction-error");
    
    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const dateVal = document.getElementById("pred-date").value;
        const timeVal = document.getElementById("pred-time").value;
        
        // Show loading state
        btnPredict.disabled = true;
        btnText.classList.add("hidden");
        spinner.classList.remove("hidden");
        errorContainer.classList.add("hidden");
        
        try {
            const res = await fetch("/api/predict-energy", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    date: dateVal,
                    time: timeVal,
                    load_id: currentLoadId
                })
            });
            
            const data = await res.json();
            
            if (!res.ok) {
                throw new Error(data.detail || data.error || "Prediction request failed.");
            }
            
            // Format time for result display
            const formattedTime = new Date(`${dateVal}T${timeVal}`).toLocaleString('en-US', {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
            
            // Display Results
            document.getElementById("pred-result-time").textContent = formattedTime;
            document.getElementById("pred-result-horizon").textContent = data.model_information.forecast_horizon;
            
            const preds = data.predictions;
            document.getElementById("pred-voltage").innerHTML = `${preds.voltage.toFixed(1)} <span class="unit">V</span>`;
            document.getElementById("pred-current").innerHTML = `${preds.current.toFixed(2)} <span class="unit">A</span>`;
            document.getElementById("pred-power").innerHTML = `${preds.power.toFixed(1)} <span class="unit">W</span>`;
            document.getElementById("pred-pf").innerHTML = preds.power_factor.toFixed(2);
            document.getElementById("pred-frequency").innerHTML = `${preds.frequency.toFixed(1)} <span class="unit">Hz</span>`;
            document.getElementById("pred-energy").innerHTML = `${preds.energy.toFixed(2)} <span class="unit">kWh</span>`;
            
            // Populate model evaluation metrics
            populateMetricsTable(data.model_information.evaluation_metrics);
            
            // Show result container
            resultsContainer.classList.remove("hidden");
            
            // Re-draw chart with the forecasted point added
            drawChart({
                time: `${dateVal} ${timeVal}`,
                predictions: preds
            });
            
        } catch (err) {
            console.error("Prediction Error:", err);
            document.getElementById("error-message").textContent = err.message;
            errorContainer.classList.remove("hidden");
            resultsContainer.classList.add("hidden");
        } finally {
            // Restore button state
            btnPredict.disabled = false;
            btnText.classList.remove("hidden");
            spinner.classList.add("hidden");
        }
    });
}

function populateMetricsTable(metrics) {
    const tbody = document.getElementById("metrics-eval-body");
    tbody.innerHTML = "";
    
    const mapping = {
        "Voltage": "XGBoost Regressor",
        "Current": "XGBoost Regressor",
        "Power": "Physical Relation (V x I x PF)",
        "Frequency": "XGBoost Regressor",
        "PowerFactor": "XGBoost Regressor",
        "Energy": "Linear Trend + XGBoost Residual"
    };
    
    Object.keys(metrics).forEach(target => {
        const tr = document.createElement("tr");
        const m = metrics[target];
        
        tr.innerHTML = `
            <td><strong>${target}</strong></td>
            <td>${mapping[target] || "XGBoost Model"}</td>
            <td>${m.MAE.toFixed(4)}</td>
            <td>${m.RMSE.toFixed(4)}</td>
            <td>${m.R2 !== null ? m.R2.toFixed(3) : "N/A"}</td>
        `;
        tbody.appendChild(tr);
    });
}

// 6. Live polling controls
function toggleLive(enable) {
    const btnLive = document.getElementById("btn-live");
    isLive = enable;
    
    if (enable) {
        btnLive.classList.add("active");
        if (!liveInterval) {
            liveInterval = setInterval(loadDashboardData, 8000); // Poll database every 8 seconds
        }
    } else {
        btnLive.classList.remove("active");
        if (liveInterval) {
            clearInterval(liveInterval);
            liveInterval = null;
        }
    }
}

function initFilters() {
    document.getElementById("btn-filter").addEventListener("click", () => {
        toggleLive(false); // Stop live polling when filter is applied
        loadDashboardData();
    });
    
    document.getElementById("btn-live").addEventListener("click", () => {
        // Toggle live updates
        toggleLive(!isLive);
        if (isLive) {
            // Clear filter inputs
            document.getElementById("filter-from").value = "";
            document.getElementById("filter-to").value = "";
            loadDashboardData();
        }
    });
    
    document.getElementById("btn-export").addEventListener("click", () => {
        const fromVal = document.getElementById("filter-from").value;
        const toVal = document.getElementById("filter-to").value;
        window.location.href = `/api/export?load_id=${currentLoadId}&from_date=${encodeURIComponent(fromVal)}&to_date=${encodeURIComponent(toVal)}`;
    });
}
