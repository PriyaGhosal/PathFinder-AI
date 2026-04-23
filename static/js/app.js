const selectedTiles = document.querySelectorAll(".check-tile input");

selectedTiles.forEach((input) => {
  const syncState = () => {
    input.closest(".check-tile").classList.toggle("is-selected", input.checked);
  };

  input.addEventListener("change", syncState);
  syncState();
});

const roadmapTasks = document.querySelectorAll("[data-task]");

roadmapTasks.forEach((task) => {
  const key = `pathfinder-task-${task.dataset.task}`;
  task.checked = localStorage.getItem(key) === "done";

  task.addEventListener("change", () => {
    if (task.checked) {
      localStorage.setItem(key, "done");
    } else {
      localStorage.removeItem(key);
    }
  });
});

const themeToggle = document.querySelector("[data-theme-toggle]");
const themeLabel = document.querySelector("[data-theme-label]");

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("pathfinder-theme", theme);

  if (themeToggle && themeLabel) {
    themeLabel.textContent =
      theme === "dark" ? themeToggle.dataset.lightLabel : themeToggle.dataset.darkLabel;
  }
}

if (themeToggle) {
  setTheme(localStorage.getItem("pathfinder-theme") || "light");

  themeToggle.addEventListener("click", () => {
    const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
  });
}
