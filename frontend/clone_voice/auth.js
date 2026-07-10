(() => {
  const statusEl = document.getElementById("authStatus");
  const formEl = document.getElementById("authForm");
  const emailEl = document.getElementById("email");
  const passwordEl = document.getElementById("password");
  const signInButton = document.getElementById("signInButton");
  const registerButton = document.getElementById("registerButton");

  const params = new URLSearchParams(window.location.search);
  const nextUrl = params.get("next") || "/tasks/clone-voice";

  function setStatus(message, kind = "info") {
    statusEl.textContent = message;
    statusEl.className = `status ${kind} show`;
  }

  function setBusy(isBusy) {
    signInButton.disabled = isBusy;
    registerButton.disabled = isBusy;
  }

  function friendlyError(error) {
    const code = error && error.code ? String(error.code) : "";
    if (code.includes("invalid-credential") || code.includes("wrong-password") || code.includes("user-not-found")) {
      return "The email or password is incorrect.";
    }
    if (code.includes("email-already-in-use")) {
      return "An account already exists for this email. Please sign in instead.";
    }
    if (code.includes("weak-password")) {
      return "Please use a stronger password.";
    }
    if (code.includes("invalid-email")) {
      return "Please enter a valid email address.";
    }
    return error && error.message ? error.message : "Authentication failed.";
  }


  async function bootstrapAccountForUser(user) {
    if (!user) {
      throw new Error("Authentication required.");
    }

    const token = await user.getIdToken(true);

    const response = await fetch("/api/account/bootstrap", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({})
    });

    const payload = await response.json().catch(() => ({}));

    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || payload.error || "Could not prepare your workspace.");
    }

    return payload;
  }

  async function loadFirebaseConfig() {
    const response = await fetch(`/api/auth/firebase-config?t=${Date.now()}`, {
      cache: "no-store"
    });

    const payload = await response.json().catch(() => ({}));

    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || payload.error || "Firebase configuration is not available.");
    }

    return payload.firebaseConfig;
  }

  async function init() {
    try {
      setStatus("Loading authentication...", "info");

      if (!window.firebase || !window.firebase.auth) {
        throw new Error("Firebase browser SDK failed to load.");
      }

      const config = await loadFirebaseConfig();
      window.firebase.initializeApp(config);

      const auth = window.firebase.auth();

      auth.onAuthStateChanged(async (user) => {
        if (user) {
          try {
            setStatus("Preparing your private workspace...", "info");
            await bootstrapAccountForUser(user);
            setStatus("Signed in. Redirecting...", "success");
            window.location.assign(nextUrl);
          } catch (error) {
            setStatus(error.message || "Could not prepare your workspace.", "error");
          }
        } else {
          setStatus("Enter your email and password.", "info");
        }
      });

      async function signIn() {
        const email = emailEl.value.trim();
        const password = passwordEl.value;

        setBusy(true);
        try {
          await auth.signInWithEmailAndPassword(email, password);
        } catch (error) {
          setStatus(friendlyError(error), "error");
        } finally {
          setBusy(false);
        }
      }

      async function register() {
        const email = emailEl.value.trim();
        const password = passwordEl.value;

        setBusy(true);
        try {
          await auth.createUserWithEmailAndPassword(email, password);
          setStatus("Account created. Redirecting...", "success");
        } catch (error) {
          setStatus(friendlyError(error), "error");
        } finally {
          setBusy(false);
        }
      }

      formEl.addEventListener("submit", (event) => {
        event.preventDefault();
        signIn();
      });

      registerButton.addEventListener("click", (event) => {
        event.preventDefault();
        register();
      });
    } catch (error) {
      setStatus(error.message || "Could not start authentication.", "error");
      setBusy(false);
    }
  }

  init();
})();
