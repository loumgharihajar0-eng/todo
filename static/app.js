const todoForm = document.getElementById('todoForm');
const todoInput = document.getElementById('todoInput');
const todoList = document.getElementById('todoList');
const message = document.getElementById('message');
const globalSearch = document.getElementById('globalSearch');
const quickFilter = document.getElementById('quickFilter');
const sortSelect = document.getElementById('sortSelect');
const newTaskBtn = document.getElementById('newTaskBtn');
const addInlineBtn = document.getElementById('addInlineBtn');
const themeToggle = document.getElementById('themeToggle');

const cardTotal = document.getElementById('cardTotal');
const cardOpen = document.getElementById('cardOpen');
const cardDone = document.getElementById('cardDone');
const cardProd = document.getElementById('cardProd');

let todos = [];
let filter = 'all';
let searchQuery = '';
let quickQuery = '';

function setMessage(text) {
  message.textContent = text;
}

function formatDate(value) {
  const date = new Date(value);
  return new Intl.DateTimeFormat('fr-FR', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function updateStats() {
  const done = todos.filter((todo) => todo.completed).length;
  const total = todos.length;
  const open = total - done;
  if (cardTotal) cardTotal.textContent = total;
  if (cardOpen) cardOpen.textContent = open;
  if (cardDone) cardDone.textContent = done;
  const prod = total === 0 ? 0 : Math.round((done / total) * 100);
  if (cardProd) cardProd.textContent = prod + '%';
}

function visibleTodos() {
  let list = todos.slice();

  // quick status filter
  if (quickQuery) {
    const q = quickQuery.toLowerCase();
    if (q === 'active' || q === 'en cours' || q === 'open') list = list.filter(t => !t.completed);
    else if (q === 'done' || q === 'terminées' || q === 'completed') list = list.filter(t => t.completed);
    else list = list.filter(t => t.title.toLowerCase().includes(q) || (t.description && t.description.toLowerCase().includes(q)));
  }

  // global search
  if (searchQuery) {
    const q = searchQuery.toLowerCase();
    list = list.filter(t => t.title.toLowerCase().includes(q) || (t.description && t.description.toLowerCase().includes(q)));
  }

  // sort
  const sort = sortSelect ? sortSelect.value : 'new';
  if (sort === 'alpha') list.sort((a,b) => a.title.localeCompare(b.title));
  else if (sort === 'old') list.sort((a,b) => new Date(a.created_at) - new Date(b.created_at));
  else list.sort((a,b) => new Date(b.created_at) - new Date(a.created_at));

  return list;
}

function renderTodos() {
  const items = visibleTodos();
  todoList.innerHTML = '';

  if (!items.length) {
    const empty = document.createElement('li');
    empty.className = 'empty-state';
    empty.textContent = filter === 'all' ? 'Aucune tâche pour le moment.' : 'Aucune tâche dans ce filtre.';
    todoList.appendChild(empty);
    updateStats();
    return;
  }

  for (const todo of items) {
    const item = document.createElement('li');
    item.className = `todo-item${todo.completed ? ' is-completed' : ''}`;
    item.dataset.id = String(todo.id);

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.className = 'todo-toggle';
    checkbox.checked = todo.completed;
    checkbox.ariaLabel = `Marquer ${todo.title} comme ${todo.completed ? 'non terminée' : 'terminée'}`;
    checkbox.addEventListener('change', () => toggleTodo(todo.id, checkbox.checked));

    const content = document.createElement('div');
    content.className = 'todo-content';

    const title = document.createElement('div');
    title.className = 'todo-title';
    title.textContent = todo.title;

    title.addEventListener('dblclick', () => startEdit(todo, content, title));

    const meta = document.createElement('div');
    meta.className = 'todo-meta';
    meta.textContent = `Créée le ${formatDate(todo.created_at)}`;

    content.append(title, meta);

    const actions = document.createElement('div');
    actions.className = 'todo-actions';

    const menuEdit = document.createElement('button');
    menuEdit.type = 'button';
    menuEdit.title = 'Modifier';
    menuEdit.innerHTML = '✏️';
    menuEdit.addEventListener('click', () => startEdit(todo, content, title));

    const menuDone = document.createElement('button');
    menuDone.type = 'button';
    menuDone.title = todo.completed ? 'Marquer non terminée' : 'Marquer terminée';
    menuDone.innerHTML = todo.completed ? '↩️' : '✅';
    menuDone.addEventListener('click', () => toggleTodo(todo.id, !todo.completed));

    const menuDelete = document.createElement('button');
    menuDelete.type = 'button';
    menuDelete.title = 'Supprimer';
    menuDelete.innerHTML = '🗑️';
    menuDelete.addEventListener('click', () => deleteTodo(todo.id));

    actions.append(menuEdit, menuDone, menuDelete);
    item.append(checkbox, content, actions);
    todoList.appendChild(item);
  }

  updateStats();
}

function setFilter(nextFilter) {
  filter = nextFilter;
  filterButtons.forEach((button) => {
    button.classList.toggle('is-active', button.dataset.filter === nextFilter);
  });
  renderTodos();
}

async function loadTodos() {
  const response = await fetch('/api/todos');
  todos = await response.json();
  renderTodos();
}

async function createTodo(title) {
  const response = await fetch('/api/todos', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });

  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload.error || 'Impossible de créer la tâche.');
  }

  todos = [payload, ...todos];
  renderTodos();
}

