document.addEventListener("DOMContentLoaded", () => {
  const searchForm = document.querySelector(".md-search__form");
  const isApple = /Mac|iPhone|iPad|iPod/.test(navigator.platform);

  if (searchForm) {
    searchForm.dataset.shortcut = isApple ? "⌘ K" : "Ctrl K";
  }

  document.addEventListener("keydown", (event) => {
    const isSearchShortcut =
      event.key.toLowerCase() === "k" &&
      !event.altKey &&
      !event.shiftKey &&
      (event.metaKey || event.ctrlKey);

    if (!isSearchShortcut) return;

    event.preventDefault();

    const searchInput = document.querySelector("[data-md-component='search-query']");
    const searchCheckbox = document.querySelector("#__search");
    const searchToggle = document.querySelector("label[for='__search']");

    if (searchToggle && (!searchCheckbox || !searchCheckbox.checked)) {
      searchToggle.click();
    }

    window.setTimeout(() => {
      searchInput?.focus();
      searchInput?.select();
    }, 0);
  });
});
