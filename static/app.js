const todoForm = document.getElementById('todoForm');
const todoInput = document.getElementById('todoInput');
const todoList = document.getElementById('todoList');
const message = document.getElementById('message');
const filterButtons = Array.from(document.querySelectorAll('.filter'));
const totalCount = document.getElementById('totalCount');
const openCount = document.getElementById('openCount');
const doneCount = document.getElementById('doneCount');

let todos = [];
let filter = 'all';

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
  totalCount.textContent = todos.length;
  openCount.textContent = todos.length - done;
  doneCount.textContent = done;
}

function visibleTodos() {
  if (filter === 'active') {
    return todos.filter((todo) => !todo.completed);
  }

  if (filter === 'completed') {
    return todos.filter((todo) => todo.completed);
  }

  return todos;
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

    const editButton = document.createElement('button');
    editButton.type = 'button';
    editButton.textContent = 'Modifier';
    editButton.addEventListener('click', () => startEdit(todo, content, title));

    const deleteButton = document.createElement('button');
    deleteButton.type = 'button';
    deleteButton.className = 'danger';
    deleteButton.textContent = 'Supprimer';
    deleteButton.addEventListener('click', () => deleteTodo(todo.id));

    actions.append(editButton, deleteButton);
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

filterButtons.forEach((button) => {
  button.addEventListener('click', () => setFilter(button.dataset.filter));
});

loadTodos().catch(() => {
  setMessage("Impossible de charger la liste. Vérifie que le serveur tourne.");
});
