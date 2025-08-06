// script.js
document.addEventListener("DOMContentLoaded", function() {
  // Initialize cart count
  updateCartCount();
  
  // Button hover effects
  const buttons = document.querySelectorAll(".btn");
  buttons.forEach((btn) => {
    btn.addEventListener("mouseenter", function() {
      this.style.transform = "translateY(-2px)";
      this.style.boxShadow = "0 5px 15px rgba(0,0,0,0.1)";
    });
    btn.addEventListener("mouseleave", function() {
      this.style.transform = "translateY(0)";
      this.style.boxShadow = "none";
    });
  });

  // File upload preview (for admin dashboard)
  const fileUpload = document.getElementById("image");
  if (fileUpload) {
    fileUpload.addEventListener("change", function(e) {
      const file = e.target.files[0];
      if (file) {
        const previewContainer = document.querySelector(".file-upload");
        let preview = previewContainer.querySelector(".image-preview");
        
        if (!preview) {
          preview = document.createElement("div");
          preview.className = "image-preview";
          previewContainer.appendChild(preview);
        }
        
        preview.innerHTML = `
          <img src="${URL.createObjectURL(file)}" alt="Preview" class="upload-preview">
          <p>${file.name} (${(file.size / 1024).toFixed(1)}KB)</p>
        `;
      }
    });
  }

  // Real-time cart counter
  function updateCartCount() {
    fetch('/get_cart_count')
      .then(response => response.json())
      .then(data => {
        const cartBtn = document.querySelector('.cart-btn');
        if (cartBtn) {
          cartBtn.textContent = `Cart (${data.count})`;
          // Pulse animation when cart updates
          if (data.count > 0) {
            cartBtn.classList.add('pulse');
            setTimeout(() => {
              cartBtn.classList.remove('pulse');
            }, 500);
          }
        }
      })
      .catch(error => console.error('Error updating cart:', error));
  }

  // Set interval to update cart every 3 seconds
  setInterval(updateCartCount, 3000);

  // Quantity handlers (for cart page)
  document.querySelectorAll(".quantity-btn").forEach(btn => {
    btn.addEventListener("click", function() {
      const productId = this.dataset.id;
      const action = this.dataset.action;
      updateCartQuantity(productId, action);
    });
  });

  // Product image error handling
  document.querySelectorAll(".product-card img").forEach(img => {
    img.addEventListener("error", function() {
      this.src = "/static/images/default-product.png";
    });
  });

  // Checkout form validation
  const checkoutForm = document.querySelector("form[action='/checkout']");
  if (checkoutForm) {
    checkoutForm.addEventListener("submit", function(e) {
      const phone = this.querySelector("input[name='phone']").value;
      if (!/^\d{10}$/.test(phone)) {
        e.preventDefault();
        alert("Please enter a valid 10-digit phone number");
      }
    });
  }
});

// Cart quantity update function
function updateCartQuantity(productId, action) {
  fetch(`/update_cart/${productId}/${action}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    }
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      // Update the UI
      const quantityElement = document.querySelector(`.quantity-value[data-id="${productId}"]`);
      if (quantityElement) {
        quantityElement.textContent = data.newQuantity;
        document.querySelector(`.subtotal[data-id="${productId}"]`).textContent = 
          `?${(data.newQuantity * data.price).toFixed(2)}`;
        
        // Update totals
        document.getElementById("cart-total").textContent = `?${data.cartTotal.toFixed(2)}`;
        document.getElementById("grand-total").textContent = 
          `?${(data.cartTotal + 30).toFixed(2)}`; // 30 is delivery charge
        
        // Show update animation
        quantityElement.parentElement.classList.add('updated');
        setTimeout(() => {
          quantityElement.parentElement.classList.remove('updated');
        }, 300);
      }
    }
  })
  .catch(error => console.error('Error:', error));
}

// Toast notification function
function showToast(message, type = 'success') {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  document.body.appendChild(toast);
  
  setTimeout(() => {
    toast.classList.add("show");
  }, 10);
  
  setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => {
      document.body.removeChild(toast);
    }, 300);
  }, 3000);
}