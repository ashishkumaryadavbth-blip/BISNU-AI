"use strict";

/*
    BISNU-X FRONTEND

    Existing backend compatibility:
        GET  /health
        POST /v1/chat

    Request:
    {
        messages: [...],
        model: "auto" | "qwen" | "llama",
        live_search: true | false
    }
*/


/* =========================================================
   CONFIG
========================================================= */

const API_BASE = "";

const HEALTH_URL = `${API_BASE}/health`;
const CHAT_URL = `${API_BASE}/v1/chat`;

const STORAGE_USER = "bisnu_user";
const STORAGE_CHATS = "bisnu_chats_v2";
const STORAGE_CURRENT = "bisnu_current_chat_v2";
const STORAGE_MODEL = "bisnu_model_v2";
const STORAGE_LIVE = "bisnu_live_search_v2";


/* =========================================================
   STATE
========================================================= */

let state = {
    user: null,
    chats: [],
    currentChatId: null,

    model: localStorage.getItem(STORAGE_MODEL) || "auto",
    liveSearch:
        localStorage.getItem(STORAGE_LIVE) === "true",

    generating: false,
    controller: null
};


/* =========================================================
   DOM
========================================================= */

const $ = (selector) =>
    document.querySelector(selector);

const $$ = (selector) =>
    document.querySelectorAll(selector);

const splashScreen = $("#splashScreen");
const loginScreen = $("#loginScreen");
const app = $("#app");

const googleLoginBtn = $("#googleLoginBtn");

const messages = $("#messages");
const emptyState = $("#emptyState");

const messageInput = $("#messageInput");
const sendBtn = $("#sendBtn");

const chatHistory = $("#chatHistory");

const selectedModel = $("#selectedModel");
const modelBtn = $("#modelBtn");
const modelMenu = $("#modelMenu");

const liveSearchToggle = $("#liveSearchToggle");

const connectionStatus = $("#connectionStatus");

const chatTitle = $("#chatTitle");

const toast = $("#toast");

const chatView = $("#chatView");
const appsView = $("#appsView");

const sidebar = $("#sidebar");
const sidebarOverlay = $("#sidebarOverlay");


/* =========================================================
   STARTUP
========================================================= */

document.addEventListener("DOMContentLoaded", () => {

    liveSearchToggle.checked = state.liveSearch;

    updateModelUI();

    setTimeout(() => {

        splashScreen.classList.add("hidden");

        const savedUser =
            localStorage.getItem(STORAGE_USER);

        if (savedUser) {

            try {
                state.user = JSON.parse(savedUser);
                enterApp();
            } catch {
                showLogin();
            }

        } else {
            showLogin();
        }

    }, 1100);

    setupEvents();

    checkHealth();

    setInterval(checkHealth, 30000);
});


/* =========================================================
   LOGIN
========================================================= */

function showLogin() {

    splashScreen.classList.add("hidden");
    app.classList.add("hidden");

    loginScreen.classList.remove("hidden");
}


function enterApp() {

    loginScreen.classList.add("hidden");
    splashScreen.classList.add("hidden");

    app.classList.remove("hidden");

    loadChats();

    if (!state.currentChatId) {
        createNewChat(false);
    } else {
        renderCurrentChat();
    }

    updateUserUI();
}


googleLoginBtn.addEventListener("click", () => {

    /*
       IMPORTANT:
       This is the frontend entry point.

       For REAL Google OAuth, replace this handler
       with your backend/Firebase/Supabase OAuth flow.

       No fake Google authentication is performed here.
    */

    const existing =
        localStorage.getItem(STORAGE_USER);

    if (existing) {
        enterApp();
        return;
    }

    /*
       Temporary local session so the complete UI
       can be tested before OAuth backend is connected.
    */

    const user = {
        name: "Google User",
        email: "",
        avatar: "G"
    };

    state.user = user;

    localStorage.setItem(
        STORAGE_USER,
        JSON.stringify(user)
    );

    showToast("Google login connected to the UI");

    enterApp();
});


function updateUserUI() {

    if (!state.user) return;

    const name =
        state.user.name ||
        "Google User";

    $("#userName").textContent = name;

    $("#userAvatar").textContent =
        name.trim().charAt(0).toUpperCase() || "G";
}


/* =========================================================
   LOGOUT
========================================================= */

