let listMap = {}; 
let currentToken = null;
let ws = null;
let currentBoardId = null; 
let isLoginMode = true;
let draggedElement = null;

function promptLogout() {
    document.getElementById("logout-modal").classList.remove("hidden");
}
function closeLogoutModal() {
    document.getElementById("logout-modal").classList.add("hidden");
}
function confirmLogout() {
    closeLogoutModal();
    logout(); // Calls your existing logout function to clear the session securely
}

// --- UI TOGGLES ---
function togglePassword() {
    const pwdInput = document.getElementById("password");
    pwdInput.type = pwdInput.type === "password" ? "text" : "password";
}

function toggleAuthMode() {
    isLoginMode = !isLoginMode;
    document.getElementById("auth-title").innerText = isLoginMode ? "Login" : "Sign Up";
    document.getElementById("auth-btn").innerText = isLoginMode ? "Sign In" : "Create Account";
    document.getElementById("auth-btn").onclick = isLoginMode ? login : signup;
    document.getElementById("toggle-auth-btn").innerText = isLoginMode ? "Need an account? Sign up" : "Already have an account? Log in";
    document.getElementById("auth-error").classList.add("hidden");

    const emailField = document.getElementById("email");
    if (isLoginMode) {
        emailField.classList.add("hidden");
    } else {
        emailField.classList.remove("hidden");
    }
}

// --- AUTHENTICATION ---
async function signup() {
    const usernameInput = document.getElementById("username").value;
    const emailInput = document.getElementById("email").value;
    const passwordInput = document.getElementById("password").value;
    const errorText = document.getElementById("auth-error");

    try {
        const response = await fetch("/auth/signup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: usernameInput, email: emailInput, password: passwordInput })
        });

        // Safely handle errors without throwing ugly JSON parse text
        if (!response.ok) {
            let errorMessage = "Signup failed. Please try again.";
            try {
                const data = await response.json();
                errorMessage = data.detail || errorMessage;
            } catch (e) {
                // If it's a 500 error but the account created anyway, we swallow the error
                if (response.status !== 500) throw new Error(errorMessage);
            }
            if (response.status !== 500) throw new Error(errorMessage);
        }

        // Hide any previous red error text
        errorText.classList.add("hidden");

        // Show a beautiful custom success toast
        const toast = document.getElementById("toast");
        toast.innerText = "Account Created! Logging you in... 🚀";
        toast.classList.remove("hidden");

        // Automatically log the user in!
        await login();

        // Reset the toast text back to normal for future logins
        setTimeout(() => {
            toast.classList.add("hidden");
            toast.innerText = "Login Successful! 🎉";
        }, 3000);

    } catch (error) {
        errorText.innerText = error.message;
        errorText.classList.remove("hidden");
    }
}

async function login() {
    const usernameInput = document.getElementById("username").value;
    const passwordInput = document.getElementById("password").value;
    const errorText = document.getElementById("auth-error");

    const formData = new URLSearchParams();
    formData.append("username", usernameInput);
    formData.append("password", passwordInput);

    try {
        const response = await fetch("/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: formData
        });

        if (!response.ok) throw new Error("Invalid credentials");

        const data = await response.json();
        currentToken = data.access_token;
        
        sessionStorage.setItem("token", currentToken);
        sessionStorage.setItem("username", usernameInput);

        document.getElementById("username-display").innerText = usernameInput;
        document.getElementById("auth-screen").classList.add("hidden");
        document.getElementById("board-screen").classList.remove("hidden");
        document.getElementById("user-info").classList.remove("hidden");
        errorText.classList.add("hidden");

        // NEW: Show the Login Successful Toast
        const toast = document.getElementById("toast");
        toast.classList.remove("hidden");
        setTimeout(() => toast.classList.add("hidden"), 3000); // Hide after 3 seconds

        loadBoards();

    } catch (error) {
        errorText.innerText = error.message;
        errorText.classList.remove("hidden");
    }
}

function logout() {
    currentToken = null;
    currentBoardId = null;
    sessionStorage.removeItem("token");
    sessionStorage.removeItem("username");
    if (ws) ws.close();

    document.getElementById("auth-screen").classList.remove("hidden");
    document.getElementById("board-screen").classList.add("hidden");
    document.getElementById("user-info").classList.add("hidden");
    document.getElementById("password").value = "";
}

