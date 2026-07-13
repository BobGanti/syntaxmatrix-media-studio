(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const workspace = $("#billingWorkspaceSelect"), planSelect = $("#billingPlanSelect");
  const statusBox = $("#billingStatusBox"), usageBox = $("#billingUsageBreakdown"), pricingStatus = $("#pricingStatusBox");
  const savePlan = $("#saveBillingPlanBtn"), refresh = $("#refreshBillingBtn"), savePricing = $("#savePricingConfigBtn");
  let config = null;

  const esc = (v) => String(v ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");
  const num = (id) => Number($(id)?.value || 0);
  const nullable = (id) => $(id)?.value.trim() === "" ? null : Number($(id).value);
  const plan = (key) => (config?.plans || []).find((p) => p.key === key) || {};
  const money = (v, c) => `${c} ${Number(v || 0).toFixed(2)}`;
  const credits = (v) => v == null ? "Unlimited" : Number(v || 0).toLocaleString();

  async function loadWorkspaces() {
    const r = await fetch(`/api/admin/workspaces?t=${Date.now()}`, {cache:"no-store"});
    const d = await r.json();
    if (!r.ok || !d.ok) throw new Error(d.message || d.error || "Could not load workspaces");
    workspace.innerHTML = (d.workspaces || []).map((w) => `<option value="${esc(w.workspaceId)}">${esc(w.label || w.workspaceId)}</option>`).join("");
  }

  function renderPlanOptions() {
    const current = planSelect.value;
    planSelect.innerHTML = (config?.plans || []).map((p) => `<option value="${esc(p.key)}">${esc(p.label)} — ${p.creditPeriod === "weekly" ? `${credits(p.weeklyCredits)} weekly` : `${credits(p.monthlyCredits)} monthly`} credits</option>`).join("");
    if ([...planSelect.options].some((o) => o.value === current)) planSelect.value = current;
  }

  async function loadConfig() {
    pricingStatus.textContent = "Loading pricing configuration...";
    const r = await fetch(`/api/billing/pricing-config?t=${Date.now()}`, {cache:"no-store"});
    const d = await r.json();
    if (!r.ok || !d.ok) throw new Error(d.message || d.error || "Could not load pricing configuration");
    config = d;
    $("#voiceCloneCostUsd").value = d.metering.voiceCloneCostUsd;
    $("#ttsCostPer10000CharactersUsd").value = d.metering.ttsCostPer10000CharactersUsd;
    $("#retailMarkupPercent").value = d.metering.retailMarkupPercent;
    $("#retailValuePerCreditUsd").value = d.metering.retailValuePerCreditUsd;
    $("#freeWeeklyCredits").value = d.freePlan.weeklyCredits;
    $("#freeResetWeekday").value = d.freePlan.resetWeekday;
    $("#freeResetHourUtc").value = d.freePlan.resetHourUtc;
    for (const key of ["starter","pro","business","enterprise"]) {
      const p = plan(key);
      $(`#${key}MonthlyPrice`).value = p.monthlyPrice ?? 0;
      $(`#${key}MonthlyCredits`).value = p.monthlyCredits ?? "";
      $(`#${key}CloneSlots`).value = p.cloneSlots ?? "";
    }
    renderPlanOptions();
    pricingStatus.innerHTML = `<strong>Pricing loaded.</strong><br>Source: ${esc(d.configPath)}<br>Durable production storage: ${d.durable ? "GCS" : "local development file"}`;
  }

  function payload() {
    const existing = Object.fromEntries((config?.plans || []).map((p) => [p.key,p]));
    const paid = (key) => ({...existing[key],key,label:existing[key]?.label || key[0].toUpperCase()+key.slice(1),monthlyPrice:num(`#${key}MonthlyPrice`),monthlyCredits:nullable(`#${key}MonthlyCredits`),cloneSlots:nullable(`#${key}CloneSlots`),creditPeriod:"monthly",weeklyCredits:null,systemVoicesOnly:false,enabled:true});
    return {
      currency: config?.currency || "EUR",
      supplierCurrency: "USD",
      metering: {voiceCloneCostUsd:num("#voiceCloneCostUsd"),ttsCostPer10000CharactersUsd:num("#ttsCostPer10000CharactersUsd"),retailMarkupPercent:num("#retailMarkupPercent"),retailValuePerCreditUsd:num("#retailValuePerCreditUsd")},
      freePlan: {weeklyCredits:num("#freeWeeklyCredits"),resetWeekday:num("#freeResetWeekday"),resetHourUtc:num("#freeResetHourUtc"),rollover:false},
      plans: [{...existing.free,key:"free",label:"Free",monthlyPrice:0,monthlyCredits:num("#freeWeeklyCredits"),weeklyCredits:num("#freeWeeklyCredits"),creditPeriod:"weekly",cloneSlots:0,systemVoicesOnly:true,enabled:true},paid("starter"),paid("pro"),paid("business"),paid("enterprise")]
    };
  }

  async function saveConfig() {
    savePricing.disabled = true; pricingStatus.textContent = "Saving...";
    try {
      const r = await fetch("/api/billing/pricing-config", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload())});
      const d = await r.json();
      if (!r.ok || !d.ok) throw new Error(d.message || d.error || "Could not save pricing configuration");
      config = d; renderPlanOptions(); pricingStatus.innerHTML = `<strong>Saved.</strong> Future operations now use the new supplier rates, markup, credit value, and plan defaults.`;
      await loadUsage();
    } catch (e) { pricingStatus.textContent = e.message || String(e); }
    finally { savePricing.disabled = false; }
  }

  async function loadUsage() {
    if (!workspace.value) return;
    statusBox.textContent = "Loading billing usage...";
    const id = encodeURIComponent(workspace.value);
    const [sr,er] = await Promise.all([fetch(`/api/billing/subscription?workspaceId=${id}&t=${Date.now()}`,{cache:"no-store"}),fetch(`/api/billing/economics?workspaceId=${id}&t=${Date.now()}`,{cache:"no-store"})]);
    const s = await sr.json(), e = await er.json();
    if (!sr.ok || !s.ok) throw new Error(s.message || s.error || "Could not load subscription");
    if (!er.ok || !e.ok) throw new Error(e.message || e.error || "Could not load economics");
    $("#billingCurrentPlan").textContent = s.plan?.label || s.subscription?.planKey || "—";
    $("#billingMonthlyLimit").textContent = credits(s.creditLimit ?? s.monthlyCreditLimit);
    $("#billingUsedCredits").textContent = credits(s.totalCredits);
    $("#billingRemainingCredits").textContent = credits(s.remainingCredits);
    $("#billingMonthlyRevenue").textContent = money(e.monthlyRevenue,e.planCurrency || "EUR");
    $("#billingEstimatedCost").textContent = money(e.estimatedProviderCostUsd,"USD");
    $("#billingRetailUsage").textContent = money(e.estimatedRetailUsageUsd,"USD");
    $("#billingCreditPeriod").textContent = s.creditPeriod || "monthly";
    planSelect.value = s.subscription?.planKey || "free";
    statusBox.innerHTML = `<strong>${esc(String(s.quotaState || "ok").toUpperCase())}</strong><br>Workspace: ${esc(s.workspaceId)}<br>Period: ${esc(s.periodStart)} to ${esc(s.periodEnd)}<br>Subscription: ${esc(s.subscription?.status)} / ${esc(s.subscription?.provider)}`;
    const costs = e.byEventType || [];
    usageBox.innerHTML = (s.byEventType || []).length ? s.byEventType.map((row) => { const c = costs.find((x) => x.eventType === row.eventType) || {}; return `<div class="usage-row"><strong>${esc(row.eventType)}</strong><span>${esc(row.count)} events</span><span>${esc(row.credits)} credits</span><span>USD ${Number(c.estimatedProviderCost || 0).toFixed(6)}</span></div>`; }).join("") : `<p class="status">No usage in the current credit period.</p>`;
  }

  async function saveManualPlan() {
    savePlan.disabled = true;
    try {
      const r = await fetch("/api/billing/subscription", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({workspaceId:workspace.value,planKey:planSelect.value,status:"active",provider:planSelect.value === "free" ? "internal" : "manual"})});
      const d = await r.json();
      if (!r.ok || !d.ok) throw new Error(d.message || d.error || "Could not save plan");
      await loadUsage();
    } catch (e) { statusBox.textContent = e.message || String(e); }
    finally { savePlan.disabled = false; }
  }

  workspace.addEventListener("change", loadUsage); refresh.addEventListener("click", loadUsage); savePlan.addEventListener("click", saveManualPlan); savePricing.addEventListener("click", saveConfig);
  loadWorkspaces().then(loadConfig).then(loadUsage).catch((e) => { statusBox.textContent = e.message || String(e); pricingStatus.textContent = e.message || String(e); });
})();
