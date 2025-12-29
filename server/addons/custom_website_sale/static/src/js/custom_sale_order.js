document.addEventListener("DOMContentLoaded", () => {
  if (document.querySelectorAll("#product_name")) {
    document.querySelectorAll("#product_name").forEach(el => {
      el.children[0].removeAttribute("href")
      el.children[0].classList.remove("cursor-pointer")
      el.children[0].style.textDecoration = "unset"
    })
  }
  if (document.querySelectorAll("#taxes")) {
    document.querySelectorAll("#taxes").forEach(el => {
      el.textContent = el.textContent.split("(")[0].trim()
    })
  }

})
