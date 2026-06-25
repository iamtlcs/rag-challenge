const loginView = document.querySelector("#loginView");
const chatView = document.querySelector("#chatView");
const loginForm = document.querySelector("#loginForm");
const loginError = document.querySelector("#loginError");
const chatForm = document.querySelector("#chatForm");
const messageInput = document.querySelector("#messageInput");
const messages = document.querySelector("#messages");
const sourceList = document.querySelector("#sourceList");
const healthText = document.querySelector("#healthText");
const logoutButton = document.querySelector("#logoutButton");

function showChat() {
  loginView.classList.add("hidden");
  chatView.classList.remove("hidden");
  messageInput.focus();
}

function showLogin() {
  chatView.classList.add("hidden");
  loginView.classList.remove("hidden");
}

function addMessage(role, text) {
  const node = document.createElement("div");
  node.className = `message ${role}`;
  node.textContent = text;
  messages.append(node);
  messages.scrollTop = messages.scrollHeight;
}

function renderSources(sources) {
  sourceList.innerHTML = "";
  for (const source of sources || []) {
    const card = document.createElement("article");
    card.className = "source-card";
    card.innerHTML = `
      <a href="${source.url}" target="_blank" rel="noreferrer">${source.title || "Source"}</a>
      <p>${source.date || "Unknown date"} · ${source.column || "THSS"} · score ${Number(source.score || 0).toFixed(3)}</p>
    `;
    sourceList.append(card);
  }
}

async function refreshHealth() {
  const response = await fetch("/api/health");
  const data = await response.json();
  healthText.textContent = data.index_ready
    ? `${data.chunk_count} indexed chunks`
    : "Index not ready";
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.textContent = "";
  const submit = loginForm.querySelector("button");
  submit.disabled = true;

  const body = {
    username: loginForm.username.value,
    password: loginForm.password.value,
  };

  try {
    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      loginError.textContent = "Invalid username or password.";
      return;
    }
    showChat();
    await refreshHealth();
  } finally {
    submit.disabled = false;
  }
});

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = messageInput.value.trim();
  if (!text) return;
  messageInput.value = "";
  addMessage("user", text);
  const submit = chatForm.querySelector("button");
  submit.disabled = true;

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    if (response.status === 401) {
      showLogin();
      return;
    }
    const data = await response.json();
    if (!response.ok) {
      addMessage("assistant", data.detail || "The service is not ready.");
      return;
    }
    addMessage("assistant", data.answer);
    renderSources(data.sources);
  } finally {
    submit.disabled = false;
    messageInput.focus();
  }
});

logoutButton.addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  showLogin();
});

refreshHealth().catch(() => {
  healthText.textContent = "Service unavailable";
});
