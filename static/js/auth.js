// Authentication and session logic for the Habit Tracker System
// The server-side Flask session is the single source of truth.

const Auth = {
    clearLocalSession() {
        localStorage.removeItem("user_id");
        localStorage.removeItem("user_email");
    },

    // Kept for compatibility, but no longer used as the app's auth source of truth.
    saveSession() {
        this.clearLocalSession();
        return true;
    },

    async isAuthenticated() {
        try {
            const response = await fetch("/api/me", {
                method: "GET",
                credentials: "include"
            });
            return response.ok;
        } catch (error) {
            console.warn("Auth.isAuthenticated failed:", error);
            return false;
        }
    },

    async getUserId() {
        try {
            const response = await fetch("/api/me", {
                method: "GET",
                credentials: "include"
            });
            if (!response.ok) return null;
            const data = await response.json();
            return data.user_id || null;
        } catch (error) {
            console.warn("Auth.getUserId failed:", error);
            return null;
        }
    },

    async getUserEmail() {
        try {
            const response = await fetch("/api/me", {
                method: "GET",
                credentials: "include"
            });
            if (!response.ok) return null;
            const data = await response.json();
            return data.email || null;
        } catch (error) {
            console.warn("Auth.getUserEmail failed:", error);
            return null;
        }
    },

    async logout() {
        try {
            await fetch("/api/logout", {
                method: "POST",
                credentials: "include"
            });
        } catch (e) {
            console.error("Logout API error:", e);
        }

        this.clearLocalSession();
        window.location.href = "/login";
    },

    async guardDashboard() {
        if (!(await this.isAuthenticated())) {
            window.location.href = "/login";
        }
    },

    async guardGuestPage() {
        if (await this.isAuthenticated()) {
            window.location.href = "/";
        }
    }
};

// Handle register form submission
async function handleRegister(event) {
    event.preventDefault();

    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    const confirmPassword = document.getElementById("confirmPassword").value;
    const errorMessage = document.getElementById("errorMessage");

    if (!email || !password) {
        errorMessage.innerText = "Please fill in all fields.";
        return;
    }

    if (password !== confirmPassword) {
        errorMessage.innerText = "Passwords do not match.";
        return;
    }

    try {
        errorMessage.innerText = "";
        const response = await fetch("/api/register", {
            method: "POST",
            credentials: "include",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ email, password })
        });

        const data = await response.json();

        if (response.ok) {
            alert(data.message || "Registration successful! Please log in.");
            window.location.href = "/login";
        } else {
            errorMessage.innerText = data.error || data.message || "Registration failed.";
        }
    } catch (error) {
        console.error("Register error:", error);
        errorMessage.innerText = "Failed to connect to the server.";
    }
}

// Handle login form submission
async function handleLogin(event) {
    event.preventDefault();

    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    const errorMessage = document.getElementById("errorMessage");

    if (!email || !password) {
        errorMessage.innerText = "Please fill in all fields.";
        return;
    }

    try {
        errorMessage.innerText = "";
        const response = await fetch("/api/login", {
            method: "POST",
            credentials: "include",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ email, password })
        });

        const data = await response.json();

        if (response.ok) {
            Auth.clearLocalSession();
            window.location.href = "/";
        } else {
            errorMessage.innerText = data.error || data.message || "Invalid credentials.";
        }
    } catch (error) {
        console.error("Login error:", error);
        errorMessage.innerText = "Failed to connect to the server.";
    }
}