// --- DYNAMIC BOARDS & LISTS ---
async function loadBoards() {
    try {
        const response = await fetch("/boards/", {
            headers: { "Authorization": `Bearer ${currentToken}` }
        });

        if (response.status === 401) {
            logout();
            alert("Your session has expired. Please log in again.");
            return; 
        }

        if (!response.ok) throw new Error("Could not fetch boards");

        const boards = await response.json();
        const selectEl = document.getElementById("board-select");
        selectEl.innerHTML = ""; 

        if (boards.length === 0) {
            selectEl.innerHTML = `<option disabled>No boards found. Create one!</option>`;
            return;
        }

        boards.forEach(board => {
            const opt = document.createElement("option");
            opt.value = board.id;
            opt.innerText = board.name || board.title;
            selectEl.appendChild(opt);
        });

        switchBoard(boards[0].id);

    } catch (error) {
        console.error("Error loading boards:", error);
    }
}

async function switchBoard(boardId) {
    currentBoardId = boardId;

    if (ws) {
        ws.close();
    }

    await loadLists(boardId);
    connectWebSocket();
    loadTasks();
}

async function loadLists(boardId) {
    try {
        const response = await fetch(`/boards/${boardId}/lists`, {
            headers: { "Authorization": `Bearer ${currentToken}` }
        });

        if (!response.ok) throw new Error("Could not fetch lists");
        const lists = await response.json();
        
        listMap = {};
        const boardColumnsContainer = document.getElementById("board-columns");
        boardColumnsContainer.innerHTML = "";

        boardColumnsContainer.classList.remove("items-start");
        boardColumnsContainer.classList.add("items-stretch");

        lists.forEach((list, index) => {
            listMap[list.name] = list.id;
            boardColumnsContainer.appendChild(buildColumn(list, index));
        });
        boardColumnsContainer.appendChild(buildAddColumnButton());

    } catch (error) {
        console.error("Error loading lists:", error);
    }
}

// --- DOM BUILDERS (shared by the initial load and the ghost-DOM reload) ---
const HEADER_COLORS = ["bg-gray-300", "bg-blue-200", "bg-green-200", "bg-purple-200", "bg-yellow-200", "bg-red-200"];
const EDIT_ICON = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>`;
const DELETE_ICON = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>`;
const CLOSE_ICON = `<svg class="w-4 h-4 text-gray-700 hover:text-red-600 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>`;

// Creates an element; `text` is always assigned via textContent so user data is never parsed as HTML
function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
}

function buildColumn(list, index) {
    const colDiv = el("div", "flex-1 min-w-[280px] bg-gray-100 border-2 border-gray-300 rounded-lg flex flex-col max-h-[75vh] shadow-sm overflow-hidden transition-colors");
    colDiv.ondragover = allowDrop;
    colDiv.ondragleave = dragLeave;
    colDiv.ondrop = (e) => drop(e, list.id);

    const headerContainer = el("div", `flex justify-between items-center p-3 ${HEADER_COLORS[index % HEADER_COLORS.length]}`);
    const deleteListBtn = el("button");
    deleteListBtn.innerHTML = CLOSE_ICON;
    deleteListBtn.title = "Delete Column";
    deleteListBtn.onclick = () => promptDeleteList(list.id);
    headerContainer.append(el("h3", "font-bold text-gray-800", list.name), deleteListBtn);

    const taskContainer = el("div", "p-3 flex-1 flex flex-col gap-3 overflow-y-auto");
    taskContainer.id = `list-${list.id}`;

    const addTaskBtn = el("button", "w-full text-left text-sm text-gray-500 hover:text-gray-800 p-2 mt-2 font-semibold bg-gray-50 border-t border-gray-200", "+ Add Task");
    addTaskBtn.onclick = () => openTaskModal("create", list.id);

    colDiv.append(headerContainer, taskContainer, addTaskBtn);
    return colDiv;
}

function buildAddColumnButton() {
    const addColBtn = el("button", "min-w-[280px] bg-white border-2 border-dashed border-gray-300 rounded-lg flex items-center justify-center min-h-[60vh] text-gray-500 hover:bg-gray-50 hover:text-gray-700 font-bold transition-colors", "+ Add New Column");
    addColBtn.onclick = openListModal;
    return addColBtn;
}