$("#logoutBtn").addEventListener("click", () => {

    localStorage.removeItem(STORAGE_USER);

    state.user = null;

    closeSidebar();

    showLogin();

    showToast("Logged out");
});


/* =========================================================
   EVENTS
========================================================= */

function setupEvents() {

    /* New chat */

    $("#newChatBtn").addEventListener(
        "click",
        () => createNewChat(true)
    );


    /* Sidebar */

    $("#openSidebarBtn").addEventListener(
        "click",
        openSidebar
    );

    $("#closeSidebarBtn").addEventListener(
        "click",
        closeSidebar
    );

    sidebarOverlay.addEventListener(
        "click",
        closeSidebar
    );


    /* Model */

    modelBtn.addEventListener("click", (event) => {

        event.stopPropagation();

        modelMenu.classList.toggle("open");
    });

    $$("#modelMenu button").forEach(button => {

        button.addEventListener("click", () => {

            state.model =
                button.dataset.model;

            localStorage.setItem(
                STORAGE_MODEL,
                state.model
            );

            updateModelUI();

            modelMenu.classList.remove("open");
        });

    });

    document.addEventListener("click", () => {
        modelMenu.classList.remove("open");
    });


    /* Live Search */

    liveSearchToggle.addEventListener(
        "change",
        () => {

            state.liveSearch =
                liveSearchToggle.checked;

            localStorage.setItem(
                STORAGE_LIVE,
                String(state.liveSearch)
            );
        }
    );


    /* Send */

    sendBtn.addEventListener(
        "click",
        handleSend
    );


    messageInput.addEventListener(
        "keydown",
        (event) => {

            if (
                event.key === "Enter" &&
                !event.shiftKey
            ) {

                event.preventDefault();

                handleSend();
            }
        }
    );


    messageInput.addEventListener(
        "input",
        autoResizeTextarea
    );


    /* Suggestions */

    $$(".suggestion-card").forEach(card => {

        card.addEventListener("click", () => {

            const prompt =
                card.dataset.prompt || "";

            messageInput.value = prompt;

            autoResizeTextarea();

            messageInput.focus();
        });

    });


    /* Navigation */

    $$(".nav-item").forEach(item => {

        item.addEventListener("click", () => {

            const view =
                item.dataset.view;

            if (view === "apps") {
                showApps();
            } else {
                showChat();
            }

            closeSidebar();
        });

    });


    $("#backToChatBtn").addEventListener(
        "click",
        showChat
    );


    $$(".open-app-btn").forEach(button => {

        button.addEventListener("click", () => {
            showChat();
            messageInput.focus();
        });

    });


    /* Settings */

    $("#settingsBtn").addEventListener(
        "click",
        () => {
            $("#settingsModal").classList.remove("hidden");
        }
    );

    $("#closeSettingsBtn").addEventListener(
        "click",
        closeSettings
    );

    $(".modal-backdrop").addEventListener(
        "click",
        closeSettings
    );


    $("#clearChatsBtn").addEventListener(
        "click",
        clearAllChats
    );


    /* Search */

    $("#searchChatsBtn").addEventListener(
        "click",
        searchChats
    );


    /* Attach */

    $("#attachBtn").addEventListener(
        "click",
        () => {
            showToast("File upload can be connected to the backend next");
        }
    );


    /* Voice */

    $("#voiceBtn").addEventListener(
        "click",
        startVoiceInput
    );


    /* Keyboard */

    document.addEventListener("keydown", event => {

        if (
            (event.ctrlKey || event.metaKey) &&
            event.key.toLowerCase() === "k"
        ) {

            event.preventDefault();

            messageInput.focus();
        }

    });
}


/* =========================================================
   MODEL
========================================================= */

function updateModelUI() {

    const names = {
        auto: "BISNU AUTO",
        qwen: "Qwen",
        llama: "Llama"
    };

    selectedModel.textContent =
        names[state.model] || "BISNU AUTO";
}


/* =========================================================
   HEALTH
========================================================= */

async function checkHealth() {

    try {

        const response =
            await fetch(HEALTH_URL, {
                method: "GET",
                cache: "no-store"
            });

        if (!response.ok) {
            throw new Error("Health check failed");
        }

        const data =
            await response.json().catch(() => ({}));

        setConnection(
            true,
            data.status || "Connected"
        );

    } catch {

        setConnection(
            false,
            "Backend offline"
        );
    }
}


