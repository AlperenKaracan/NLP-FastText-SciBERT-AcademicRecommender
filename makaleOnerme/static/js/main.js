document.addEventListener("DOMContentLoaded", function() {
  const loader = document.getElementById("loader");
  if (loader) {
    loader.style.display = "none";
  }

  console.log("Custom JS yüklendi.");

  const btns = document.querySelectorAll('.btn');
  btns.forEach(btn => {
    btn.addEventListener('click', function() {
      this.classList.add('animate__animated', 'animate__pulse');
      setTimeout(() => {
        this.classList.remove('animate__animated', 'animate__pulse');
      }, 500);
    });
  });

  const searchInput = document.getElementById('search_query');
  if (searchInput) {
    const suggestionBox = document.createElement('div');
    suggestionBox.classList.add('list-group', 'position-absolute');
    suggestionBox.style.zIndex = 1000;
    searchInput.parentNode.appendChild(suggestionBox);

    searchInput.addEventListener('input', function() {
      let query = this.value.trim();
      if (query.length < 2) {
        suggestionBox.innerHTML = '';
        return;
      }
      fetch(`/search-suggestions?q=${encodeURIComponent(query)}`)
        .then(res => res.json())
        .then(data => {
          suggestionBox.innerHTML = '';
          if (data.suggestions && data.suggestions.length > 0) {
            data.suggestions.forEach(item => {
              const li = document.createElement('a');
              li.classList.add('list-group-item', 'list-group-item-action');
              li.href = "#";
              li.textContent = item;
              li.addEventListener('click', function(e) {
                e.preventDefault();
                searchInput.value = this.textContent;
                suggestionBox.innerHTML = '';
              });
              suggestionBox.appendChild(li);
            });
          }
        })
        .catch(err => console.error(err));
    });
  }

  const scrollBtn = document.getElementById("scrollTopBtn");
  window.addEventListener("scroll", function() {
    if (document.body.scrollTop > 300 || document.documentElement.scrollTop > 300) {
      scrollBtn.style.display = "block";
    } else {
      scrollBtn.style.display = "none";
    }
  });

  scrollBtn.addEventListener("click", function() {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
});
