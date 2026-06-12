/**
 * 前端应用逻辑 — 任务管理、SSE 事件监听、DOM 更新。
 */
(function () {
    "use strict";

    // ========== DOM 元素 ==========
    const $ = (sel) => document.querySelector(sel);
    const taskForm = $("#taskForm");
    const taskContainer = $("#taskContainer");
    const emptyState = $("#emptyState");
    const configStatus = $("#configStatus");
    const btnCleanup = $("#btnCleanup");
    const tabs = document.querySelectorAll(".tab");

    // ========== 状态 ==========
    let currentFilter = "all";
    let allTasks = [];
    let config = {};
    let expandedTasks = new Set();
    let lastRefresh = 0;
    let pendingRefresh = null;

    /**SSE 事件节流刷新：最多 5 秒一次。*/
    function throttledRefresh() {
        const now = Date.now();
        const elapsed = now - lastRefresh;
        if (elapsed >= 5000) {
            lastRefresh = now;
            loadTasks();
        } else if (!pendingRefresh) {
            pendingRefresh = setTimeout(() => {
                pendingRefresh = null;
                lastRefresh = Date.now();
                loadTasks();
            }, 5000 - elapsed);
        }
    }

    // ========== API 调用 ==========

    async function api(url, options = {}) {
        const resp = await fetch(url, options);
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || "Request failed");
        }
        return resp.json();
    }

    // ========== 配置加载 ==========

    async function loadConfig() {
        config = await api("/api/config");
        renderConfigStatus();
        updateHfOptions();
        $("#platform").addEventListener("change", updateHfOptions);
    }

    function updateHfOptions() {
        $("#hfOptions").style.display = $("#platform").value === "huggingface" ? "" : "none";
    }

    function getHfMode() {
        return $("#hfMode").value;
    }

    function renderConfigStatus() {
        const tags = [
            { label: "HF Token", on: config.has_hf_token },
            { label: "MS Token", on: config.has_ms_token },
            { label: "代理", on: config.has_proxy },
            { label: "镜像", on: config.has_mirror },
        ];
        configStatus.innerHTML = tags
            .map((t) => `<span class="tag ${t.on ? "on" : "off"}">${t.label} ${t.on ? "✓" : "✗"}</span>`)
            .join("");
    }

    // ========== 任务列表 ==========

    async function loadTasks() {
        allTasks = await api("/api/tasks");
        renderTasks();
    }

    function renderTasks() {
        const filtered =
            currentFilter === "all" ? allTasks : allTasks.filter((t) => t.status === currentFilter);

        if (filtered.length === 0) {
            taskContainer.innerHTML = "";
            emptyState.style.display = "block";
            return;
        }

        emptyState.style.display = "none";
        taskContainer.innerHTML = filtered.map(renderTaskCard).join("");
    }

    function renderTaskCard(task) {
        const statusMap = {
            pending: "排队中",
            running: "下载中",
            completed: "已完成",
            failed: "失败",
            cancelled: "已取消",
        };
        const platformLabel = task.platform === "huggingface" ? "HuggingFace" : "ModelScope";
        const progressPct = Math.round(task.progress * 100);

        let actions = "";
        if (task.status === "running") {
            actions = `<button class="btn-outline danger" onclick="cancelTask('${task.id}')">取消</button>`;
        } else if (task.status === "failed" || task.status === "cancelled") {
            actions = `
                <button class="btn-outline info" onclick="retryTask('${task.id}')">重试</button>
                <button class="btn-outline danger" onclick="deleteTask('${task.id}')">删除</button>`;
        } else if (task.status === "completed") {
            actions = `<button class="btn-outline danger" onclick="deleteTask('${task.id}')">删除</button>`;
        } else if (task.status === "pending") {
            actions = `<button class="btn-outline danger" onclick="deleteTask('${task.id}')">取消</button>`;
        }

        let progressHtml = "";
        if (task.status === "running") {
            // 子文件信息
            let fileLine = "";
            if (task.current_file) {
                const fileCount = task.files_total > 0
                    ? ` (${task.files_done}/${task.files_total})` : "";
                fileLine = `<div class="task-file">正在下载: ${task.current_file}${fileCount}</div>`;
            }
            progressHtml = `
                ${fileLine}
                <div class="progress-bar"><div class="fill" style="width:${progressPct}%"></div></div>
                <div class="task-meta">
                    <span>${progressPct}% ${task.speed ? "— " + task.speed : ""}</span>
                    <span>${formatSize(task.downloaded)} / ${formatSize(task.total)}</span>
                </div>`;
        } else if (task.status === "completed") {
            progressHtml = `<div class="task-info">总大小: ${formatSize(task.total)} — ${task.save_path || ""}</div>`;
        } else if (task.status === "failed") {
            progressHtml = `<div class="task-error">${task.error_msg || "未知错误"}</div>`;
        }

        // 可展开的文件列表
        let fileExpandHtml = "";
        let files = [];
        try { files = task.files_json ? JSON.parse(task.files_json) : []; } catch { files = []; }

        if (files.length > 0 && (task.status === "running" || task.status === "completed")) {
            const isExpanded = expandedTasks.has(task.id);
            const fileItems = files.map(function (f) {
                const pct = f.size > 0 ? Math.round(f.downloaded / f.size * 100) : 0;
                const doneMark = f.status === "done" ? " ✓" : "";
                return '<div class="file-item ' + (f.status === "done" ? "done" : "") + '">'
                    + '<div class="file-info">'
                    + '<span class="file-name">' + escapeHtml(f.name) + '</span>'
                    + '<span class="file-pct">' + pct + '%' + doneMark + '</span>'
                    + '</div>'
                    + '<div class="file-progress-bar"><div class="file-fill" style="width:' + pct + '%"></div></div>'
                    + '</div>';
            }).join("");

            fileExpandHtml = '<div class="file-expand-toggle" onclick="toggleFiles(\'' + task.id + '\')">'
                + '<span class="expand-icon ' + (isExpanded ? "expanded" : "") + '">▶</span>'
                + '<span>文件列表 (' + files.length + ')</span>'
                + '</div>'
                + '<div class="file-list" id="files-' + task.id + '" style="display:' + (isExpanded ? "block" : "none") + '">'
                + fileItems
                + '</div>';
        }

        return `
            <div class="task-card ${task.status}" data-id="${task.id}">
                <div class="task-header">
                    <div class="left">
                        <span class="repo">${task.repo_id}</span>
                        <span class="platform">${platformLabel}</span>
                        <span class="status-tag ${task.status}">${statusMap[task.status]}</span>
                    </div>
                    <div class="actions">${actions}</div>
                </div>
                ${progressHtml}
                ${fileExpandHtml}
            </div>`;
    }

    // ========== 工具函数 ==========

    function formatSize(bytes) {
        if (!bytes || bytes === 0) return "—";
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
        if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
        return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB";
    }

    function escapeHtml(text) {
        var d = document.createElement("div");
        d.textContent = text;
        return d.innerHTML;
    }

    // ========== 事件处理 ==========

    taskForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const platform = $("#platform").value;
        const hfMode = platform === "huggingface" ? getHfMode() : "none";
        const body = {
            repo_id: $("#repoId").value.trim(),
            platform: platform,
            use_proxy: hfMode === "proxy",
            use_mirror: hfMode === "mirror",
        };
        const filename = $("#filename").value.trim();
        if (filename) body.filename = filename;

        try {
            await api("/api/tasks", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            $("#repoId").value = "";
            $("#filename").value = "";
            await loadTasks();
        } catch (err) {
            alert("创建任务失败: " + err.message);
        }
    });

    window.cancelTask = async function (id) {
        try {
            await api(`/api/tasks/${id}`, { method: "DELETE" });
            await loadTasks();
        } catch (err) {
            alert("取消失败: " + err.message);
        }
    };

    window.deleteTask = async function (id) {
        try {
            await api(`/api/tasks/${id}`, { method: "DELETE" });
            await loadTasks();
        } catch (err) {
            alert("删除失败: " + err.message);
        }
    };

    window.retryTask = async function (id) {
        try {
            await api(`/api/tasks/${id}/retry`, { method: "POST" });
            await loadTasks();
        } catch (err) {
            alert("重试失败: " + err.message);
        }
    };

    window.toggleFiles = function (taskId) {
        var el = document.getElementById("files-" + taskId);
        if (!el) return;
        var toggle = el.previousElementSibling;
        var icon = toggle ? toggle.querySelector(".expand-icon") : null;
        var isVisible = el.style.display !== "none";
        el.style.display = isVisible ? "none" : "block";
        if (icon) icon.classList.toggle("expanded");
        if (isVisible) {
            expandedTasks.delete(taskId);
        } else {
            expandedTasks.add(taskId);
        }
    };

    // Tab 切换
    tabs.forEach((tab) => {
        tab.addEventListener("click", () => {
            tabs.forEach((t) => t.classList.remove("active"));
            tab.classList.add("active");
            currentFilter = tab.dataset.status;
            renderTasks();
        });
    });

    // 清理记录
    btnCleanup.addEventListener("click", async () => {
        // 清理当前筛选状态的任务
        const status = currentFilter === "all" ? null : currentFilter;
        if (!status) {
            alert("请先选择要清理的状态类型（已完成/失败）");
            return;
        }
        if (!confirm(`确定要清理所有${status === "completed" ? "已完成" : "失败"}的记录吗？`)) return;

        try {
            const result = await api(`/api/tasks?status=${status}`, { method: "DELETE" });
            alert(`已清理 ${result.deleted} 条记录`);
            await loadTasks();
        } catch (err) {
            alert("清理失败: " + err.message);
        }
    });

    // ========== SSE 全局事件 ==========

    function connectSSE() {
        const source = new EventSource("/api/events");
        source.onmessage = (event) => {
            try {
                JSON.parse(event.data);
                // 节流刷新，最多 5 秒一次
                throttledRefresh();
            } catch { /* ignore parse errors */ }
        };
        source.onerror = () => {
            // 断线重连由浏览器自动处理
        };
    }

    // ========== 初始化 ==========

    async function init() {
        await loadConfig();
        await loadTasks();
        connectSSE();
    }

    init();
})();
