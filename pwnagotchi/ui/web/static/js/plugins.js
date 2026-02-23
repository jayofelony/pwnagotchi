// Plugins page event handlers

delegateEvent("change", "input[type='checkbox']", function (e) {
  const form = this.closest("form");
  const url = form.getAttribute("action");
  const formData = new FormData(form);
  apiCall(url, {
    method: "POST",
    data: Object.fromEntries(formData),
    onError: function () {
      showToast("Could not toggle plugin.", 5000, "error");
    },
  });
});

delegateEvent("click", "input[type='submit']", function (e) {
  const form = this.closest("form");
  const url = form.getAttribute("action");
  const formData = new FormData(form);
  apiCall(url, {
    method: "POST",
    data: Object.fromEntries(formData),
    onError: function () {
      showToast("Could not upgrade plugin.", 5000, "error");
    },
  });
});
