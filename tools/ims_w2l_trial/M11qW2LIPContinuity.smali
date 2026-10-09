.class public final Lcom/sec/internal/ims/core/M11qW2LIPContinuity;
.super Ljava/lang/Object;
.source "M11qW2LIPContinuity.java"


# static fields
.field private static final KEY:Ljava/lang/String; = "m11q_active_call_w2l_handover_bool"

.field private static final NETWORK_TYPE_IMS:I = 0xb


# direct methods
.method private constructor <init>()V
    .locals 0

    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    return-void
.end method

.method private static hasAllRetained(Ljava/util/List;Ljava/util/List;)Z
    .locals 1

    if-eqz p0, :cond_fail

    if-eqz p1, :cond_fail

    invoke-interface {p0}, Ljava/util/List;->isEmpty()Z

    move-result v0

    if-nez v0, :cond_fail

    invoke-interface {p1}, Ljava/util/List;->isEmpty()Z

    move-result v0

    if-nez v0, :cond_fail

    invoke-interface {p1, p0}, Ljava/util/List;->containsAll(Ljava/util/Collection;)Z

    move-result v0

    return v0

    :cond_fail
    const/4 v0, 0x0

    return v0
.end method

.method private static hasOrdinaryActiveVoice(I)Z
    .locals 3

    invoke-static {}, Lcom/sec/internal/ims/registry/ImsRegistry;->getServiceModuleManager()Lcom/sec/internal/interfaces/ims/servicemodules/IServiceModuleManager;

    move-result-object v0

    if-eqz v0, :cond_fail

    invoke-interface {v0}, Lcom/sec/internal/interfaces/ims/servicemodules/IServiceModuleManager;->getVolteServiceModule()Lcom/sec/internal/interfaces/ims/servicemodules/volte2/IVolteServiceModule;

    move-result-object v0

    if-eqz v0, :cond_fail

    invoke-interface {v0, p0}, Lcom/sec/internal/interfaces/ims/servicemodules/volte2/IVolteServiceModule;->hasActiveCall(I)Z

    move-result v1

    if-eqz v1, :cond_fail

    invoke-interface {v0, p0}, Lcom/sec/internal/interfaces/ims/servicemodules/volte2/IVolteServiceModule;->getTotalCallCount(I)I

    move-result v1

    const/4 v2, 0x1

    if-ne v1, v2, :cond_fail

    invoke-interface {v0, p0}, Lcom/sec/internal/interfaces/ims/servicemodules/volte2/IVolteServiceModule;->getVideoCallCount(I)I

    move-result v1

    if-nez v1, :cond_fail

    invoke-interface {v0, p0}, Lcom/sec/internal/interfaces/ims/servicemodules/volte2/IVolteServiceModule;->getDowngradedCallCount(I)I

    move-result v1

    if-nez v1, :cond_fail

    invoke-interface {v0, p0}, Lcom/sec/internal/interfaces/ims/servicemodules/volte2/IVolteServiceModule;->getE911CallCount(I)I

    move-result v1

    if-nez v1, :cond_fail

    invoke-interface {v0}, Lcom/sec/internal/interfaces/ims/servicemodules/volte2/IVolteServiceModule;->getForegroundSession()Lcom/sec/ims/volte2/IImsCallSession;

    move-result-object v0

    if-eqz v0, :cond_fail

    invoke-interface {v0}, Lcom/sec/ims/volte2/IImsCallSession;->getPhoneId()I

    move-result v1

    if-ne v1, p0, :cond_fail

    invoke-interface {v0}, Lcom/sec/ims/volte2/IImsCallSession;->getCallStateOrdinal()I

    move-result v0

    sget-object v1, Lcom/sec/internal/constants/ims/servicemodules/volte2/CallConstants$STATE;->InCall:Lcom/sec/internal/constants/ims/servicemodules/volte2/CallConstants$STATE;

    invoke-virtual {v1}, Ljava/lang/Enum;->ordinal()I

    move-result v1

    if-ne v0, v1, :cond_fail

    return v2

    :cond_fail
    const/4 v0, 0x0

    return v0
.end method

.method private static logReject(Ljava/lang/String;)V
    .locals 1

    const-string v0, "M11Q_W2L_IP"

    invoke-static {v0, p0}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    return-void
.end method

