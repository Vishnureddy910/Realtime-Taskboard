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

        const headerColors = ["bg-gray-300", "bg-blue-200", "bg-green-200", "bg-purple-200", "bg-yellow-200", "bg-red-200"];

        lists.forEach((list, index) => {
            listMap[list.name] = list.id;

            const colDiv = document.createElement("div");
            colDiv.className = "flex-1 min-w-[280px] bg-gray-100 border-2 border-gray-300 rounded-lg flex flex-col max-h-[75vh] shadow-sm overflow-hidden transition-colors";

            colDiv.ondragover = allowDrop;
            colDiv.ondragleave = dragLeave;
            colDiv.ondrop = (e) => drop(e, list.id);

            const colorClass = headerColors[index % headerColors.length];
            
            // NEW: Header container with Delete Column (X) icon
            const headerContainer = document.createElement("div");
            headerContainer.className = `flex justify-between items-center p-3 ${colorClass}`;
            
            const header = document.createElement("h3");
            header.className = `font-bold text-gray-800`;
            header.innerText = list.name;
            
            const deleteListBtn = document.createElement("button");
            deleteListBtn.innerHTML = `<svg class="w-4 h-4 text-gray-700 hover:text-red-600 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>`;
            deleteListBtn.onclick = () => promptDeleteList(list.id);
            deleteListBtn.title = "Delete Column";

            headerContainer.appendChild(header);
            headerContainer.appendChild(deleteListBtn);

            const taskContainer = document.createElement("div");
            taskContainer.id = `list-${list.id}`;
            taskContainer.className = "p-3 flex-1 flex flex-col gap-3 overflow-y-auto";
            
            const addTaskBtn = document.createElement("button");
            addTaskBtn.className = "w-full text-left text-sm text-gray-500 hover:text-gray-800 p-2 mt-2 font-semibold bg-gray-50 border-t border-gray-200";
            addTaskBtn.innerText = "+ Add Task";
            addTaskBtn.onclick = () => openTaskModal("create", list.id);

            colDiv.appendChild(headerContainer);
            colDiv.appendChild(taskContainer);
            colDiv.appendChild(addTaskBtn); 
            
            boardColumnsContainer.appendChild(colDiv);
        });

        // NEW: Add a "New Column" placeholder at the far right
        const addColBtn = document.createElement("button");
        addColBtn.className = "min-w-[280px] bg-white border-2 border-dashed border-gray-300 rounded-lg flex items-center justify-center min-h-[60vh] text-gray-500 hover:bg-gray-50 hover:text-gray-700 font-bold transition-colors";
        addColBtn.innerText = "+ Add New Column";
        addColBtn.onclick = openListModal;
        boardColumnsContainer.appendChild(addColBtn);

    } catch (error) {
        console.error("Error loading lists:", error);
    }
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

let modalMode = "create"; // Tracks if we are creating or editing