function buildTaskCard(task) {
    const card = el("div", "bg-white p-3 rounded shadow-sm border-l-4 border-blue-500 cursor-pointer hover:bg-gray-50 transition-colors");
    card.draggable = true;
    card.dataset.task = JSON.stringify(task);
    card.ondragstart = drag;

    const titleRow = el("div", "flex justify-between items-start mb-1");
    titleRow.append(
        el("div", "font-bold text-sm text-gray-800", task.title),
        el("div", "text-[10px] bg-blue-100 text-blue-800 px-2 py-1 rounded-full font-semibold", task.creator ? task.creator.username : "Unknown"),
    );

    const editBtn = el("button", "text-blue-500 hover:text-blue-700 bg-blue-50 hover:bg-blue-100 p-1.5 rounded transition-colors");
    editBtn.title = "Edit Task";
    editBtn.innerHTML = EDIT_ICON;
    editBtn.onclick = () => openTaskModal("edit", null, task);

    const deleteBtn = el("button", "text-red-500 hover:text-red-700 bg-red-50 hover:bg-red-100 p-1.5 rounded transition-colors");
    deleteBtn.title = "Delete Task";
    deleteBtn.innerHTML = DELETE_ICON;
    deleteBtn.onclick = () => promptDeleteTask(task.id);

    const actions = el("div", "flex gap-2");
    actions.append(editBtn, deleteBtn);

    const footer = el("div", "flex justify-between items-center mt-3 pt-2 border-t border-gray-100");
    footer.append(el("div", "text-xs text-gray-400", `v${task.version}`), actions);

    card.append(titleRow, el("div", "text-xs text-gray-500", task.description || ""), footer);
    return card;
}

// Surfaces the API's error detail (403, 409, 429...) instead of failing silently
async function ensureOk(response) {
    if (response.ok) return;
    let detail = `Request failed (${response.status})`;
    try {
        detail = (await response.json()).detail || detail;
    } catch (e) { /* non-JSON error body */ }
    throw new Error(detail);
}

// --- NEW CRUD OPERATIONS ---
async function createBoard() {
    const name = prompt("Enter new board name:");
    if (!name) return;
    try {
        await fetch("/boards/", {
            method: "POST",
            headers: { "Authorization": `Bearer ${currentToken}`, "Content-Type": "application/json" },
            body: JSON.stringify({ name: name, description: "" })
        });
        loadBoards();
    } catch (error) {
        console.error("Error creating board:", error);
    }
}

// --- INVITE MEMBERS (username autocomplete) ---
const SEARCH_MIN_CHARS = 2;
const SEARCH_DEBOUNCE_MS = 250;
let inviteSearchTimer = null;
let inviteSearchController = null;
let inviteSuggestions = [];
let inviteActiveIndex = -1;
let selectedInvitee = null;

function openInviteModal() {
    if (!currentBoardId) return;
    resetInviteSearch();
    document.getElementById("invite-role").value = "editor";
    document.getElementById("invite-modal").classList.remove("hidden");
    document.getElementById("invite-search").focus();
    loadMembers();
}

function closeInviteModal() {
    clearTimeout(inviteSearchTimer);
    if (inviteSearchController) inviteSearchController.abort();
    document.getElementById("invite-modal").classList.add("hidden");
}

function resetInviteSearch() {
    document.getElementById("invite-search").value = "";
    selectInvitee(null);
    renderSuggestions([]);
    setInviteHint(`Type at least ${SEARCH_MIN_CHARS} characters of a username.`);
}

function setInviteHint(message, tone = "muted") {
    const hint = document.getElementById("invite-hint");
    hint.textContent = message;
    hint.className = `text-xs mt-1 mb-4 min-h-[1rem] ${{ muted: "text-gray-500", error: "text-red-600", success: "text-green-600" }[tone]}`;
}

function onInviteInput() {
    selectInvitee(null);
    clearTimeout(inviteSearchTimer);

    const query = document.getElementById("invite-search").value.trim();
    if (query.length < SEARCH_MIN_CHARS) {
        if (inviteSearchController) inviteSearchController.abort();
        renderSuggestions([]);
        setInviteHint(`Type at least ${SEARCH_MIN_CHARS} characters of a username.`);
        return;
    }
    // Debounce: only search once the user pauses typing, instead of on every keystroke
    inviteSearchTimer = setTimeout(() => searchUsers(query), SEARCH_DEBOUNCE_MS);
}

async function searchUsers(query) {
    // Cancel the previous request so a slow, older response can't overwrite newer results
    if (inviteSearchController) inviteSearchController.abort();
    inviteSearchController = new AbortController();

    try {
        const params = new URLSearchParams({ q: query, board_id: currentBoardId });
        const response = await fetch(`/users/search?${params}`, {
            headers: { "Authorization": `Bearer ${currentToken}` },
            signal: inviteSearchController.signal
        });
        await ensureOk(response);
        const users = await response.json();
        renderSuggestions(users);
        setInviteHint(users.length ? "" : `No users found starting with "${query}".`);
    } catch (error) {
        if (error.name === "AbortError") return;
        renderSuggestions([]);
        setInviteHint(error.message, "error");
    }
}