function setConnection(online, text) {

    const dot =
        connectionStatus.querySelector(".status-dot");

    const label =
        connectionStatus.querySelector("span:last-child");

    dot.classList.toggle("online", online);
    dot.classList.toggle("offline", !online);

    label.textContent =
        text || (online ? "Connected" : "Offline");
}


/* =========================================================
   CHAT DATA
========================================================= */

function loadChats() {

    try {

        state.chats =
            JSON.parse(
                localStorage.getItem(STORAGE_CHATS)
            ) || [];

    } catch {
        state.chats = [];
    }

    state.currentChatId =
        localStorage.getItem(STORAGE_CURRENT);

    renderHistory();
}


function saveChats() {

    localStorage.setItem(
        STORAGE_CHATS,
        JSON.stringify(state.chats)
    );

    if (state.currentChatId) {

        localStorage.setItem(
            STORAGE_CURRENT,
            state.currentChatId
        );
    }
}


function createNewChat(autoSave = true) {

    const chat = {

        id:
            "chat_" +
            Date.now() +
            "_" +
            Math.random()
                .toString(36)
                .slice(2, 7),

        title: "New chat",

        createdAt:
            new Date().toISOString(),

        messages: []
    };

    state.chats.unshift(chat);

    state.currentChatId = chat.id;

    if (autoSave) {
        saveChats();
    }

    renderHistory();
    renderCurrentChat();

    showChat();

    messageInput.focus();

    closeSidebar();
}


function getCurrentChat() {

    return state.chats.find(
        chat =>
            chat.id === state.currentChatId
    );
}


/* =========================================================
   RENDER HISTORY
========================================================= */

function renderHistory() {

    chatHistory.innerHTML = "";

    state.chats
        .slice(0, 50)
        .forEach(chat => {

            const button =
                document.createElement("button");

            button.className =
                "history-item";

            if (
                chat.id ===
                state.currentChatId
            ) {
                button.classList.add("active");
            }

            button.textContent =
                chat.title || "New chat";

            button.title =
                chat.title || "New chat";

            button.addEventListener(
                "click",
                () => {

                    state.currentChatId =
                        chat.id;

                    saveChats();

                    renderHistory();
                    renderCurrentChat();
                    showChat();

                    closeSidebar();
                }
            );

            chatHistory.appendChild(button);
        });
}


/* =========================================================
   RENDER CURRENT CHAT
========================================================= */

function renderCurrentChat() {

    messages.innerHTML = "";

    const chat =
        getCurrentChat();

    if (!chat || !chat.messages.length) {

        messages.appendChild(emptyState);

        emptyState.classList.remove("hidden");

        chatTitle.textContent =
            chat?.title || "New chat";

        return;
    }

    emptyState.classList.add("hidden");

    chat.messages.forEach(
        message =>
            renderMessage(message)
    );

    chatTitle.textContent =
        chat.title || "New chat";

    scrollToBottom();
}


/* =========================================================
   ADD MESSAGE
========================================================= */

function addMessage(role, content, extra = {}) {

    const chat =
        getCurrentChat();

    if (!chat) return null;

    const message = {

        id:
            "msg_" +
            Date.now() +
            "_" +
            Math.random()
                .toString(36)
                .slice(2, 7),

        role,
        content,

        timestamp:
            new Date().toISOString(),

        ...extra
    };

    chat.messages.push(message);

    if (
        role === "user" &&
        chat.title === "New chat"
    ) {

        chat.title =
            createChatTitle(content);
    }

    saveChats();
    renderHistory();

    return message;
}


function createChatTitle(text) {

    const clean =
        text
            .replace(/\s+/g, " ")
            .trim();

    if (!clean) return "New chat";

    return clean.length > 38
        ? clean.slice(0, 38) + "..."
        : clean;
}


/* =========================================================
   RENDER MESSAGE
========================================================= */