async function toggleTodo(id, completed) {
  const response = await fetch(`/api/todos/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ completed }),
  });

  const payload = await response.json();

  if (!response.ok) {
    setMessage(payload.error || 'Impossible de mettre à jour la tâche.');
    await loadTodos();
    return;
  }

  todos = todos.map((todo) => (todo.id === id ? payload : todo));
  renderTodos();
  setMessage('Tâche mise à jour.');
}

async function deleteTodo(id) {
  const response = await fetch(`/api/todos/${id}`, { method: 'DELETE' });
  const payload = await response.json();

  if (!response.ok) {
    setMessage(payload.error || 'Impossible de supprimer la tâche.');
    return;
  }

  todos = todos.filter((todo) => todo.id !== id);
  renderTodos();
  setMessage('Tâche supprimée.');
}

async function saveTodo(id, title) {
  const response = await fetch(`/api/todos/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });

  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload.error || 'Impossible de modifier la tâche.');
  }

  todos = todos.map((todo) => (todo.id === id ? payload : todo));
  renderTodos();
  setMessage('Tâche modifiée.');
}

function startEdit(todo, content, titleNode) {
  const wrapper = document.createElement('div');
  wrapper.style.display = 'grid';
  wrapper.style.gap = '6px';

  const input = document.createElement('input');
  input.className = 'todo-title-input';
  input.value = todo.title;
  input.maxLength = 140;

  const hint = document.createElement('small');
  hint.className = 'todo-meta';
  hint.textContent = 'Entrée pour enregistrer, Échap pour annuler.';

  wrapper.append(input, hint);
  content.replaceChildren(wrapper);
  input.focus();
  input.select();

  const cancel = () => {
    renderTodos();
  };

  const commit = async () => {
    const nextTitle = input.value.trim();

    if (!nextTitle) {
      setMessage('Le titre ne peut pas être vide.');
      input.focus();
      return;
    }

    try {
      await saveTodo(todo.id, nextTitle);
    } catch (error) {
      setMessage(error.message);
      await loadTodos();
    }
  };

  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      commit();
    }

    if (event.key === 'Escape') {
      cancel();
    }
  });

  input.addEventListener('blur', commit);
}

todoForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const title = todoInput.value.trim();

  if (!title) {
    setMessage('Ajoute un titre avant de valider.');
    todoInput.focus();
    return;
  }

  try {
    await createTodo(title);
    todoInput.value = '';
    todoInput.focus();
    setMessage('Tâche ajoutée.');
  } catch (error) {
    setMessage(error.message);
  }
});

// UI bindings
if (globalSearch) {
  globalSearch.addEventListener('input', (e) => { searchQuery = e.target.value.trim(); renderTodos(); });
}

