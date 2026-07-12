(() => {
  "use strict";

  const statusEl = document.getElementById("authStatus");
  const leadEl = document.getElementById("authLead");
  const signInForm = document.getElementById("signInForm");
  const registerForm = document.getElementById("registerForm");
  const signInEmail = document.getElementById("signInEmail");
  const signInPassword = document.getElementById("signInPassword");
  const registerEmail = document.getElementById("registerEmail");
  const registerPassword = document.getElementById("registerPassword");
  const confirmPassword = document.getElementById("confirmPassword");
  const rememberMe = document.getElementById("rememberMe");
  const signInButton = document.getElementById("signInButton");
  const registerButton = document.getElementById("registerButton");
  const resetPasswordButton = document.getElementById("resetPasswordButton");
  const showSignIn = document.getElementById("showSignIn");
  const showRegister = document.getElementById("showRegister");

  const params = new URLSearchParams(window.location.search);
  const rawNext = params.get("next") || "/tasks/clone-voice";
  const nextUrl = rawNext.startsWith("/") && !rawNext.startsWith("//") ? rawNext : "/tasks/clone-voice";
  let action = "idle";
  let redirecting = false;

  function setStatus(message, kind = "info") {
    statusEl.textContent = message;
    statusEl.className = `status ${kind} show`;
  }

  function setBusy(isBusy) {
    signInButton.disabled = isBusy;
    registerButton.disabled = isBusy;
    resetPasswordButton.disabled = isBusy;
  }

  function showMode(mode) {
    const registering = mode === "register";
    signInForm.classList.toggle("hidden", registering);
    registerForm.classList.toggle("hidden", !registering);
    showSignIn.classList.toggle("active", !registering);
    showRegister.classList.toggle("active", registering);
    showSignIn.setAttribute("aria-selected", String(!registering));
    showRegister.setAttribute("aria-selected", String(registering));
    leadEl.textContent = registering
      ? "Create an account, then choose a paid plan to activate your workspace."
      : "Sign in to access your private workspace.";
    setStatus(registering ? "Create your account below." : "Enter your email and password.", "info");
  }

  function friendlyError(error) {
    const code = String(error?.code || "");
    if (code.includes("invalid-credential") || code.includes("wrong-password") || code.includes("user-not-found")) return "The email or password is incorrect.";
    if (code.includes("email-already-in-use")) return "An account already exists for this email. Please sign in instead.";
    if (code.includes("weak-password")) return "Use a stronger password with at least eight characters.";
    if (code.includes("invalid-email")) return "Enter a valid email address.";
    if (code.includes("too-many-requests")) return "Too many attempts. Wait briefly and try again.";
    return error?.message || "Authentication failed.";
  }

  async function loadFirebaseConfig() {
    const response = await fetch(`/api/auth/firebase-config?t=${Date.now()}`, { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.message || payload.error || "Firebase configuration is unavailable.");
    return payload.firebaseConfig;
  }

  async function createServerSession(user, remember) {
    const idToken = await user.getIdToken(true);
    const response = await fetch("/api/auth/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idToken, remember: Boolean(remember) })
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.message || payload.error || "Could not create a secure session.");
  }

  async function bootstrapAccountForUser(user) {
    const token = await user.getIdToken(true);
    const response = await fetch("/api/account/bootstrap", {
      method: "POST",
      headers: { "Authorization": `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.message || payload.error || "Could not prepare your workspace.");
    return payload;
  }

  async function init() {
    try {
      if (!window.firebase?.auth) throw new Error("Firebase browser SDK failed to load.");
      const config = await loadFirebaseConfig();
      if (!window.firebase.apps.length) window.firebase.initializeApp(config);
      const auth = window.firebase.auth();

      auth.onAuthStateChanged(async (user) => {
        if (!user || redirecting) {
          if (!user) setStatus("Enter your email and password.", "info");
          return;
        }

        try {
          redirecting = true;
          const remember = action === "register" ? true : rememberMe.checked;
          setStatus("Securing your session and preparing your workspace...", "info");
          await createServerSession(user, remember);
          await bootstrapAccountForUser(user);
          const destination = action === "register" ? "/plans?onboarding=1" : nextUrl;
          setStatus("Account ready. Redirecting...", "success");
          window.location.assign(destination);
        } catch (error) {
          redirecting = false;
          setStatus(error.message || "Could not prepare your account.", "error");
        }
      });

      signInForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        action = "signin";
        setBusy(true);
        try {
          const persistence = rememberMe.checked
            ? window.firebase.auth.Auth.Persistence.LOCAL
            : window.firebase.auth.Auth.Persistence.SESSION;
          await auth.setPersistence(persistence);
          await auth.signInWithEmailAndPassword(signInEmail.value.trim(), signInPassword.value);
        } catch (error) {
          setStatus(friendlyError(error), "error");
          setBusy(false);
        }
      });

      registerForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const password = registerPassword.value;
        if (password !== confirmPassword.value) {
          setStatus("Passwords do not match.", "error");
          confirmPassword.focus();
          return;
        }
        if (password.length < 8) {
          setStatus("Password must contain at least eight characters.", "error");
          registerPassword.focus();
          return;
        }
        action = "register";
        setBusy(true);
        try {
          await auth.setPersistence(window.firebase.auth.Auth.Persistence.LOCAL);
          await auth.createUserWithEmailAndPassword(registerEmail.value.trim(), password);
        } catch (error) {
          action = "idle";
          setStatus(friendlyError(error), "error");
          setBusy(false);
        }
      });

      resetPasswordButton.addEventListener("click", async () => {
        const email = signInEmail.value.trim();
        if (!email) {
          setStatus("Enter your email address first, then select Forgot password.", "error");
          signInEmail.focus();
          return;
        }
        setBusy(true);
        try {
          await auth.sendPasswordResetEmail(email);
          setStatus("Password-reset email sent. Check your inbox and spam folder.", "success");
        } catch (error) {
          setStatus(friendlyError(error), "error");
        } finally {
          setBusy(false);
        }
      });

      showSignIn.addEventListener("click", () => showMode("signin"));
      showRegister.addEventListener("click", () => showMode("register"));
      showMode(params.get("mode") === "register" ? "register" : "signin");
    } catch (error) {
      setStatus(error.message || "Could not start authentication.", "error");
      setBusy(false);
    }
  }

  init();
})();