function renderMessage(message) {

    const row =
        document.createElement("div");

    row.className =
        `message-row ${message.role}`;

    const avatar =
        document.createElement("div");

    avatar.className =
        "message-avatar";

    avatar.textContent =
        message.role === "user"
            ? getUserInitial()
            : "B";

    const content =
        document.createElement("div");

    content.className =
        "message-content";

    const role =
        document.createElement("div");

    role.className =
        "message-role";

    role.textContent =
        message.role === "user"
            ? "YOU"
            : "BISNU AI";

    const bubble =
        document.createElement("div");

    bubble.className =
        `bubble ${
            message.role === "user"
                ? "user-bubble"
                : "ai-bubble"
        }`;

    bubble.textContent =
        message.content || "";

    content.appendChild(role);
    content.appendChild(bubble);


    /* AI actions */

    if (message.role === "assistant") {

        const actions =
            document.createElement("div");

        actions.className =
            "message-actions";

        const copyBtn =
            document.createElement("button");

        copyBtn.textContent = "⧉";
        copyBtn.title = "Copy";

        copyBtn.addEventListener(
            "click",
            () => copyText(message.content)
        );


        const regenerateBtn =
            document.createElement("button");

        regenerateBtn.textContent = "↻";
        regenerateBtn.title = "Regenerate";

        regenerateBtn.addEventListener(
            "click",
            () => regenerate(message.id)
        );

        actions.appendChild(copyBtn);
        actions.appendChild(regenerateBtn);

        content.appendChild(actions);


        /* Live evidence */

        if (
            message.live_evidence &&
            Array.isArray(message.live_evidence) &&
            message.live_evidence.length
        ) {

            const evidence =
                document.createElement("div");

            evidence.className =
                "live-evidence";

            const title =
                document.createElement("div");

            title.className =
                "live-evidence-title";

            title.textContent =
                "LIVE SEARCH EVIDENCE";

            evidence.appendChild(title);

            message.live_evidence
                .slice(0, 8)
                .forEach(source => {

                    const link =
                        document.createElement("a");

                    const url =
                        typeof source === "string"
                            ? source
                            : source.url || source.link || "#";

                    link.href = url;
                    link.target = "_blank";
                    link.rel = "noopener noreferrer";

                    link.textContent =
                        typeof source === "string"
                            ? source
                            : source.title ||
                              source.name ||
                              url;

                    evidence.appendChild(link);
                });

            content.appendChild(evidence);
        }
    }


    row.appendChild(avatar);
    row.appendChild(content);

    messages.appendChild(row);

    return row;
}


/* =========================================================
   THINKING
========================================================= */

function showThinking() {

    removeThinking();

    const row =
        document.createElement("div");

    row.id =
        "thinkingMessage";

    row.className =
        "message-row assistant";

    const avatar =
        document.createElement("div");

    avatar.className =
        "message-avatar";

    avatar.textContent = "B";

    const content =
        document.createElement("div");

    content.className =
        "message-content";

    const role =
        document.createElement("div");

    role.className =
        "message-role";

    role.textContent =
        "BISNU AI";

    const bubble =
        document.createElement("div");

    bubble.className =
        "thinking-bubble";

    const top =
        document.createElement("div");

    top.className =
        "thinking-top";

    top.innerHTML = `
        <span>BISNU AI IS THINKING</span>
        <span class="thinking-dots">
            <span></span>
            <span></span>
            <span></span>
        </span>
    `;

    const text =
        document.createElement("div");

    text.className =
        "thinking-text";

    text.textContent =
        state.liveSearch
            ? "Processing your request and checking live information..."
            : "Processing your request...";

    bubble.appendChild(top);
    bubble.appendChild(text);

    content.appendChild(role);
    content.appendChild(bubble);

    row.appendChild(avatar);
    row.appendChild(content);

    messages.appendChild(row);

    scrollToBottom();
}


function removeThinking() {

    const thinking =
        $("#thinkingMessage");

    if (thinking) {
        thinking.remove();
    }
}


/* =========================================================
   SEND
========================================================= */

