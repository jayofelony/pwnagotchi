/* ============================================
   Modern App Utilities
   ============================================ */

// Format timestamps using Intl API
const formatTimeAgo = (timestamp) => {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now - date;
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 60) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleDateString();
};

// Update time elements
const updateTimeElements = () => {
  document.querySelectorAll("time.timeago").forEach((el) => {
    const dt = el.getAttribute("datetime");
    if (dt) {
      el.textContent = formatTimeAgo(dt);
    }
  });
};

// Initialize time formatting on page load and update every minute
document.addEventListener("DOMContentLoaded", () => {
  updateTimeElements();
  setInterval(updateTimeElements, 60000);
});

// Modern AJAX helper
const apiCall = (url, options = {}) => {
  const {
    method = "GET",
    data = null,
    contentType = "application/x-www-form-urlencoded",
    onSuccess = null,
    onError = null,
    onComplete = null,
  } = options;

  const fetchOptions = {
    method,
    headers: {
      "Content-Type": contentType,
    },
  };

  if (data && method !== "GET") {
    if (contentType === "application/json") {
      fetchOptions.body = JSON.stringify(data);
    } else {
      fetchOptions.body = new URLSearchParams(data).toString();
    }
  }

  return fetch(url, fetchOptions)
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.text().then((text) => {
        try {
          return JSON.parse(text);
        } catch {
          return text;
        }
      });
    })
    .then((result) => {
      onSuccess?.(result);
      return result;
    })
    .catch((error) => {
      console.error("API Error:", error);
      onError?.(error);
    })
    .finally(() => {
      onComplete?.();
    });
};
// Generate QR Code using kjua library (already loaded in base.html)
const generateQRCode = (elementId, text, options = {}) => {
  const { size = 256 } = options;

  const element = document.getElementById(elementId);
  if (!element) {
    console.error("QR Code element not found:", elementId);
    return;
  }

  try {
    // Clear existing content
    element.innerHTML = "";

    // Check if kjua library is available
    if (typeof kjua !== "undefined") {
      const qrCanvas = kjua({
        text: text,
        size: size,
        fill: "#000000",
        back: "#ffffff",
        ecLevel: "H",
        rounded: 50,
      });
      element.appendChild(qrCanvas);
    } else {
      console.warn("kjua library not loaded");
      element.innerHTML =
        '<p style="color: var(--text-muted);">QR Code library not available</p>';
    }
  } catch (e) {
    console.error("QR Code generation error:", e);
    element.innerHTML =
      '<p style="color: var(--text-muted);">QR Code unavailable: ' +
      e.message +
      "</p>";
  }
};

// Form submission with AJAX
const handleFormSubmit = (formSelector, options = {}) => {
  const form = document.querySelector(formSelector);
  if (!form) return;

  form.addEventListener("submit", (e) => {
    e.preventDefault();

    const url = form.getAttribute("action");
    const method = form.getAttribute("method") || "POST";
    const formData = new FormData(form);

    const data = {};
    formData.forEach((value, key) => {
      data[key] = value;
    });

    apiCall(url, {
      method,
      data,
      contentType: "application/x-www-form-urlencoded",
      onSuccess: (result) => {
        if (typeof result === "string" && result.includes("error")) {
          alert("Error: " + result);
        } else if (result.error) {
          alert("Error: " + result.error);
        } else {
          options.onSuccess?.(result);
          if (options.redirect) {
            window.location.href = options.redirect;
          }
        }
      },
      onError: (error) => {
        alert("Request failed: " + error.message);
        options.onError?.(error);
      },
    });
  });
};

// Event delegation for dynamic elements
const delegateEvent = (eventType, selector, handler) => {
  document.addEventListener(eventType, (e) => {
    const target = e.target.closest(selector);
    if (target) {
      handler.call(target, e);
    }
  });
};

// Toggle element visibility
const toggleElement = (selector) => {
  const element = document.querySelector(selector);
  if (element) {
    element.classList.toggle("hidden");
  }
};

// Show alert popup
const showAlert = (message, type = "error") => {
  const alertDiv = document.createElement("div");
  alertDiv.className = `alert alert-${type} p-2`;
  alertDiv.textContent = message;
  alertDiv.style.position = "fixed";
  alertDiv.style.top = "1rem";
  alertDiv.style.right = "1rem";
  alertDiv.style.zIndex = "9999";
  alertDiv.style.minWidth = "200px";

  document.body.appendChild(alertDiv);

  setTimeout(() => {
    alertDiv.remove();
  }, 5000);
};

// Page refresh at interval
const autoRefresh = (interval) => {
  setInterval(() => {
    window.location.reload();
  }, interval);
};

// Mark elements as active based on current page
const setActiveNavItem = () => {
  const currentPath = window.location.pathname;
  document.querySelectorAll("a[href]").forEach((link) => {
    const href = link.getAttribute("href");
    if (href === currentPath) {
      link.classList.add("active");
    } else {
      link.classList.remove("active");
    }
  });
};

// Search/filter functionality
const filterList = (inputSelector, itemSelector) => {
  const input = document.querySelector(inputSelector);
  if (!input) return;

  input.addEventListener("input", (e) => {
    const filter = e.target.value.toLowerCase();
    document.querySelectorAll(itemSelector).forEach((item) => {
      const text = item.textContent.toLowerCase();
      item.style.display = text.includes(filter) ? "" : "none";
    });
  });
};

// Poll for updates (e.g., image refresh)
const pollResource = (elementSelector, urlGetter, interval) => {
  const element = document.querySelector(elementSelector);
  if (!element) return;

  setInterval(() => {
    const url =
      typeof urlGetter === "function" ? urlGetter(element) : urlGetter;
    element.src = url.includes("?")
      ? url + "&t=" + new Date().getTime()
      : url + "?" + new Date().getTime();
  }, interval);
};

// Toast notification system
const showToast = (message, duration = 4000, type = "error") => {
  // Remove any existing toast
  const existing = document.querySelector(".toast");
  if (existing) existing.remove();

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;

  document.body.appendChild(toast);

  // Trigger animation
  setTimeout(() => toast.classList.add("show"), 10);

  // Remove after duration
  setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => toast.remove(), 300);
  }, duration);
};