function openTaskModal(mode, listId, taskString = null) {
    modalMode = mode;
    document.getElementById("task-modal").classList.remove("hidden");
    
    if (mode === "create") {
        document.getElementById("modal-title").innerText = "Add New Task";
        document.getElementById("modal-task-title").value = "";
        document.getElementById("modal-task-desc").value = "";
        document.getElementById("modal-list-id").value = listId;
    } else if (mode === "edit") {
        const task = JSON.parse(taskString);
        document.getElementById("modal-title").innerText = "Edit Task";
        document.getElementById("modal-task-title").value = task.title || task.name || "";
        document.getElementById("modal-task-desc").value = task.description || "";
        document.getElementById("modal-list-id").value = task.list_id;
        document.getElementById("modal-task-id").value = task.id;
        document.getElementById("modal-task-version").value = task.version || task.expected_version || 1;
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
        if (modalMode === "create") {
            await fetch("/tasks/", {
                method: "POST",
                headers: { "Authorization": `Bearer ${currentToken}`, "Content-Type": "application/json" },
                body: JSON.stringify({ title: title, description: desc, list_id: parseInt(listId) })
            });
        } else if (modalMode === "edit") {
            const taskId = document.getElementById("modal-task-id").value;
            const version = document.getElementById("modal-task-version").value;
            
            await fetch(`/tasks/${taskId}`, {
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
        closeTaskModal();
    } catch (error) {
        console.error("Error saving task:", error);
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
        await fetch(url, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${currentToken}` }
        });
        closeDeleteModal();
    } catch (error) {
        console.error("Error deleting:", error);
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
        await fetch("/lists/", {
            method: "POST",
            headers: { "Authorization": `Bearer ${currentToken}`, "Content-Type": "application/json" },
            body: JSON.stringify({ name: name, board_id: currentBoardId })
        });
        closeListModal();
    } catch (error) {
        console.error("Error creating list:", error);
    }
}

// --- WEBSOCKETS ---
function connectWebSocket() {
    if (!currentBoardId) return;
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/boards/${currentBoardId}`;
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
        const card = document.createElement("div");
        card.className = "bg-white p-3 rounded shadow-sm border-l-4 border-blue-500 cursor-pointer hover:bg-gray-50 transition-colors";
        card.draggable = true;
        card.dataset.task = JSON.stringify(task);
        card.ondragstart = drag;

        const version = task.version || task.expected_version || 1;
        const creatorName = task.creator ? task.creator.username : "Unknown";
        const taskDataString = encodeURIComponent(JSON.stringify(task));

        // Professional SVG Icons
        const editIcon = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>`;
        const deleteIcon = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>`;

        card.innerHTML = `
            <div class="flex justify-between items-start mb-1">
                <div class="font-bold text-sm text-gray-800">${task.title || task.name}</div>
                <div class="text-[10px] bg-blue-100 text-blue-800 px-2 py-1 rounded-full font-semibold">${creatorName}</div>
            </div>
            <div class="text-xs text-gray-500">${task.description || ""}</div>
            
            <div class="flex justify-between items-center mt-3 pt-2 border-t border-gray-100">
                <div class="text-xs text-gray-400">v${version}</div>
                <div class="flex gap-2">
                    <button onclick='openTaskModal("edit", null, decodeURIComponent("${taskDataString}"))' class="text-blue-500 hover:text-blue-700 bg-blue-50 hover:bg-blue-100 p-1.5 rounded transition-colors" title="Edit Task">${editIcon}</button>
                    <button onclick="promptDeleteTask(${task.id})" class="text-red-500 hover:text-red-700 bg-red-50 hover:bg-red-100 p-1.5 rounded transition-colors" title="Delete Task">${deleteIcon}</button>
                </div>
            </div>
        `;

        const targetList = document.getElementById(`list-${task.list_id}`);
        if (targetList) {
            targetList.appendChild(card);
        }
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
                title: taskData.title,
                name: taskData.name,
                description: taskData.description,
                list_id: newListId,
                expected_version: taskData.version || 1 
            })
        });

        if (!response.ok) {
            if (response.status === 409) {
                throw new Error("Someone else modified this task! Refreshing...");
            }
            throw new Error("Failed to move task on server.");
        }
    } catch (error) {
        console.error(error);
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

        const lists = await listsRes.json();
        const tasks = await tasksRes.json();

        // 1. Build an invisible "ghost" DOM in memory so the live screen doesn't flicker
        const fragment = document.createDocumentFragment();
        listMap = {};

        const headerColors = ["bg-gray-300", "bg-blue-200", "bg-green-200", "bg-purple-200", "bg-yellow-200", "bg-red-200"];

        lists.forEach((list, index) => {
            listMap[list.name] = list.id;
            const colDiv = document.createElement("div");
            colDiv.className = "flex-1 min-w-[280px] bg-gray-100 border-2 border-gray-300 rounded-lg flex flex-col max-h-[75vh] shadow-sm overflow-hidden transition-colors";
            
            // Re-attach drag and drop events
            colDiv.ondragover = allowDrop;
            colDiv.ondragleave = dragLeave;
            colDiv.ondrop = (e) => drop(e, list.id);

            const colorClass = headerColors[index % headerColors.length];
            const headerContainer = document.createElement("div");
            headerContainer.className = `flex justify-between items-center p-3 ${colorClass}`;
            
            const header = document.createElement("h3");
            header.className = `font-bold text-gray-800`;
            header.innerText = list.name;
            
            const deleteListBtn = document.createElement("button");
            deleteListBtn.innerHTML = `<svg class="w-4 h-4 text-gray-700 hover:text-red-600 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>`;
            deleteListBtn.onclick = () => promptDeleteList(list.id);
            
            headerContainer.appendChild(header);
            headerContainer.appendChild(deleteListBtn);

            const taskContainer = document.createElement("div");
            taskContainer.id = `list-${list.id}`;
            taskContainer.className = "p-3 flex-1 flex flex-col gap-3 overflow-y-auto";
            
            const addTaskBtn = document.createElement("button");
            addTaskBtn.className = "w-full text-left text-sm text-gray-500 hover:text-gray-800 p-2 mt-2 font-semibold bg-gray-50 border-t border-gray-200";
            addTaskBtn.innerText = "+ Add Task";
            addTaskBtn.onclick = () => openTaskModal("create", list.id);

            colDiv.appendChild(headerContainer);
            colDiv.appendChild(taskContainer);
            colDiv.appendChild(addTaskBtn); 
            
            fragment.appendChild(colDiv); // Add finished column to our ghost DOM
        });

        // Add the "New Column" button to the ghost DOM
        const addColBtn = document.createElement("button");
        addColBtn.className = "min-w-[280px] bg-white border-2 border-dashed border-gray-300 rounded-lg flex items-center justify-center min-h-[60vh] text-gray-500 hover:bg-gray-50 hover:text-gray-700 font-bold transition-colors";
        addColBtn.innerText = "+ Add New Column";
        addColBtn.onclick = openListModal;
        fragment.appendChild(addColBtn);

        // 2. Put all the tasks into their exact columns IN MEMORY (still invisible)
        tasks.forEach(task => {
            const card = document.createElement("div");
            card.className = "bg-white p-3 rounded shadow-sm border-l-4 border-blue-500 cursor-pointer hover:bg-gray-50 transition-colors";
            card.draggable = true;
            card.dataset.task = JSON.stringify(task);
            card.ondragstart = drag;

            const version = task.version || task.expected_version || 1;
            const creatorName = task.creator ? task.creator.username : "Unknown";
            const taskDataString = encodeURIComponent(JSON.stringify(task));

            const editIcon = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>`;
            const deleteIcon = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>`;

            card.innerHTML = `
                <div class="flex justify-between items-start mb-1">
                    <div class="font-bold text-sm text-gray-800">${task.title || task.name}</div>
                    <div class="text-[10px] bg-blue-100 text-blue-800 px-2 py-1 rounded-full font-semibold">${creatorName}</div>
                </div>
                <div class="text-xs text-gray-500">${task.description || ""}</div>
                
                <div class="flex justify-between items-center mt-3 pt-2 border-t border-gray-100">
                    <div class="text-xs text-gray-400">v${version}</div>
                    <div class="flex gap-2">
                        <button onclick='openTaskModal("edit", null, decodeURIComponent("${taskDataString}"))' class="text-blue-500 hover:text-blue-700 bg-blue-50 hover:bg-blue-100 p-1.5 rounded transition-colors" title="Edit Task">${editIcon}</button>
                        <button onclick="promptDeleteTask(${task.id})" class="text-red-500 hover:text-red-700 bg-red-50 hover:bg-red-100 p-1.5 rounded transition-colors" title="Delete Task">${deleteIcon}</button>
                    </div>
                </div>
            `;

            const targetList = fragment.querySelector(`#list-${task.list_id}`);
            if (targetList) {
                targetList.appendChild(card);
            }
        });

        // 3. The magic move! Swap the fully built structure onto the screen instantly
        const boardColumnsContainer = document.getElementById("board-columns");
        boardColumnsContainer.innerHTML = ""; 
        boardColumnsContainer.appendChild(fragment);

    } catch (error) {
        console.error("Error completely reloading board UI:", error);
    }
}