async function handleSend() {

    if (state.generating) {

        stopGeneration();

        return;
    }

    const text =
        messageInput.value.trim();

    if (!text) return;

    let chat =
        getCurrentChat();

    if (!chat) {

        createNewChat(false);

        chat =
            getCurrentChat();
    }


    /* User message */

    addMessage(
        "user",
        text
    );

    messageInput.value = "";

    autoResizeTextarea();

    renderCurrentChat();

    showThinking();

    setGenerating(true);


    try {

        state.controller =
            new AbortController();


        /*
            IMPORTANT:
            Existing backend connection remains:
                POST /v1/chat

            Same request structure as previous version.
        */

        const response =
            await fetch(CHAT_URL, {

                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({

                    messages:
                        chat.messages.map(message => ({
                            role:
                                message.role === "assistant"
                                    ? "assistant"
                                    : "user",

                            content:
                                message.content
                        })),

                    model:
                        state.model,

                    live_search:
                        state.liveSearch
                }),

                signal:
                    state.controller.signal
            });


        const data =
            await response.json()
                .catch(() => ({}));


        if (!response.ok) {

            throw new Error(
                data.detail ||
                data.error ||
                `Server error ${response.status}`
            );
        }


        const answer =
            data.answer ||
            data.response ||
            data.message ||
            data.content ||
            "BISNU-X did not return an answer.";


        removeThinking();


        addMessage(
            "assistant",
            String(answer),
            {
                model:
                    data.model ||
                    state.model,

                live_evidence:
                    data.live_evidence ||
                    data.sources ||
                    []
            }
        );


        renderCurrentChat();


    } catch (error) {

        removeThinking();

        if (
            error.name ===
            "AbortError"
        ) {

            showToast("Generation stopped");

        } else {

            addMessage(
                "assistant",
                "Sorry, BISNU-X could not connect to the backend.\n\n" +
                error.message
            );

            renderCurrentChat();

            showToast("Backend connection error");
        }

    } finally {

        state.controller = null;

        setGenerating(false);
    }
}


/* =========================================================
   STOP
========================================================= */

function stopGeneration() {

    if (state.controller) {
        state.controller.abort();
    }
}


/* =========================================================
   GENERATING UI
========================================================= */

function setGenerating(value) {

    state.generating = value;

    if (value) {

        sendBtn.classList.add("stop");

        sendBtn.textContent = "■";

        sendBtn.title = "Stop";

    } else {

        sendBtn.classList.remove("stop");

        sendBtn.textContent = "↑";

        sendBtn.title = "Send";
    }
}


/* =========================================================
   REGENERATE
========================================================= */

async function regenerate(messageId) {

    const chat =
        getCurrentChat();

    if (!chat || state.generating) {
        return;
    }

    const index =
        chat.messages.findIndex(
            message =>
                message.id === messageId
        );

    if (index === -1) return;


    let userIndex = -1;

    for (
        let i = index - 1;
        i >= 0;
        i--
    ) {

        if (
            chat.messages[i].role ===
            "user"
        ) {

            userIndex = i;
            break;
        }
    }

    if (userIndex === -1) return;


    chat.messages =
        chat.messages.slice(
            0,
            userIndex + 1
        );

    saveChats();

    renderCurrentChat();

    showThinking();

    setGenerating(true);


    try {

        state.controller =
            new AbortController();

        const response =
            await fetch(CHAT_URL, {

                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({

                    messages:
                        chat.messages.map(message => ({
                            role: message.role,
                            content: message.content
                        })),

                    model:
                        state.model,

                    live_search:
                        state.liveSearch
                }),

                signal:
                    state.controller.signal
            });


        const data =
            await response.json()
                .catch(() => ({}));


        if (!response.ok) {

            throw new Error(
                data.detail ||
                data.error ||
                `Server error ${response.status}`
            );
        }


        const answer =
            data.answer ||
            data.response ||
            data.message ||
            data.content ||
            "No answer returned.";


        removeThinking();


        addMessage(
            "assistant",
            String(answer),
            {
                model:
                    data.model ||
                    state.model,

                live_evidence:
                    data.live_evidence ||
                    data.sources ||
                    []
            }
        );


        renderCurrentChat();

    } catch (error) {

        removeThinking();

        if (
            error.name !==
            "AbortError"
        ) {

            addMessage(
                "assistant",
                "Regeneration failed: " +
                error.message
            );

            renderCurrentChat();
        }

    } finally {

        state.controller = null;

        setGenerating(false);
    }
}


/* =========================================================
   UI
========================================================= */

function showChat() {

    chatView.classList.remove("hidden");
    appsView.classList.add("hidden");

    $$(".nav-item").forEach(item => {

        item.classList.toggle(
            "active",
            item.dataset.view === "chat"
        );

    });
}


function showApps() {

    chatView.classList.add("hidden");
    appsView.classList.remove("hidden");

    $$(".nav-item").forEach(item => {

        item.classList.toggle(
            "active",
            item.dataset.view === "apps"
        );

    });
}


function openSidebar() {

    sidebar.classList.add("open");
    sidebarOverlay.classList.add("open");
}