if (quickFilter) {
  quickFilter.addEventListener('input', (e) => { quickQuery = e.target.value.trim(); renderTodos(); });
}

if (sortSelect) {
  sortSelect.addEventListener('change', () => renderTodos());
}

if (newTaskBtn) newTaskBtn.addEventListener('click', () => { todoInput.focus(); });
if (addInlineBtn) addInlineBtn.addEventListener('click', () => { todoInput.focus(); });

// theme toggle
function applyTheme(theme) {
  if (theme === 'dark') document.documentElement.setAttribute('data-theme','dark');
  else document.documentElement.removeAttribute('data-theme');
}

const savedTheme = localStorage.getItem('theme') || 'light';
applyTheme(savedTheme);
if (themeToggle) {
  themeToggle.addEventListener('click', () => {
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    localStorage.setItem('theme', next);
    applyTheme(next);
  });
}

loadTodos().catch(() => {
  setMessage("Impossible de charger la liste. Vérifie que le serveur tourne.");
});

/* Timer (simple Pomodoro-like) */
const timerToggle = document.getElementById('timerToggle');
const timerReset = document.getElementById('timerReset');
const timerDisplay = document.getElementById('timerDisplay');

const TIMER_KEY = 'aurora_timer_v1';
let timerInterval = null;
let timerState = {
  remaining: 25 * 60, // seconds
  running: false,
  endAt: null
};

function loadTimer() {
  try {
    const raw = localStorage.getItem(TIMER_KEY);
    if (raw) {
      const s = JSON.parse(raw);
      timerState = Object.assign(timerState, s);
      // if running, recompute remaining
      if (timerState.running && timerState.endAt) {
        const diff = Math.round((timerState.endAt - Date.now()) / 1000);
        timerState.remaining = Math.max(0, diff);
        if (timerState.remaining === 0) timerState.running = false;
      }
    }
  } catch (e) { console.warn('timer load failed', e); }
}

function saveTimer() { localStorage.setItem(TIMER_KEY, JSON.stringify(timerState)); }

function formatTime(s) {
  const mm = String(Math.floor(s / 60)).padStart(2,'0');
  const ss = String(Math.floor(s % 60)).padStart(2,'0');
  return `${mm}:${ss}`;
}

function updateTimerDisplay() {
  if (timerDisplay) timerDisplay.textContent = formatTime(timerState.remaining);
  if (timerToggle) timerToggle.textContent = timerState.running ? '⏸' : '▶';
}

function tickTimer() {
  if (!timerState.running) return;
  const now = Date.now();
  timerState.remaining = Math.max(0, Math.round((timerState.endAt - now) / 1000));
  if (timerState.remaining <= 0) {
    timerState.running = false;
    clearInterval(timerInterval); timerInterval = null;
    // simple alert
    try { new Audio('/static/tick.mp3'); } catch (e) {}
  }
  updateTimerDisplay();
  saveTimer();
}

function startTimer() {
  if (timerState.running) return;
  timerState.endAt = Date.now() + timerState.remaining * 1000;
  timerState.running = true;
  if (timerInterval) clearInterval(timerInterval);
  timerInterval = setInterval(tickTimer, 500);
  saveTimer();
  updateTimerDisplay();
}

function pauseTimer() {
  if (!timerState.running) return;
  timerState.running = false;
  // compute remaining
  const diff = Math.max(0, Math.round((timerState.endAt - Date.now()) / 1000));
  timerState.remaining = diff;
  timerState.endAt = null;
  if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
  saveTimer();
  updateTimerDisplay();
}

function resetTimer() {
  timerState.running = false;
  timerState.remaining = 25 * 60;
  timerState.endAt = null;
  if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
  saveTimer();
  updateTimerDisplay();
}

if (timerToggle) {
  timerToggle.addEventListener('click', () => {
    if (timerState.running) pauseTimer(); else startTimer();
  });
}

if (timerReset) {
  timerReset.addEventListener('click', () => resetTimer());
}

loadTimer();
if (timerState.running) startTimer();
updateTimerDisplay();