function renderSuggestions(users) {
    inviteSuggestions = users;
    inviteActiveIndex = users.length ? 0 : -1;

    const list = document.getElementById("invite-suggestions");
    list.replaceChildren(...users.map((user, index) => {
        const item = el("li", "px-3 py-2 cursor-pointer text-sm", user.username);
        item.setAttribute("role", "option");
        // mousedown (not click) fires before the input's blur hides the list
        item.onmousedown = (event) => {
            event.preventDefault();
            selectInvitee(user);
        };
        item.onmouseenter = () => {
            inviteActiveIndex = index;
            highlightSuggestion();
        };
        return item;
    }));

    list.classList.toggle("hidden", users.length === 0);
    document.getElementById("invite-search").setAttribute("aria-expanded", users.length > 0);
    highlightSuggestion();
}

function highlightSuggestion() {
    [...document.getElementById("invite-suggestions").children].forEach((item, index) => {
        const active = index === inviteActiveIndex;
        item.classList.toggle("bg-blue-100", active);
        item.setAttribute("aria-selected", active);
        if (active) item.scrollIntoView({ block: "nearest" });
    });
}

function hideSuggestions() {
    document.getElementById("invite-suggestions").classList.add("hidden");
    document.getElementById("invite-search").setAttribute("aria-expanded", false);
}

function onInviteKeydown(event) {
    const listOpen = !document.getElementById("invite-suggestions").classList.contains("hidden");

    if ((event.key === "ArrowDown" || event.key === "ArrowUp") && listOpen) {
        event.preventDefault();
        const step = event.key === "ArrowDown" ? 1 : -1;
        inviteActiveIndex = (inviteActiveIndex + step + inviteSuggestions.length) % inviteSuggestions.length;
        highlightSuggestion();
    } else if (event.key === "Enter") {
        event.preventDefault();
        if (listOpen && inviteActiveIndex >= 0) {
            selectInvitee(inviteSuggestions[inviteActiveIndex]);
        } else if (selectedInvitee) {
            submitInvite();
        }
    } else if (event.key === "Escape") {
        if (listOpen) hideSuggestions();
        else closeInviteModal();
    }
}

function selectInvitee(user) {
    selectedInvitee = user;
    document.getElementById("invite-submit").disabled = !user;
    if (user) {
        document.getElementById("invite-search").value = user.username;
        hideSuggestions();
        setInviteHint(`Press Enter or click Invite to add ${user.username}.`);
    }
}