.method private static hasTrialOptIn(Landroid/content/Context;II)Z
    .locals 4

    if-eqz p0, :cond_fail

    if-ltz p1, :cond_fail

    if-ltz p2, :cond_fail

    invoke-static {p2}, Landroid/telephony/SubscriptionManager;->getSlotIndex(I)I

    move-result v0

    if-ne v0, p1, :cond_fail

    const-string v0, "carrier_config"

    invoke-virtual {p0, v0}, Landroid/content/Context;->getSystemService(Ljava/lang/String;)Ljava/lang/Object;

    move-result-object v0

    check-cast v0, Landroid/telephony/CarrierConfigManager;

    if-eqz v0, :cond_fail

    invoke-virtual {v0, p2}, Landroid/telephony/CarrierConfigManager;->getConfigForSubId(I)Landroid/os/PersistableBundle;

    move-result-object v0

    if-eqz v0, :cond_fail

    invoke-static {v0}, Landroid/telephony/CarrierConfigManager;->isConfigForIdentifiedCarrier(Landroid/os/PersistableBundle;)Z

    move-result v1

    if-eqz v1, :cond_fail

    const-string v1, "m11q_active_call_w2l_handover_bool"

    const/4 v2, 0x0

    invoke-virtual {v0, v1, v2}, Landroid/os/PersistableBundle;->getBoolean(Ljava/lang/String;Z)Z

    move-result v0

    if-eqz v0, :cond_fail

    const-string v0, "phone"

    invoke-virtual {p0, v0}, Landroid/content/Context;->getSystemService(Ljava/lang/String;)Ljava/lang/Object;

    move-result-object v0

    check-cast v0, Landroid/telephony/TelephonyManager;

    if-eqz v0, :cond_fail

    invoke-virtual {v0, p2}, Landroid/telephony/TelephonyManager;->createForSubscriptionId(I)Landroid/telephony/TelephonyManager;

    move-result-object v0

    if-eqz v0, :cond_fail

    invoke-virtual {v0}, Landroid/telephony/TelephonyManager;->getSimOperator()Ljava/lang/String;

    move-result-object v0

    const-string v1, "46697"

    invoke-virtual {v1, v0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v0

    return v0

    :cond_fail
    const/4 v0, 0x0

    return v0
.end method

.method private static isW2LInterfaceChange(Ljava/lang/String;Ljava/lang/String;)Z
    .locals 2

    if-eqz p0, :cond_fail

    if-eqz p1, :cond_fail

    invoke-virtual {p0, p1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v0

    if-nez v0, :cond_fail

    const-string v0, "epdg_data[0-9]+"

    invoke-virtual {p0, v0}, Ljava/lang/String;->matches(Ljava/lang/String;)Z

    move-result v1

    if-eqz v1, :cond_fail

    const-string v0, "rmnet_data[0-9]+"

    invoke-virtual {p1, v0}, Ljava/lang/String;->matches(Ljava/lang/String;)Z

    move-result v0

    return v0

    :cond_fail
    const/4 v0, 0x0

    return v0
.end method

.method public static shouldClassifyAsStacked(Lcom/sec/internal/ims/core/PdnController$NetworkCallback;Lcom/sec/internal/helper/os/LinkPropertiesWrapper;)Z
    .locals 8

    if-eqz p0, :cond_fail

    if-eqz p1, :cond_fail

    const/4 v7, 0x0

    :try_start_0
    iget v0, p0, Lcom/sec/internal/ims/core/PdnController$NetworkCallback;->mNetworkType:I

    const/16 v1, 0xb

    if-ne v0, v1, :cond_fail

    iget v0, p0, Lcom/sec/internal/ims/core/PdnController$NetworkCallback;->mPhoneId:I

    if-ltz v0, :cond_fail

    iget-object v3, p0, Lcom/sec/internal/ims/core/PdnController$NetworkCallback;->mLinkProperties:Lcom/sec/internal/helper/os/LinkPropertiesWrapper;

    if-eqz v3, :cond_fail

    invoke-virtual {v3}, Lcom/sec/internal/helper/os/LinkPropertiesWrapper;->getInterfaceName()Ljava/lang/String;

    move-result-object v4

    invoke-virtual {p1}, Lcom/sec/internal/helper/os/LinkPropertiesWrapper;->getInterfaceName()Ljava/lang/String;

    move-result-object v5

    invoke-static {v4, v5}, Lcom/sec/internal/ims/core/M11qW2LIPContinuity;->isW2LInterfaceChange(Ljava/lang/String;Ljava/lang/String;)Z

    move-result v4

    if-eqz v4, :cond_fail

    const/4 v7, 0x1

    invoke-static {}, Lcom/sec/internal/ims/registry/ImsRegistry;->getContext()Landroid/content/Context;

    move-result-object v1

    invoke-static {v0}, Lcom/sec/internal/helper/SimUtil;->getSubId(I)I

    move-result v2

    invoke-static {v1, v0, v2}, Lcom/sec/internal/ims/core/M11qW2LIPContinuity;->hasTrialOptIn(Landroid/content/Context;II)Z

    move-result v1

    if-eqz v1, :cond_reject_subscription

    invoke-static {v0}, Lcom/sec/internal/ims/core/M11qW2LIPContinuity;->hasOrdinaryActiveVoice(I)Z

    move-result v0

    if-eqz v0, :cond_reject_voice

    move-object v0, v3

    iget-object v1, p0, Lcom/sec/internal/ims/core/PdnController$NetworkCallback;->this$0:Lcom/sec/internal/ims/core/PdnController;

    invoke-virtual {v0}, Lcom/sec/internal/helper/os/LinkPropertiesWrapper;->getAddresses()Ljava/util/List;

    move-result-object v2

    invoke-virtual {v1, v2}, Lcom/sec/internal/ims/core/PdnController;->filterAddresses(Ljava/lang/Iterable;)Ljava/util/List;

    move-result-object v2

    invoke-virtual {p1}, Lcom/sec/internal/helper/os/LinkPropertiesWrapper;->getAddresses()Ljava/util/List;

    move-result-object v3

    invoke-virtual {v1, v3}, Lcom/sec/internal/ims/core/PdnController;->filterAddresses(Ljava/lang/Iterable;)Ljava/util/List;

    move-result-object v3

    invoke-static {v2, v3}, Lcom/sec/internal/ims/core/M11qW2LIPContinuity;->hasAllRetained(Ljava/util/List;Ljava/util/List;)Z

    move-result v2

    if-eqz v2, :cond_reject_main

    invoke-virtual {v0}, Lcom/sec/internal/helper/os/LinkPropertiesWrapper;->getAllAddresses()Ljava/util/List;

    move-result-object v2

    invoke-virtual {v1, v2}, Lcom/sec/internal/ims/core/PdnController;->filterAddresses(Ljava/lang/Iterable;)Ljava/util/List;

    move-result-object v2

    invoke-virtual {p1}, Lcom/sec/internal/helper/os/LinkPropertiesWrapper;->getAllAddresses()Ljava/util/List;

    move-result-object v3

    invoke-virtual {v1, v3}, Lcom/sec/internal/ims/core/PdnController;->filterAddresses(Ljava/lang/Iterable;)Ljava/util/List;

    move-result-object v3

    invoke-static {v2, v3}, Lcom/sec/internal/ims/core/M11qW2LIPContinuity;->hasAllRetained(Ljava/util/List;Ljava/util/List;)Z

    move-result v2

    if-eqz v2, :cond_reject_all

    invoke-virtual {v0}, Lcom/sec/internal/helper/os/LinkPropertiesWrapper;->getPcscfServers()Ljava/util/List;

    move-result-object v2

    invoke-virtual {v1, v2}, Lcom/sec/internal/ims/core/PdnController;->filterAddresses(Ljava/lang/Iterable;)Ljava/util/List;

    move-result-object v2

    invoke-virtual {p1}, Lcom/sec/internal/helper/os/LinkPropertiesWrapper;->getPcscfServers()Ljava/util/List;

    move-result-object v3

    invoke-virtual {v1, v3}, Lcom/sec/internal/ims/core/PdnController;->filterAddresses(Ljava/lang/Iterable;)Ljava/util/List;

    move-result-object v3

    invoke-static {v2, v3}, Lcom/sec/internal/ims/core/M11qW2LIPContinuity;->hasAllRetained(Ljava/util/List;Ljava/util/List;)Z

    move-result v2

    if-eqz v2, :cond_reject_pcscf

    const-string v2, "M11Q_W2L_IP"

    const-string v3, "classify-stacked:retained"

    invoke-static {v2, v3}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    :try_end_0
    const/4 v0, 0x1

    return v0

    :cond_reject_subscription
    const-string v0, "reject:subscription-config"

    invoke-static {v0}, Lcom/sec/internal/ims/core/M11qW2LIPContinuity;->logReject(Ljava/lang/String;)V

    goto :cond_fail

    :cond_reject_voice
    const-string v0, "reject:ordinary-connected"

    invoke-static {v0}, Lcom/sec/internal/ims/core/M11qW2LIPContinuity;->logReject(Ljava/lang/String;)V

    goto :cond_fail

    :cond_reject_main
    const-string v0, "reject:retained-main"

    invoke-static {v0}, Lcom/sec/internal/ims/core/M11qW2LIPContinuity;->logReject(Ljava/lang/String;)V

    goto :cond_fail

    :cond_reject_all
    const-string v0, "reject:retained-all"

    invoke-static {v0}, Lcom/sec/internal/ims/core/M11qW2LIPContinuity;->logReject(Ljava/lang/String;)V

    goto :cond_fail

    :cond_reject_pcscf
    const-string v0, "reject:retained-pcscf"

    invoke-static {v0}, Lcom/sec/internal/ims/core/M11qW2LIPContinuity;->logReject(Ljava/lang/String;)V

    goto :cond_fail

    :catch_0
    move-exception v0

    if-eqz v7, :cond_fail

    const-string v0, "reject:runtime-exception"

    invoke-static {v0}, Lcom/sec/internal/ims/core/M11qW2LIPContinuity;->logReject(Ljava/lang/String;)V

    :cond_fail
    const/4 v0, 0x0

    return v0

    .catch Ljava/lang/Exception; {:try_start_0 .. :try_end_0} :catch_0
.end method
