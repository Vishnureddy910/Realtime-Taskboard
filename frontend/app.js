let currentToken = null;
let ws = null;
const BOARD_ID = 1;
let isLoginMode = true;

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

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || "Signup failed");
        }
        
        // If signup succeeds, automatically log them in
        await login();
        
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
        localStorage.setItem("token", currentToken);
        localStorage.setItem("username", usernameInput);
        
        // Update UI
        document.getElementById("username-display").innerText = usernameInput;
        document.getElementById("auth-screen").classList.add("hidden");
        document.getElementById("board-screen").classList.remove("hidden");
        document.getElementById("user-info").classList.remove("hidden");
        errorText.classList.add("hidden");

        connectWebSocket();
        
        // TRIGGER TASK LOAD ON LOGIN
        loadTasks();
        
    } catch (error) {
        errorText.innerText = error.message;
        errorText.classList.remove("hidden");
    }
}

function logout() {
    currentToken = null;
    localStorage.removeItem("token");
    localStorage.removeItem("username");
    if (ws) ws.close();
    
    document.getElementById("auth-screen").classList.remove("hidden");
    document.getElementById("board-screen").classList.add("hidden");
    document.getElementById("user-info").classList.add("hidden");
    document.getElementById("password").value = "";
}

// --- WEBSOCKETS ---
function connectWebSocket() {
    // Connect to the WebSocket endpoint for this board
    const wsUrl = `ws://${window.location.host}/ws/boards/${BOARD_ID}`;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log("WebSocket connected to Board", BOARD_ID);
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log("Real-time update received:", data);
        
        flashBoard();
        
        // TRIGGER TASK RE-LOAD ON WEBSOCKET EVENT
        loadTasks();
    };

    ws.onclose = () => {
        console.log("WebSocket disconnected.");
    };
}

// Visual indicator that an event arrived
function flashBoard() {
    const board = document.getElementById("board-screen");
    board.classList.add("bg-green-100");
    setTimeout(() => {
        board.classList.remove("bg-green-100");
    }, 500);
}

// --- BOARD & TASKS ---
async function loadTasks() {
    try {
        // Fetch tasks for this board. 
        const response = await fetch(`/boards/${BOARD_ID}/tasks`, {
            headers: { 
                "Authorization": `Bearer ${currentToken}`,
                "Content-Type": "application/json"
            }
        });
        
        if (!response.ok) throw new Error("Could not fetch tasks. (Does Board 1 exist?)");
        
        const tasks = await response.json();
        renderTasks(tasks);
    } catch (error) {
        console.error("Error loading tasks:", error);
    }
}

function renderTasks(tasks) {
    document.getElementById("list-todo").innerHTML = "";
    document.getElementById("list-inprogress").innerHTML = "";
    document.getElementById("list-done").innerHTML = "";

    tasks.forEach(task => {
        const card = document.createElement("div");
        card.className = "bg-white p-3 rounded shadow-sm border-l-4 border-blue-500 cursor-pointer hover:bg-gray-50 transition-colors";
        
        // 1. Make the card draggable
        card.draggable = true;
        
        // 2. Store the task data inside the card so we can read it when dropped
        card.dataset.task = JSON.stringify(task);
        
        // 3. Attach the drag start event
        card.ondragstart = drag;
        
        const version = task.version || task.expected_version || 1;
        
        card.innerHTML = `
            <div class="font-bold text-sm text-gray-800">${task.title}</div>
            <div class="text-xs text-gray-500 mt-1">${task.description || ""}</div>
            <div class="text-xs text-gray-400 mt-2 text-right">v${version}</div>
        `;

        if (task.list_id === 1) document.getElementById("list-todo").appendChild(card);
        else if (task.list_id === 2) document.getElementById("list-inprogress").appendChild(card);
        else if (task.list_id === 3) document.getElementById("list-done").appendChild(card);
    });
}

// Automatically log in on refresh if a token exists
window.onload = () => {
    const savedToken = localStorage.getItem("token");
    const savedUsername = localStorage.getItem("username");
    
    if (savedToken) {
        currentToken = savedToken;
        document.getElementById("username-display").innerText = savedUsername;
        document.getElementById("auth-screen").classList.add("hidden");
        document.getElementById("board-screen").classList.remove("hidden");
        document.getElementById("user-info").classList.remove("hidden");
        
        connectWebSocket();
        loadTasks();
    }
};

// --- DRAG AND DROP ---
function allowDrop(event) {
    event.preventDefault(); // Required to allow dropping
}

function drag(event) {
    // Pass the task JSON text to the drop zone
    event.dataTransfer.setData("text/plain", event.target.dataset.task);
}

async function drop(event, newListId) {
    event.preventDefault();
    
    // Read the task data we embedded in the card
    const taskData = JSON.parse(event.dataTransfer.getData("text/plain"));

    // If dropped in the same column, do nothing
    if (taskData.list_id === newListId) return;

    try {
        // Fire the PUT request to move the task
        const response = await fetch(`/tasks/${taskData.id}`, {
            method: "PUT",
            headers: { 
                "Authorization": `Bearer ${currentToken}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                title: taskData.title,
                description: taskData.description,
                list_id: newListId,
                expected_version: taskData.version || 1 // Phase 6 Conflict Checking!
            })
        });

        if (!response.ok) {
            throw new Error("Failed to move task. Someone else may have updated it.");
        }

        // Fetch fresh tasks to show the new position and version
        loadTasks();
        
    } catch (error) {
        console.error(error);
        alert(error.message);
        loadTasks(); // Reload to get the actual current state
    }
}