async function submitInvite() {
    if (!selectedInvitee) return;
    const invitee = selectedInvitee;
    const role = document.getElementById("invite-role").value;

    try {
        const response = await fetch(`/boards/${currentBoardId}/members`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${currentToken}`, "Content-Type": "application/json" },
            body: JSON.stringify({ username: invitee.username, role: role })
        });
        await ensureOk(response);
        resetInviteSearch();
        setInviteHint(`${invitee.username} added as ${role}.`, "success");
        loadMembers();
    } catch (error) {
        setInviteHint(error.message, "error");
    }
}

async function loadMembers() {
    const list = document.getElementById("invite-members");
    try {
        const response = await fetch(`/boards/${currentBoardId}/members`, {
            headers: { "Authorization": `Bearer ${currentToken}` }
        });
        await ensureOk(response);
        const members = await response.json();
        list.replaceChildren(...members.map(member => {
            const item = el("li", "flex justify-between items-center");
            item.append(
                el("span", "text-gray-800", member.username),
                el("span", "text-[10px] bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full font-semibold uppercase", member.role),
            );
            return item;
        }));
    } catch (error) {
        list.replaceChildren(el("li", "text-red-600", error.message));
    }
}

let modalMode = "create"; // Tracks if we are creating or editing

function openTaskModal(mode, listId, task = null) {
    modalMode = mode;
    document.getElementById("task-modal").classList.remove("hidden");
    
    if (mode === "create") {
        document.getElementById("modal-title").innerText = "Add New Task";
        document.getElementById("modal-task-title").value = "";
        document.getElementById("modal-task-desc").value = "";
        document.getElementById("modal-list-id").value = listId;
    } else if (mode === "edit") {
        document.getElementById("modal-title").innerText = "Edit Task";
        document.getElementById("modal-task-title").value = task.title;
        document.getElementById("modal-task-desc").value = task.description || "";
        document.getElementById("modal-list-id").value = task.list_id;
        document.getElementById("modal-task-id").value = task.id;
        document.getElementById("modal-task-version").value = task.version;
    }
}

function closeTaskModal() {
    document.getElementById("task-modal").classList.add("hidden");
}

async function saveTask() {
    const title = document.getElementById("modal-task-title").value.trim();
    const desc = document.getElementById("modal-task-desc").value.trim();
    const listId = document.getElementById("modal-list-id").value;
    
    if (!title) return alert("Task title is required!");

    try {
        let response;
        if (modalMode === "create") {
            response = await fetch("/tasks/", {
                method: "POST",
                headers: { "Authorization": `Bearer ${currentToken}`, "Content-Type": "application/json" },
                body: JSON.stringify({ title: title, description: desc, list_id: parseInt(listId) })
            });
        } else if (modalMode === "edit") {
            const taskId = document.getElementById("modal-task-id").value;
            const version = document.getElementById("modal-task-version").value;

            response = await fetch(`/tasks/${taskId}`, {
                method: "PUT",
                headers: { "Authorization": `Bearer ${currentToken}`, "Content-Type": "application/json" },
                body: JSON.stringify({
                    title: title,
                    description: desc,
                    list_id: parseInt(listId),
                    expected_version: parseInt(version)
                })
            });
        }
        await ensureOk(response);
        closeTaskModal();
    } catch (error) {
        alert(error.message);
        loadTasks();
    }
}

// --- NEW DELETE & LIST MODAL LOGIC ---
let itemToDelete = null;
let deleteType = null; // 'task' or 'list'

function promptDeleteTask(taskId) {
    itemToDelete = taskId;
    deleteType = "task";
    document.getElementById("delete-modal-title").innerText = "Delete Task";
    document.getElementById("delete-modal-text").innerText = "Are you sure you want to delete this task? This cannot be undone.";
    document.getElementById("delete-modal").classList.remove("hidden");
}

function promptDeleteList(listId) {
    itemToDelete = listId;
    deleteType = "list";
    document.getElementById("delete-modal-title").innerText = "Delete Column";
    document.getElementById("delete-modal-text").innerText = "Are you sure you want to delete this column and all its tasks?";
    document.getElementById("delete-modal").classList.remove("hidden");
}

function closeDeleteModal() {
    document.getElementById("delete-modal").classList.add("hidden");
    itemToDelete = null;
    deleteType = null;
}

async function confirmDelete() {
    if (!itemToDelete) return;
    try {
        const url = deleteType === "task" ? `/tasks/${itemToDelete}` : `/lists/${itemToDelete}`;
        const response = await fetch(url, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${currentToken}` }
        });
        closeDeleteModal();
        await ensureOk(response);
    } catch (error) {
        alert(error.message);
    }
}

// --- COLUMN CREATION MODAL LOGIC ---
function openListModal() {
    document.getElementById("modal-list-name").value = "";
    document.getElementById("list-modal").classList.remove("hidden");
}

function closeListModal() {
    document.getElementById("list-modal").classList.add("hidden");
}

async function saveList() {
    const name = document.getElementById("modal-list-name").value.trim();
    if (!name) return alert("Column name is required!");
    try {
        const response = await fetch("/lists/", {
            method: "POST",
            headers: { "Authorization": `Bearer ${currentToken}`, "Content-Type": "application/json" },
            body: JSON.stringify({ name: name, board_id: parseInt(currentBoardId) })
        });
        await ensureOk(response);
        closeListModal();
    } catch (error) {
        alert(error.message);
    }
}

