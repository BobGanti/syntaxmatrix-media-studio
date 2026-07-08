(() => {
  const $ = (selector) => document.querySelector(selector);

  const billingWorkspaceSelect = $("#billingWorkspaceSelect");
  const billingPlanSelect = $("#billingPlanSelect");
  const saveBillingPlanBtn = $("#saveBillingPlanBtn");
  const refreshBillingBtn = $("#refreshBillingBtn");
  const openStripeCheckoutBtn = $("#openStripeCheckoutBtn");
  const billingStatusBox = $("#billingStatusBox");
  const billingUsageBreakdown = $("#billingUsageBreakdown");
  const billingCurrentPlan = $("#billingCurrentPlan");
  const billingMonthlyLimit = $("#billingMonthlyLimit");
  const billingUsedCredits = $("#billingUsedCredits");
  const billingRemainingCredits = $("#billingRemainingCredits");
  const billingMonthlyRevenue = $("#billingMonthlyRevenue");
  const billingEstimatedCost = $("#billingEstimatedCost");
  const billingGrossMargin = $("#billingGrossMargin");
  const billingMarginPercent = $("#billingMarginPercent");

  const starterMonthlyPrice = $("#starterMonthlyPrice");
  const starterMonthlyCredits = $("#starterMonthlyCredits");
  const proMonthlyPrice = $("#proMonthlyPrice");
  const proMonthlyCredits = $("#proMonthlyCredits");
  const businessMonthlyPrice = $("#businessMonthlyPrice");
  const businessMonthlyCredits = $("#businessMonthlyCredits");
  const enterpriseMonthlyPrice = $("#enterpriseMonthlyPrice");
  const enterpriseMonthlyCredits = $("#enterpriseMonthlyCredits");

  const voiceParameterCredits = $("#voiceParameterCredits");
  const narrationCreditsPerSecond = $("#narrationCreditsPerSecond");
  const voiceProviderFixedCost = $("#voiceProviderFixedCost");
  const narrationProviderCostPerSecond = $("#narrationProviderCostPerSecond");
  const savePricingConfigBtn = $("#savePricingConfigBtn");
  const pricingStatusBox = $("#pricingStatusBox");

  let billingPlans = [];
  let pricingConfig = null;

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function money(value, currency = "EUR") {
    const amount = Number(value || 0);
    return `${currency} ${amount.toFixed(2)}`;
  }

  function formatCredits(value) {
    if (value === null || value === undefined) return "Unlimited";
    return Number(value || 0).toLocaleString();
  }

  function planByKey(key) {
    return (pricingConfig?.plans || []).find((plan) => plan.key === key) || {};
  }

  function creditRule(eventType) {
    return (pricingConfig?.creditRules || []).find((rule) => rule.eventType === eventType) || {};
  }

  function costRule(eventType) {
    return (pricingConfig?.providerCostRules || []).find((rule) => rule.eventType === eventType) || {};
  }

  async function loadAdminWorkspaces() {
    try {
      const response = await fetch(`/api/admin/workspaces?t=${Date.now()}`, {
        cache: "no-store"
      });

      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not load workspaces");
      }

      const current = billingWorkspaceSelect.value || "mock_user_001";
      const rows = data.workspaces || [];

      if (rows.length) {
        billingWorkspaceSelect.innerHTML = rows.map((workspace) => `
          <option value="${escapeHtml(workspace.workspaceId)}">${escapeHtml(workspace.label || workspace.workspaceId)}</option>
        `).join("");

        billingWorkspaceSelect.value = rows.some((workspace) => workspace.workspaceId === current)
          ? current
          : rows[0].workspaceId;
      }
    } catch (error) {
      console.warn("[Finance Console] Could not load admin workspaces:", error);
    }
  }

  async function loadPricingConfig() {
    pricingStatusBox.textContent = "Loading pricing configuration...";

    try {
      const response = await fetch(`/api/billing/pricing-config?t=${Date.now()}`, { cache: "no-store" });
      const data = await response.json();

      if (!response.ok || !data.ok) throw new Error(data.message || data.error || "Could not load pricing config");

      pricingConfig = data;

      starterMonthlyPrice.value = planByKey("starter").monthlyPrice ?? 0;
      starterMonthlyCredits.value = planByKey("starter").monthlyCredits ?? "";

      proMonthlyPrice.value = planByKey("pro").monthlyPrice ?? 0;
      proMonthlyCredits.value = planByKey("pro").monthlyCredits ?? "";

      businessMonthlyPrice.value = planByKey("business").monthlyPrice ?? 0;
      businessMonthlyCredits.value = planByKey("business").monthlyCredits ?? "";

      enterpriseMonthlyPrice.value = planByKey("enterprise").monthlyPrice ?? 0;
      enterpriseMonthlyCredits.value = planByKey("enterprise").monthlyCredits ?? "";

      voiceParameterCredits.value = creditRule("voice.parameter.saved").creditsPerUnit ?? 25;
      narrationCreditsPerSecond.value = creditRule("narration.generated").creditsPerUnit ?? 1;

      voiceProviderFixedCost.value = costRule("voice.parameter.saved").fixedCost ?? 0;
      narrationProviderCostPerSecond.value = costRule("narration.generated").costPerUnit ?? 0;

      pricingStatusBox.innerHTML = `
        <strong>Pricing loaded.</strong><br>
        Config: ${escapeHtml(data.configPath || "billing/pricing_config.json")}
      `;

      renderPlanSelectOptions();
    } catch (error) {
      pricingStatusBox.textContent = error.message || String(error);
    }
  }

  function buildPricingPayload() {
    return {
      currency: pricingConfig?.currency || "EUR",
      plans: [
        {
          key: "starter",
          label: "Starter",
          monthlyPrice: Number(starterMonthlyPrice.value || 0),
          monthlyCredits: Number(starterMonthlyCredits.value || 0),
          description: "Small team / early usage plan.",
        },
        {
          key: "pro",
          label: "Pro",
          monthlyPrice: Number(proMonthlyPrice.value || 0),
          monthlyCredits: Number(proMonthlyCredits.value || 0),
          description: "Regular narration and voice generation.",
        },
        {
          key: "business",
          label: "Business",
          monthlyPrice: Number(businessMonthlyPrice.value || 0),
          monthlyCredits: Number(businessMonthlyCredits.value || 0),
          description: "Higher usage with multiple workspaces and users.",
        },
        {
          key: "enterprise",
          label: "Enterprise",
          monthlyPrice: Number(enterpriseMonthlyPrice.value || 0),
          monthlyCredits: enterpriseMonthlyCredits.value.trim() ? Number(enterpriseMonthlyCredits.value) : null,
          description: "Contract pricing, limits, and governance.",
        },
      ],
      creditRules: [
        {
          eventType: "voice.parameter.saved",
          unit: "event",
          creditsPerUnit: Number(voiceParameterCredits.value || 0),
          minimumCredits: Number(voiceParameterCredits.value || 0),
          description: "Creating or replacing a saved voice parameter.",
        },
        {
          eventType: "narration.generated",
          unit: "second",
          creditsPerUnit: Number(narrationCreditsPerSecond.value || 0),
          minimumCredits: 1,
          description: "Final narration audio generation, charged by generated audio second.",
        },
      ],
      providerCostRules: [
        {
          eventType: "voice.parameter.saved",
          unit: "event",
          fixedCost: Number(voiceProviderFixedCost.value || 0),
          costPerUnit: 0,
          description: "Internal estimated provider cost for creating/replacing a voice parameter and preview.",
        },
        {
          eventType: "narration.generated",
          unit: "second",
          fixedCost: 0,
          costPerUnit: Number(narrationProviderCostPerSecond.value || 0),
          description: "Internal estimated provider cost per generated narration second.",
        },
      ],
    };
  }

  async function savePricingConfig() {
    savePricingConfigBtn.disabled = true;
    savePricingConfigBtn.textContent = "Saving...";
    pricingStatusBox.textContent = "Saving pricing configuration...";

    try {
      const response = await fetch("/api/billing/pricing-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPricingPayload())
      });

      const data = await response.json();

      if (!response.ok || !data.ok) throw new Error(data.message || data.error || "Could not save pricing config");

      pricingConfig = data;

      pricingStatusBox.innerHTML = `
        <strong>Pricing saved.</strong><br>
        Customer credit rules and internal provider cost assumptions are now updated.
      `;

      renderPlanSelectOptions();
      await loadBillingPlans();
      await loadBillingUsage();
    } catch (error) {
      pricingStatusBox.textContent = error.message || String(error);
    } finally {
      savePricingConfigBtn.disabled = false;
      savePricingConfigBtn.textContent = "Save pricing & costs";
    }
  }

  function renderPlanSelectOptions() {
    const plans = pricingConfig?.plans || billingPlans || [];

    if (!plans.length) return;

    const current = billingPlanSelect.value || "starter";

    billingPlanSelect.innerHTML = plans.map((plan) => `
      <option value="${escapeHtml(plan.key)}">
        ${escapeHtml(plan.label)} (${plan.monthlyCredits === null ? "Unlimited" : `${plan.monthlyCredits} credits`})
      </option>
    `).join("");

    billingPlanSelect.value = current;
  }

  async function loadBillingPlans() {
    try {
      const response = await fetch(`/api/billing/plans?t=${Date.now()}`, { cache: "no-store" });
      const data = await response.json();

      if (!response.ok || !data.ok) throw new Error(data.message || data.error || "Could not load billing plans");

      billingPlans = data.plans || [];
      renderPlanSelectOptions();
    } catch (error) {
      billingStatusBox.textContent = error.message || String(error);
    }
  }

  async function loadBillingUsage() {
    const workspaceId = billingWorkspaceSelect.value || "mock_user_001";
    billingStatusBox.textContent = "Loading billing usage...";
    billingUsageBreakdown.textContent = "Loading usage breakdown...";

    try {
      const [subscriptionResponse, economicsResponse] = await Promise.all([
        fetch(`/api/billing/subscription?workspaceId=${encodeURIComponent(workspaceId)}&t=${Date.now()}`, { cache: "no-store" }),
        fetch(`/api/billing/economics?workspaceId=${encodeURIComponent(workspaceId)}&t=${Date.now()}`, { cache: "no-store" }),
      ]);

      const data = await subscriptionResponse.json();
      const economics = await economicsResponse.json();

      if (!subscriptionResponse.ok || !data.ok) throw new Error(data.message || data.error || "Could not load billing usage");
      if (!economicsResponse.ok || !economics.ok) throw new Error(economics.message || economics.error || "Could not load economics");

      renderBillingUsage(data, economics);
    } catch (error) {
      billingStatusBox.textContent = error.message || String(error);
      billingUsageBreakdown.textContent = "Usage could not be loaded.";
    }
  }

  function renderBillingUsage(data, economics) {
    const plan = data.plan || data.subscription?.plan || {};
    const subscription = data.subscription || {};
    const usageRows = data.byEventType || [];
    const currency = economics.currency || pricingConfig?.currency || "EUR";

    billingCurrentPlan.textContent = plan.label || subscription.planKey || "—";
    billingMonthlyLimit.textContent = formatCredits(data.monthlyCreditLimit);
    billingUsedCredits.textContent = formatCredits(data.totalCredits);
    billingRemainingCredits.textContent = formatCredits(data.remainingCredits);

    billingMonthlyRevenue.textContent = money(economics.monthlyRevenue, currency);
    billingEstimatedCost.textContent = money(economics.estimatedProviderCost, currency);
    billingGrossMargin.textContent = money(economics.estimatedGrossMargin, currency);
    billingMarginPercent.textContent = economics.estimatedGrossMarginPercent === null
      ? "—"
      : `${economics.estimatedGrossMarginPercent}%`;

    billingPlanSelect.value = subscription.planKey || plan.key || "starter";

    billingStatusBox.innerHTML = `
      <strong>${escapeHtml(data.quotaState || "ok").toUpperCase()}</strong><br>
      Workspace: ${escapeHtml(data.workspaceId)}<br>
      Month: ${escapeHtml(data.month)}<br>
      Subscription status: ${escapeHtml(subscription.status || "active")}<br>
      Provider: ${escapeHtml(subscription.provider || "manual")}
    `;

    if (!usageRows.length) {
      billingUsageBreakdown.innerHTML = `<p class="status">No usage events recorded for this workspace/month yet.</p>`;
      return;
    }

    const costByEvent = economics.byEventType || [];

    billingUsageBreakdown.innerHTML = usageRows.map((row) => {
      const costRow = costByEvent.find((item) => item.eventType === row.eventType) || {};
      return `
        <div class="usage-row">
          <strong>${escapeHtml(row.eventType)}</strong>
          <span>${escapeHtml(row.count)} events</span>
          <span>${escapeHtml(row.credits)} credits</span>
          <span>${escapeHtml(money(costRow.estimatedProviderCost || 0, currency))}</span>
        </div>
      `;
    }).join("");
  }

  async function openStripeCheckout() {
    const workspaceId = billingWorkspaceSelect.value || "mock_user_001";
    const planKey = billingPlanSelect.value || "starter";

    openStripeCheckoutBtn.disabled = true;
    openStripeCheckoutBtn.textContent = "Opening Stripe...";
    billingStatusBox.textContent = "Creating Stripe Checkout Session...";

    try {
      const response = await fetch("/api/billing/checkout/stripe", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          workspaceId,
          planKey
        })
      });

      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not create Stripe Checkout Session");
      }

      billingStatusBox.innerHTML = `
        <strong>Stripe Checkout Session created.</strong><br>
        Workspace: ${escapeHtml(data.workspaceId)}<br>
        Plan: ${escapeHtml(data.planLabel || data.planKey)}<br>
        Price: ${escapeHtml(data.currency)} ${escapeHtml(Number(data.monthlyPrice || 0).toFixed(2))}/month
      `;

      if (data.checkoutUrl) {
        window.open(data.checkoutUrl, "_blank", "noopener,noreferrer");
      }
    } catch (error) {
      billingStatusBox.innerHTML = `
        <strong>Stripe Checkout unavailable.</strong><br>
        ${escapeHtml(error.message || String(error))}
      `;
    } finally {
      openStripeCheckoutBtn.disabled = false;
      openStripeCheckoutBtn.textContent = "Open Stripe Checkout";
    }
  }

  async function saveBillingPlan() {
    const workspaceId = billingWorkspaceSelect.value || "mock_user_001";
    const planKey = billingPlanSelect.value || "starter";

    saveBillingPlanBtn.disabled = true;
    saveBillingPlanBtn.textContent = "Saving...";
    billingStatusBox.textContent = "Saving subscription plan...";

    try {
      const response = await fetch("/api/billing/subscription", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspaceId, planKey, status: "active", provider: "manual" })
      });

      const data = await response.json();

      if (!response.ok || !data.ok) throw new Error(data.message || data.error || "Could not save plan");

      await loadBillingUsage();
    } catch (error) {
      billingStatusBox.textContent = error.message || String(error);
    } finally {
      saveBillingPlanBtn.disabled = false;
      saveBillingPlanBtn.textContent = "Save plan";
    }
  }

  billingWorkspaceSelect.addEventListener("change", loadBillingUsage);
  refreshBillingBtn.addEventListener("click", loadBillingUsage);
  saveBillingPlanBtn.addEventListener("click", saveBillingPlan);
  openStripeCheckoutBtn.addEventListener("click", openStripeCheckout);
  savePricingConfigBtn.addEventListener("click", savePricingConfig);

  loadAdminWorkspaces()
    .then(loadPricingConfig)
    .then(loadBillingPlans)
    .then(loadBillingUsage);
})();