function closeSidebar() {

    sidebar.classList.remove("open");
    sidebarOverlay.classList.remove("open");
}


function closeSettings() {

    $("#settingsModal")
        .classList.add("hidden");
}


/* =========================================================
   TEXTAREA
========================================================= */

function autoResizeTextarea() {

    messageInput.style.height = "auto";

    messageInput.style.height =
        Math.min(
            messageInput.scrollHeight,
            180
        ) + "px";

    const count =
        messageInput.value.length;

    $("#characterCount").textContent =
        count.toLocaleString();
}


/* =========================================================
   SCROLL
========================================================= */

function scrollToBottom() {

    requestAnimationFrame(() => {

        messages.scrollTop =
            messages.scrollHeight;
    });
}


/* =========================================================
   COPY
========================================================= */

async function copyText(text) {

    try {

        await navigator.clipboard.writeText(
            text || ""
        );

        showToast("Copied");

    } catch {

        showToast("Copy failed");
    }
}


/* =========================================================
   VOICE
========================================================= */

function startVoiceInput() {

    const SpeechRecognition =
        window.SpeechRecognition ||
        window.webkitSpeechRecognition;

    if (!SpeechRecognition) {

        showToast(
            "Voice input is not supported in this browser"
        );

        return;
    }

    const recognition =
        new SpeechRecognition();

    recognition.lang =
        navigator.language || "en-IN";

    recognition.interimResults = false;

    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
        showToast("Listening...");
    };

    recognition.onresult = event => {

        const text =
            event.results[0][0].transcript;

        messageInput.value =
            messageInput.value
                ? messageInput.value + " " + text
                : text;

        autoResizeTextarea();
    };

    recognition.onerror = () => {
        showToast("Voice input failed");
    };

    recognition.start();
}


/* =========================================================
   SEARCH CHATS
========================================================= */

function searchChats() {

    const query =
        prompt("Search chats:");

    if (!query) return;

    const q =
        query.toLowerCase();

    const matches =
        state.chats.filter(chat => {

            if (
                chat.title
                    .toLowerCase()
                    .includes(q)
            ) {
                return true;
            }

            return chat.messages.some(
                message =>
                    message.content
                        .toLowerCase()
                        .includes(q)
            );
        });

    chatHistory.innerHTML = "";

    matches.forEach(chat => {

        const button =
            document.createElement("button");

        button.className =
            "history-item";

        button.textContent =
            chat.title;

        button.addEventListener(
            "click",
            () => {

                state.currentChatId =
                    chat.id;

                saveChats();

                renderHistory();
                renderCurrentChat();
                showChat();

                closeSidebar();
            }
        );

        chatHistory.appendChild(button);
    });

    if (!matches.length) {

        const empty =
            document.createElement("div");

        empty.style.cssText =
            "padding:10px;color:#697183;font-size:11px";

        empty.textContent =
            "No chats found.";

        chatHistory.appendChild(empty);
    }
}


/* =========================================================
   CLEAR CHATS
========================================================= */

function clearAllChats() {

    const ok =
        confirm(
            "Delete all chats stored on this device?"
        );

    if (!ok) return;

    state.chats = [];

    state.currentChatId = null;

    localStorage.removeItem(
        STORAGE_CHATS
    );

    localStorage.removeItem(
        STORAGE_CURRENT
    );

    createNewChat(true);

    closeSettings();

    showToast("Chat history cleared");
}


/* =========================================================
   USER
========================================================= */

function getUserInitial() {

    if (!state.user?.name) {
        return "U";
    }

    return state.user.name
        .trim()
        .charAt(0)
        .toUpperCase() || "U";
}


/* =========================================================
   TOAST
========================================================= */

let toastTimer = null;

function showToast(text) {

    toast.textContent = text;

    toast.classList.add("show");

    clearTimeout(toastTimer);

    toastTimer =
        setTimeout(() => {

            toast.classList.remove("show");

        }, 2500);
}


/* =========================================================
   MOBILE / APP VISIBILITY
========================================================= */

window.addEventListener(
    "resize",
    () => {

        if (
            window.innerWidth > 760
        ) {
            closeSidebar();
        }

    }
);


/* =========================================================
   GLOBAL ERROR SAFETY
========================================================= */

window.addEventListener(
    "unhandledrejection",
    event => {

        console.error(
            "BISNU-X:",
            event.reason
        );

    }
);