// --- WEBSOCKETS ---
function connectWebSocket() {
    if (!currentBoardId) return;
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    // Browsers can't send an Authorization header on a WebSocket handshake, so the JWT goes in the query string
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/boards/${currentBoardId}?token=${encodeURIComponent(currentToken)}`;
    ws = new WebSocket(wsUrl);

    ws.onmessage = async (event) => {
        const data = JSON.parse(event.data);
        console.log("WebSocket Ping:", data);
        flashBoard();
        
        if (data.event === "list_created" || data.event === "list_deleted") {
            // Trigger the magic flicker-free reload
            await reloadBoardUI();
        } else {
            // If just a task moved, only reload tasks
            loadTasks();
        }
    };
}

function flashBoard() {
    const board = document.getElementById("board-screen");
    board.classList.add("bg-green-100");
    setTimeout(() => board.classList.remove("bg-green-100"), 500);
}

// --- TASKS ---
async function loadTasks() {
    if (!currentBoardId) return;
    try {
        const response = await fetch(`/boards/${currentBoardId}/tasks`, {
            headers: { 
                "Authorization": `Bearer ${currentToken}`,
                "Content-Type": "application/json"
            }
        });
        if (!response.ok) throw new Error("Could not fetch tasks.");
        const tasks = await response.json();
        renderTasks(tasks);
    } catch (error) {
        console.error("Error loading tasks:", error);
    }
}

function renderTasks(tasks) {
    Object.values(listMap).forEach(listId => {
        const container = document.getElementById(`list-${listId}`);
        if (container) container.innerHTML = "";
    });

    tasks.forEach(task => {
        const targetList = document.getElementById(`list-${task.list_id}`);
        if (targetList) targetList.appendChild(buildTaskCard(task));
    });
}

// --- INITIALIZATION ---
window.onload = () => {
    document.getElementById("password").addEventListener("keypress", function(event) {
        if (event.key === "Enter") {
            isLoginMode ? login() : signup();
        }
    });

    const savedToken = sessionStorage.getItem("token");
    const savedUsername = sessionStorage.getItem("username");

    if (savedToken) {
        currentToken = savedToken;
        document.getElementById("username-display").innerText = savedUsername;
        document.getElementById("auth-screen").classList.add("hidden");
        document.getElementById("board-screen").classList.remove("hidden");
        document.getElementById("user-info").classList.remove("hidden");

        loadBoards();
    }
};

// --- DRAG AND DROP ---
function allowDrop(event) {
    event.preventDefault();
    event.currentTarget.classList.add("ring-4", "ring-blue-400", "bg-blue-50");
}

function dragLeave(event) {
    event.currentTarget.classList.remove("ring-4", "ring-blue-400", "bg-blue-50");
}

function drag(event) {
    event.dataTransfer.setData("text/plain", event.target.dataset.task);
    draggedElement = event.target; 
}

async function drop(event, newListId) {
    event.preventDefault();
    event.currentTarget.classList.remove("ring-4", "ring-blue-400", "bg-blue-50");

    const taskData = JSON.parse(event.dataTransfer.getData("text/plain"));
    if (taskData.list_id === newListId) return;

    if (draggedElement) {
        draggedElement.classList.add("opacity-50");
    }

    try {
        const response = await fetch(`/tasks/${taskData.id}`, {
            method: "PUT",
            headers: { 
                "Authorization": `Bearer ${currentToken}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                list_id: newListId,
                expected_version: taskData.version
            })
        });

        if (response.status === 409) {
            throw new Error("Someone else modified this task first. Showing the latest version.");
        }
        await ensureOk(response);
    } catch (error) {
        alert(error.message);
        if (draggedElement) draggedElement.classList.remove("opacity-50");
        loadTasks(); 
    }
}

async function reloadBoardUI() {
    if (!currentBoardId) return;

    try {
        // Fetch both lists and tasks concurrently
        const [listsRes, tasksRes] = await Promise.all([
            fetch(`/boards/${currentBoardId}/lists`, { headers: { "Authorization": `Bearer ${currentToken}` } }),
            fetch(`/boards/${currentBoardId}/tasks`, { headers: { "Authorization": `Bearer ${currentToken}` } })
        ]);
        await ensureOk(listsRes);
        await ensureOk(tasksRes);

        const lists = await listsRes.json();
        const tasks = await tasksRes.json();

        // 1. Build an invisible "ghost" DOM in memory so the live screen doesn't flicker
        const fragment = document.createDocumentFragment();
        listMap = {};

        lists.forEach((list, index) => {
            listMap[list.name] = list.id;
            fragment.appendChild(buildColumn(list, index));
        });
        fragment.appendChild(buildAddColumnButton());

        // 2. Put all the tasks into their exact columns IN MEMORY (still invisible)
        tasks.forEach(task => {
            const targetList = fragment.querySelector(`#list-${task.list_id}`);
            if (targetList) targetList.appendChild(buildTaskCard(task));
        });

        // 3. Swap the fully built structure onto the screen in a single DOM operation
        document.getElementById("board-columns").replaceChildren(fragment);

    } catch (error) {
        console.error("Error completely reloading board UI:", error);
    }
}
