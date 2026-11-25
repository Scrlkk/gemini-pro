/*
 * Explicit read-only Google Play Billing ProductDetails query.
 * No checkout, purchase token, account switching, or subscription mutation.
 * Invoked on user request only; requires the pre-installed Android billing DEX.
 */
var SKU_REQUEST = [];
var skuClient = null;
var skuDexLoader = null;
var skuFinished = false;
function skuSend(data) { if (!skuFinished) send(data); }
function skuClose() {
  var client = skuClient;
  skuClient = null;
  if (client) {
    try { client.endConnection(); } catch (ignored) {}
  }
}
function skuFinish(code) {
  if (skuFinished) return;
  skuFinished = true;
  skuClose();
  send({ev:"done", code:code});
}
rpc.exports = {
  close: function () {
    Java.performNow(function () {
      skuFinished = true;
      skuClose();
    });
  }
};
function skuLoader(loader) { Java.classFactory.loader = loader; }
function skuBoot() {
  Java.perform(function () {
    if (skuFinished) return;
    try {
      skuLoader(null);
      var app = Java.use("android.app.ActivityThread").currentApplication();
      if (!app) { skuFinish("device_not_ready"); return; }
      var ctx = app.getApplicationContext();
      var Loader = Java.use("dalvik.system.DexClassLoader");
      skuDexLoader = Loader.$new("/data/local/tmp/module_521.apk",
        ctx.getCodeCacheDir().getAbsolutePath(), null, ctx.getClassLoader());
      skuLoader(skuDexLoader);
      var BillingClient = Java.use("com.android.billingclient.api.BillingClient");
      var UpdateListener = Java.use("com.android.billingclient.api.PurchasesUpdatedListener");
      var Listener = Java.registerClass({
        name: "sku.Listener" + Date.now(), implements: [UpdateListener],
        methods: {
          onPurchasesUpdated: function () {
            // Required by BillingClient builder, intentionally ignored.
          }
        }
      });
      var builder = BillingClient.newBuilder(ctx);
      builder.setListener(Listener.$new());
      try { builder.enablePendingPurchases(); } catch (ignored) {}
      skuClient = builder.build();
      var SetupListener = Java.use("com.android.billingclient.api.BillingClientStateListener");
      var Setup = Java.registerClass({
        name: "sku.Setup" + Date.now(), implements: [SetupListener],
        methods: {
          onBillingSetupFinished: function (r) {
            if (skuFinished) return;
            if (r.getResponseCode() !== 0) {
              skuFinish("billing_unavailable"); return;
            }
            skuQuery();
          },
          onBillingServiceDisconnected: function () {
            skuFinish("billing_unavailable");
          }
        }
      });
      skuClient.startConnection(Setup.$new());
    } catch (error) {
      skuFinish("query_error");
    }
  });
}
function skuQuery() {
  try {
    skuLoader(skuDexLoader);
    var Product = Java.use("com.android.billingclient.api.QueryProductDetailsParams$Product");
    var Params = Java.use("com.android.billingclient.api.QueryProductDetailsParams");
    var ResponseListener = Java.use("com.android.billingclient.api.ProductDetailsResponseListener");
    var QueryResponse = Java.registerClass({
      name: "sku.Response" + Date.now(), implements: [ResponseListener],
      methods: {
        onProductDetailsResponse: function (result, list) {
          if (skuFinished) return;
          try {
            if (result.getResponseCode() !== 0) {
              skuFinish("billing_unavailable"); return;
            }
            skuLoader(skuDexLoader);
            var PD = Java.use("com.android.billingclient.api.ProductDetails");
            var SOD = Java.use("com.android.billingclient.api.ProductDetails$SubscriptionOfferDetails");
            var Phase = Java.use("com.android.billingclient.api.ProductDetails$PricingPhase");
            for (var i = 0; list && i < list.size(); i++) {
              var pd = Java.cast(list.get(i), PD);
              var productId = String(pd.getProductId());
              var offers = pd.getSubscriptionOfferDetails();
              if (!offers || !offers.size()) {
                skuSend({ev:"offer", sku:productId, no_offers:true});
                continue;
              }
              for (var j = 0; j < offers.size(); j++) {
                var offer = Java.cast(offers.get(j), SOD);
                var phases = [];
                var pricingPhases = offer.getPricingPhases().getPricingPhaseList();
                for (var k = 0; pricingPhases && k < pricingPhases.size() && k < 12; k++) {
                  var ph = Java.cast(pricingPhases.get(k), Phase);
                  phases.push({
                    price_amount_micros: String(ph.getPriceAmountMicros()),
                    currency: String(ph.getPriceCurrencyCode()),
                    billing_period: String(ph.getBillingPeriod()),
                    billing_cycle_count: Number(ph.getBillingCycleCount()),
                    recurrence_mode: Number(ph.getRecurrenceMode())
                  });
                }
                skuSend({
                  ev:"offer",
                  sku: productId,
                  base_plan_id: String(offer.getBasePlanId()),
                  offer_id: String(offer.getOfferId() || ""),
                  phases: phases
                });
              }
            }
            skuFinish("ok");
          } catch (error) {
            skuFinish("query_error");
          } finally {
            skuClose();
          }
        }
      }
    });
    var request = Java.use("java.util.ArrayList").$new();
    for (var n = 0; n < SKU_REQUEST.length && n < 10; n++) {
      request.add(Product.newBuilder()
        .setProductId(String(SKU_REQUEST[n])).setProductType("subs").build());
    }
    skuClient.queryProductDetailsAsync(
      Params.newBuilder().setProductList(request).build(), QueryResponse.$new());
  } catch (error) {
    skuFinish("query_error");
    skuClose();
  }
}
skuBoot();
