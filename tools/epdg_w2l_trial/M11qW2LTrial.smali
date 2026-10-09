.class public final Lcom/sec/epdg/M11qW2LTrial;
.super Ljava/lang/Object;
.source "M11qW2LTrial-r2.java"


# static fields
.field private static final KEY:Ljava/lang/String; = "m11q_active_call_w2l_handover_bool"

.field private static final MARK:Ljava/lang/String; = "M11Q_W2L_TRIAL"

.field private static final LOCK:Ljava/lang/Object;

.field private static final active:[Z

.field private static final attached:[Z

.field private static final cid:[I

.field private static final deferred:[Z

.field private static final generation:[I

.field private static final shutdownPending:[Z

.field private static serial:I

.field private static final subscriptions:[Lcom/sec/epdg/EpdgSubScription;

.field private static final stateMachines:[Lcom/sec/epdg/IPSecDataConnSM;


# direct methods
.method static constructor <clinit>()V
    .locals 2

    new-instance v0, Ljava/lang/Object;

    invoke-direct {v0}, Ljava/lang/Object;-><init>()V

    sput-object v0, Lcom/sec/epdg/M11qW2LTrial;->LOCK:Ljava/lang/Object;

    const/4 v0, 0x4

    new-array v1, v0, [Z

    sput-object v1, Lcom/sec/epdg/M11qW2LTrial;->active:[Z

    new-array v1, v0, [Z

    sput-object v1, Lcom/sec/epdg/M11qW2LTrial;->attached:[Z

    new-array v1, v0, [Z

    sput-object v1, Lcom/sec/epdg/M11qW2LTrial;->deferred:[Z

    new-array v1, v0, [Z

    sput-object v1, Lcom/sec/epdg/M11qW2LTrial;->shutdownPending:[Z

    new-array v1, v0, [I

    sput-object v1, Lcom/sec/epdg/M11qW2LTrial;->cid:[I

    new-array v1, v0, [I

    sput-object v1, Lcom/sec/epdg/M11qW2LTrial;->generation:[I

    new-array v0, v0, [Lcom/sec/epdg/EpdgSubScription;

    sput-object v0, Lcom/sec/epdg/M11qW2LTrial;->subscriptions:[Lcom/sec/epdg/EpdgSubScription;

    const/4 v0, 0x4

    new-array v0, v0, [Lcom/sec/epdg/IPSecDataConnSM;

    sput-object v0, Lcom/sec/epdg/M11qW2LTrial;->stateMachines:[Lcom/sec/epdg/IPSecDataConnSM;

    return-void
.end method

.method private constructor <init>()V
    .locals 0

    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    return-void
.end method

.method private static eligible(Landroid/content/Context;Lcom/sec/epdg/EpdgSubScription;II)Z
    .locals 5

    if-eqz p0, :cond_fail

    if-eqz p1, :cond_fail

    if-ltz p2, :cond_fail

    const/4 v0, 0x4

    if-ge p2, v0, :cond_fail

    if-ltz p3, :cond_fail

    :try_start_0

    invoke-static {p3}, Landroid/telephony/SubscriptionManager;->getSlotIndex(I)I

    move-result v0

    if-ne v0, p2, :cond_fail

    invoke-static {}, Lcom/sec/epdg/EpdgUtils;->isIwlanLegacyMode()Z

    move-result v0

    if-nez v0, :cond_fail

    const-string v0, "carrier_config"

    invoke-virtual {p0, v0}, Landroid/content/Context;->getSystemService(Ljava/lang/String;)Ljava/lang/Object;

    move-result-object v0

    check-cast v0, Landroid/telephony/CarrierConfigManager;

    if-eqz v0, :cond_fail

    invoke-virtual {v0, p3}, Landroid/telephony/CarrierConfigManager;->getConfigForSubId(I)Landroid/os/PersistableBundle;

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

    invoke-virtual {v0, p3}, Landroid/telephony/TelephonyManager;->createForSubscriptionId(I)Landroid/telephony/TelephonyManager;

    move-result-object v0

    invoke-virtual {v0}, Landroid/telephony/TelephonyManager;->getSimOperator()Ljava/lang/String;

    move-result-object v0

    const-string v1, "46697"

    invoke-virtual {v1, v0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v0

    if-eqz v0, :cond_fail

    invoke-virtual {p1}, Lcom/sec/epdg/EpdgSubScription;->getImsCallStatus()Lcom/sec/epdg/data/Constants/ImsConstants$EpdgCallStatus;

    move-result-object v0

    sget-object v1, Lcom/sec/epdg/data/Constants/ImsConstants$EpdgCallStatus;->CALL_VOICEONLY:Lcom/sec/epdg/data/Constants/ImsConstants$EpdgCallStatus;

    if-ne v0, v1, :cond_fail

    invoke-virtual {p1}, Lcom/sec/epdg/EpdgSubScription;->getIsImsCallConnected()Z

    move-result v0

    if-eqz v0, :cond_fail

    invoke-virtual {p1}, Lcom/sec/epdg/EpdgSubScription;->getImsManagerHelper()Lcom/sec/epdg/EpdgImsManagerHelper;

    move-result-object v0

    if-eqz v0, :cond_fail

    invoke-virtual {v0}, Lcom/sec/epdg/EpdgImsManagerHelper;->isImsEmergencyCall()Z

    move-result v0

    if-nez v0, :cond_fail

    const-string v0, "ims"

    invoke-virtual {p1, v0}, Lcom/sec/epdg/EpdgSubScription;->isPdnConnectedOverWifi(Ljava/lang/String;)Z

    move-result v0

    if-eqz v0, :cond_fail

    invoke-virtual {p1}, Lcom/sec/epdg/EpdgSubScription;->getNetworkChangeController()Lcom/sec/epdg/NetworkChangeController;

    move-result-object v0

    if-eqz v0, :cond_fail

    invoke-virtual {v0}, Lcom/sec/epdg/NetworkChangeController;->getIsCellularAvailable()Z

    move-result v1

    if-eqz v1, :cond_fail

    invoke-virtual {v0}, Lcom/sec/epdg/NetworkChangeController;->getMobileDataReg()I

    move-result v1

    if-nez v1, :cond_fail

    invoke-virtual {v0}, Lcom/sec/epdg/NetworkChangeController;->getDataRat()I

    move-result v1

    const/16 v3, 0xd

    if-ne v1, v3, :cond_fail

    invoke-static {p0, p2, p3}, Lcom/sec/epdg/M11qW2LTrial;->platformLteVops(Landroid/content/Context;II)Z

    move-result v0

    if-eqz v0, :cond_fail

    :try_end_0
    const/4 v0, 0x1

    return v0

    :catch_0
    move-exception v0

    :cond_fail
    const/4 v0, 0x0

    return v0

    .catch Ljava/lang/RuntimeException; {:try_start_0 .. :try_end_0} :catch_0
.end method

.method private static stillEligible(Lcom/sec/epdg/EpdgSubScription;I)Z
    .locals 4

    if-eqz p0, :cond_fail

    :try_start_0

    invoke-virtual {p0}, Lcom/sec/epdg/EpdgSubScription;->getImsCallStatus()Lcom/sec/epdg/data/Constants/ImsConstants$EpdgCallStatus;

    move-result-object v0

    sget-object v1, Lcom/sec/epdg/data/Constants/ImsConstants$EpdgCallStatus;->CALL_VOICEONLY:Lcom/sec/epdg/data/Constants/ImsConstants$EpdgCallStatus;

    if-ne v0, v1, :cond_fail

    invoke-virtual {p0}, Lcom/sec/epdg/EpdgSubScription;->getIsImsCallConnected()Z

    move-result v0

    if-eqz v0, :cond_fail

    invoke-virtual {p0}, Lcom/sec/epdg/EpdgSubScription;->getImsManagerHelper()Lcom/sec/epdg/EpdgImsManagerHelper;

    move-result-object v0

    if-eqz v0, :cond_fail

    invoke-virtual {v0}, Lcom/sec/epdg/EpdgImsManagerHelper;->isImsEmergencyCall()Z

    move-result v0

    if-nez v0, :cond_fail

    invoke-virtual {p0}, Lcom/sec/epdg/EpdgSubScription;->getNetworkChangeController()Lcom/sec/epdg/NetworkChangeController;

    move-result-object v0

    if-eqz v0, :cond_fail

    invoke-virtual {v0}, Lcom/sec/epdg/NetworkChangeController;->getIsCellularAvailable()Z

    move-result v1

    if-eqz v1, :cond_fail

    invoke-virtual {v0}, Lcom/sec/epdg/NetworkChangeController;->getMobileDataReg()I

    move-result v1

    if-nez v1, :cond_fail

    invoke-virtual {v0}, Lcom/sec/epdg/NetworkChangeController;->getDataRat()I

    move-result v1

    const/16 v2, 0xd

    if-ne v1, v2, :cond_fail

    invoke-virtual {p0}, Lcom/sec/epdg/EpdgSubScription;->getEpdgServiceContext()Landroid/content/Context;

    move-result-object v3

    invoke-static {p1}, Lcom/sec/epdg/EpdgUtils;->getInstance(I)Lcom/sec/epdg/EpdgUtils;

    move-result-object v0

    if-eqz v0, :cond_fail

    invoke-virtual {v0, p1}, Lcom/sec/epdg/EpdgUtils;->getSubId(I)I

    move-result v2

    invoke-static {v3, p1, v2}, Lcom/sec/epdg/M11qW2LTrial;->platformLteVops(Landroid/content/Context;II)Z

    move-result v0

    if-eqz v0, :cond_fail

    :try_end_0
    const/4 v0, 0x1

    return v0

    :catch_0
    move-exception v0

    :cond_fail
    const/4 v0, 0x0

    return v0

    .catch Ljava/lang/RuntimeException; {:try_start_0 .. :try_end_0} :catch_0
.end method

.method private static platformLteVops(Landroid/content/Context;II)Z
    .locals 4

    const-string v2, "reject:platform-subscription"

    if-eqz p0, :cond_fail

    if-ltz p2, :cond_fail

    :try_start_0
    invoke-static {p2}, Landroid/telephony/SubscriptionManager;->getSlotIndex(I)I

    move-result v0

    if-ne v0, p1, :cond_fail

    const-string v2, "reject:platform-service-unavailable"

    const-string v0, "phone"

    invoke-virtual {p0, v0}, Landroid/content/Context;->getSystemService(Ljava/lang/String;)Ljava/lang/Object;

    move-result-object v0

    check-cast v0, Landroid/telephony/TelephonyManager;

    if-eqz v0, :cond_fail

    invoke-virtual {v0, p2}, Landroid/telephony/TelephonyManager;->createForSubscriptionId(I)Landroid/telephony/TelephonyManager;

    move-result-object v0

    if-eqz v0, :cond_fail

    invoke-virtual {v0}, Landroid/telephony/TelephonyManager;->getServiceState()Landroid/telephony/ServiceState;

    move-result-object v0

    if-eqz v0, :cond_fail

    const/4 v1, 0x2

    const/4 v3, 0x1

    invoke-virtual {v0, v1, v3}, Landroid/telephony/ServiceState;->getNetworkRegistrationInfo(II)Landroid/telephony/NetworkRegistrationInfo;

    move-result-object v0

    const-string v2, "reject:wwan-ps-not-registered"

    if-eqz v0, :cond_fail

    invoke-virtual {v0}, Landroid/telephony/NetworkRegistrationInfo;->isRegistered()Z

    move-result v1

    if-eqz v1, :cond_fail

    const-string v2, "reject:wwan-emergency-only"

    invoke-virtual {v0}, Landroid/telephony/NetworkRegistrationInfo;->isEmergencyEnabled()Z

    move-result v1

    if-nez v1, :cond_fail

    const-string v2, "reject:wwan-ps-not-lte"

    invoke-virtual {v0}, Landroid/telephony/NetworkRegistrationInfo;->getAccessNetworkTechnology()I

    move-result v1

    const/16 v3, 0xd

    if-ne v1, v3, :cond_fail

    const-string v2, "reject:wwan-lte-vops-unsupported-or-unknown"

    invoke-virtual {v0}, Landroid/telephony/NetworkRegistrationInfo;->getDataSpecificInfo()Landroid/telephony/DataSpecificRegistrationInfo;

    move-result-object v0

    if-eqz v0, :cond_fail

    invoke-virtual {v0}, Landroid/telephony/DataSpecificRegistrationInfo;->getLteVopsSupportInfo()Landroid/telephony/LteVopsSupportInfo;

    move-result-object v0

    if-eqz v0, :cond_fail

    invoke-virtual {v0}, Landroid/telephony/LteVopsSupportInfo;->isVopsSupported()Z

    move-result v0

    if-eqz v0, :cond_fail

    :try_end_0
    const-string v2, "guard:android13-wwan-lte-vops-confirmed"

    invoke-static {p1, v2}, Lcom/sec/epdg/M11qW2LTrial;->logState(ILjava/lang/String;)V

    const/4 v0, 0x1

    return v0

    :catch_0
    move-exception v0

    const-string v2, "reject:platform-service-exception"

    :cond_fail
    invoke-static {p1, v2}, Lcom/sec/epdg/M11qW2LTrial;->logState(ILjava/lang/String;)V

    const/4 v0, 0x0

    return v0

    .catch Ljava/lang/RuntimeException; {:try_start_0 .. :try_end_0} :catch_0
.end method

.method private static log(Ljava/lang/String;)V
    .locals 1

    const-string v0, "M11Q_W2L_TRIAL"

    invoke-static {v0, p0}, Lcom/sec/epdg/data/Logger/Log;->i(Ljava/lang/String;Ljava/lang/String;)V

    return-void
.end method

.method private static logEvent(IIILjava/lang/String;)V
    .locals 2

    new-instance v0, Ljava/lang/StringBuilder;

    invoke-direct {v0}, Ljava/lang/StringBuilder;-><init>()V

    const-string v1, "phone="

    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v0, p0}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    const-string v1, " cid="

    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v0, p1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    const-string v1, " generation="

    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v0, p2}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    const-string v1, " event="

    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v0, p3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    invoke-static {v0}, Lcom/sec/epdg/M11qW2LTrial;->log(Ljava/lang/String;)V

    return-void
.end method

.method private static logState(ILjava/lang/String;)V
    .locals 4

    if-ltz p0, :cond_done

    const/4 v0, 0x4

    if-ge p0, v0, :cond_done

    sget-object v3, Lcom/sec/epdg/M11qW2LTrial;->LOCK:Ljava/lang/Object;

    monitor-enter v3

    :try_start_0
    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->cid:[I

    aget v1, v0, p0

    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->generation:[I

    aget v2, v0, p0

    monitor-exit v3
    :try_end_0

    invoke-static {p0, v1, v2, p1}, Lcom/sec/epdg/M11qW2LTrial;->logEvent(IIILjava/lang/String;)V

    :cond_done
    return-void

    :catchall_0
    move-exception v0

    monitor-exit v3

    throw v0

    .catchall {:try_start_0 .. :try_end_0} :catchall_0
.end method

.method private static cleanup(ILjava/lang/String;I)V
    .locals 6

    const/4 v5, -0x1

    if-ltz p0, :cond_done

    const/4 v0, 0x4

    if-ge p0, v0, :cond_done

    const/4 v2, 0x0

    sget-object v4, Lcom/sec/epdg/M11qW2LTrial;->LOCK:Ljava/lang/Object;

    monitor-enter v4

    :try_start_0
    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->active:[Z

    aget-boolean v1, v0, p0

    if-eqz v1, :cond_unlock

    sget-object v1, Lcom/sec/epdg/M11qW2LTrial;->generation:[I

    aget v1, v1, p0

    if-ne v1, p2, :cond_unlock

    sget-object v1, Lcom/sec/epdg/M11qW2LTrial;->subscriptions:[Lcom/sec/epdg/EpdgSubScription;

    aget-object v2, v1, p0

    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->cid:[I

    aget v5, v0, p0

    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->active:[Z

    const/4 v3, 0x0

    aput-boolean v3, v0, p0

    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->attached:[Z

    aput-boolean v3, v0, p0

    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->deferred:[Z

    aput-boolean v3, v0, p0

    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->shutdownPending:[Z

    aput-boolean v3, v0, p0

    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->cid:[I

    const/4 v3, -0x1

    aput v3, v0, p0

    const/4 v0, 0x0

    aput-object v0, v1, p0

    sget-object v1, Lcom/sec/epdg/M11qW2LTrial;->stateMachines:[Lcom/sec/epdg/IPSecDataConnSM;

    aput-object v0, v1, p0

    :cond_unlock
    monitor-exit v4
    :try_end_0

    if-eqz v2, :cond_done

    invoke-static {p0, v5, p2, p1}, Lcom/sec/epdg/M11qW2LTrial;->logEvent(IIILjava/lang/String;)V

    invoke-virtual {v2}, Lcom/sec/epdg/EpdgSubScription;->notifyQualifiedNetworksChange()V

    :cond_done
    return-void

    :catchall_0
    move-exception v0

    monitor-exit v4

    throw v0

    .catchall {:try_start_0 .. :try_end_0} :catchall_0
.end method

.method private static trigger(Lcom/sec/epdg/EpdgSubScription;IZ)Z
    .locals 7

    const-string v0, "ims"

    invoke-virtual {p0, v0}, Lcom/sec/epdg/EpdgSubScription;->getSMForApnType(Ljava/lang/String;)Lcom/sec/epdg/IPSecDataConnSM;

    move-result-object v5

    if-eqz v5, :cond_unavailable

    invoke-virtual {v5}, Lcom/sec/epdg/IPSecDataConnSM;->getmRilCid()I

    move-result v6

    if-lez v6, :cond_unavailable

    sget-object v3, Lcom/sec/epdg/M11qW2LTrial;->LOCK:Ljava/lang/Object;

    monitor-enter v3

    :try_start_0
    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->active:[Z

    aget-boolean v1, v0, p1

    if-nez v1, :cond_active_locked

    const/4 v1, 0x1

    aput-boolean v1, v0, p1

    sget v2, Lcom/sec/epdg/M11qW2LTrial;->serial:I

    add-int/lit8 v2, v2, 0x1

    sput v2, Lcom/sec/epdg/M11qW2LTrial;->serial:I

    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->generation:[I

    aput v2, v0, p1

    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->shutdownPending:[Z

    aput-boolean p2, v0, p1

    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->subscriptions:[Lcom/sec/epdg/EpdgSubScription;

    aput-object p0, v0, p1

    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->attached:[Z

    const/4 v2, 0x0

    aput-boolean v2, v0, p1

    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->deferred:[Z

    aput-boolean v2, v0, p1

    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->cid:[I

    aput v6, v0, p1

    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->stateMachines:[Lcom/sec/epdg/IPSecDataConnSM;

    aput-object v5, v0, p1

    monitor-exit v3
    :try_end_0

    const-string v0, "trigger:pin-ims-lte"

    invoke-static {p1, v0}, Lcom/sec/epdg/M11qW2LTrial;->logState(ILjava/lang/String;)V

    const-string v0, "ims"

    const/16 v2, 0xd

    invoke-virtual {p0, v0, v2}, Lcom/sec/epdg/EpdgSubScription;->notifyQualifiedNetworksChange(Ljava/lang/String;I)V

    return v1

    :cond_active_locked
    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->subscriptions:[Lcom/sec/epdg/EpdgSubScription;

    aget-object v0, v0, p1

    if-ne v0, p0, :cond_other_subscription

    if-eqz p2, :cond_release_active

    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->shutdownPending:[Z

    const/4 v2, 0x1

    aput-boolean v2, v0, p1

    :cond_release_active
    monitor-exit v3

    :try_end_1
    const-string v0, "trigger:already-active"

    invoke-static {p1, v0}, Lcom/sec/epdg/M11qW2LTrial;->logState(ILjava/lang/String;)V

    const/4 v0, 0x1

    return v0

    :cond_other_subscription
    monitor-exit v3
    :try_end_2

    const/4 v0, 0x0

    return v0

    :cond_unavailable
    const/4 v0, 0x0

    return v0

    :catchall_0
    move-exception v0

    monitor-exit v3

    throw v0

    .catchall {:try_start_0 .. :try_end_0} :catchall_0
    .catchall {:cond_active_locked .. :try_end_1} :catchall_0
    .catchall {:cond_other_subscription .. :try_end_2} :catchall_0
.end method

.method public static onWifiState(Landroid/content/Intent;Landroid/content/Context;Lcom/sec/epdg/EpdgSubScription;II)V
    .locals 3

    const-string v0, "wifi_state"

    const/4 v1, 0x4

    invoke-virtual {p0, v0, v1}, Landroid/content/Intent;->getIntExtra(Ljava/lang/String;I)I

    move-result v0

    if-nez v0, :cond_disabled

    invoke-static {p1, p2, p3, p4}, Lcom/sec/epdg/M11qW2LTrial;->eligible(Landroid/content/Context;Lcom/sec/epdg/EpdgSubScription;II)Z

    move-result v1

    if-eqz v1, :cond_ineligible

    const/4 v1, 0x1

    invoke-static {p2, p3, v1}, Lcom/sec/epdg/M11qW2LTrial;->trigger(Lcom/sec/epdg/EpdgSubScription;IZ)Z

    return-void

    :cond_ineligible
    const-string v1, "wifi-disabling:ineligible"

    invoke-static {p3, v1}, Lcom/sec/epdg/M11qW2LTrial;->logState(ILjava/lang/String;)V

    return-void

    :cond_disabled
    const/4 v1, 0x1

    if-eq v0, v1, :cond_terminal_wifi_state

    const/4 v1, 0x3

    if-ne v0, v1, :cond_done

    :cond_terminal_wifi_state
    invoke-static {p2, p3, v0}, Lcom/sec/epdg/M11qW2LTrial;->onTerminalWifiState(Lcom/sec/epdg/EpdgSubScription;II)V

    :cond_done
    return-void
.end method

.method private static abort(Lcom/sec/epdg/EpdgSubScription;ILjava/lang/String;)V
    .locals 7

    if-ltz p1, :cond_done

    const/4 v0, 0x4

    if-ge p1, v0, :cond_done

    const/4 v1, 0x0

    const/4 v2, -0x1

    const/4 v5, 0x0

    sget-object v6, Lcom/sec/epdg/M11qW2LTrial;->LOCK:Ljava/lang/Object;

    monitor-enter v6

    :try_start_0
    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->subscriptions:[Lcom/sec/epdg/EpdgSubScription;

    aget-object v0, v0, p1

    if-ne v0, p0, :cond_unlock

    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->generation:[I

    aget v5, v0, p1

    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->attached:[Z

    aget-boolean v1, v0, p1

    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->cid:[I

    aget v2, v0, p1

    :cond_unlock
    monitor-exit v6
    :try_end_0

    if-eqz v5, :cond_done

    if-eqz v1, :cond_cleanup

    invoke-static {p1}, Lcom/sec/epdg/apassist/IwlanService/TelephonyAdapter;->getInstance(I)Lcom/sec/epdg/apassist/IwlanService/TelephonyAdapter;

    move-result-object v0

    sget v3, Lcom/sec/epdg/apassist/IwlanService/TelephonyAdapter;->HANDOVER_FAIL:I

    const/4 v4, 0x0

    invoke-virtual {v0, p1, v2, v3, v4}, Lcom/sec/epdg/apassist/IwlanService/TelephonyAdapter;->notifyConnectionStateChanged(IIILandroid/os/Message;)V

    :cond_cleanup
    invoke-static {p1, p2, v5}, Lcom/sec/epdg/M11qW2LTrial;->cleanup(ILjava/lang/String;I)V

    :cond_done
    return-void

    :catchall_0
    move-exception v0

    monitor-exit v6

    throw v0

    .catchall {:try_start_0 .. :try_end_0} :catchall_0
.end method

.method private static onTerminalWifiState(Lcom/sec/epdg/EpdgSubScription;II)V
    .locals 5

    if-ltz p1, :cond_done

    const/4 v0, 0x4

    if-ge p1, v0, :cond_done

    const/4 v1, 0x0

    const/4 v2, 0x0

    const/4 v3, 0x0

    sget-object v4, Lcom/sec/epdg/M11qW2LTrial;->LOCK:Ljava/lang/Object;

    monitor-enter v4

    :try_start_0
    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->subscriptions:[Lcom/sec/epdg/EpdgSubScription;

    aget-object v0, v0, p1

    if-ne v0, p0, :cond_unlock

    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->generation:[I

    aget v3, v0, p1

    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->shutdownPending:[Z

    aget-boolean v2, v0, p1

    const/4 v1, 0x1

    if-ne p2, v1, :cond_keep_shutdown

    const/4 v1, 0x0

    aput-boolean v1, v0, p1

    :cond_keep_shutdown
    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->attached:[Z

    aget-boolean v1, v0, p1

    :cond_unlock
    monitor-exit v4
    :try_end_0

    if-eqz v3, :cond_done

    const/4 v0, 0x3

    if-ne p2, v0, :cond_disabled

    if-eqz v2, :cond_done

    const-string v0, "wifi-enabled-cancel"

    invoke-static {p0, p1, v0}, Lcom/sec/epdg/M11qW2LTrial;->abort(Lcom/sec/epdg/EpdgSubScription;ILjava/lang/String;)V

    return-void

    :cond_disabled
    if-nez v1, :cond_retain

    const-string v0, "wifi-disabled-pending"

    invoke-static {p1, v0, v3}, Lcom/sec/epdg/M11qW2LTrial;->cleanup(ILjava/lang/String;I)V

    return-void

    :cond_retain
    const-string v0, "wifi-disabled:retain-transaction"

    invoke-static {p1, v0}, Lcom/sec/epdg/M11qW2LTrial;->logState(ILjava/lang/String;)V

    :cond_done
    return-void

    :catchall_0
    move-exception v0

    monitor-exit v4

    throw v0

    .catchall {:try_start_0 .. :try_end_0} :catchall_0
.end method

.method public static isPinned(Lcom/sec/epdg/EpdgSubScription;I)Z
    .locals 5

    if-ltz p1, :cond_false

    const/4 v0, 0x4

    if-ge p1, v0, :cond_false

    const/4 v1, 0x0

    sget-object v4, Lcom/sec/epdg/M11qW2LTrial;->LOCK:Ljava/lang/Object;

    monitor-enter v4

    :try_start_0
    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->active:[Z

    aget-boolean v1, v0, p1

    if-eqz v1, :cond_unlock

    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->subscriptions:[Lcom/sec/epdg/EpdgSubScription;

    aget-object v0, v0, p1

    if-ne v0, p0, :cond_not_same

    goto :cond_unlock

    :cond_not_same
    const/4 v1, 0x0

    :cond_unlock
    monitor-exit v4
    :try_end_0

    return v1

    :cond_false
    const/4 v0, 0x0

    return v0

    :catchall_0
    move-exception v0

    monitor-exit v4

    throw v0

    .catchall {:try_start_0 .. :try_end_0} :catchall_0
.end method

.method public static pinResult(Lcom/sec/epdg/EpdgSubScription;ILjava/util/List;)V
    .locals 2

    invoke-static {p0, p1}, Lcom/sec/epdg/M11qW2LTrial;->isPinned(Lcom/sec/epdg/EpdgSubScription;I)Z

    move-result v0

    if-eqz v0, :cond_done

    sget-object v0, Lcom/sec/epdg/data/Constants/MapconConstants$MapconApnType;->APN_TYPE_IMS:Lcom/sec/epdg/data/Constants/MapconConstants$MapconApnType;

    invoke-virtual {v0}, Lcom/sec/epdg/data/Constants/MapconConstants$MapconApnType;->getIntValue()I

    move-result v0

    sget-object v1, Lcom/sec/epdg/data/Constants/MapconConstants$MapconMode;->LTE:Lcom/sec/epdg/data/Constants/MapconConstants$MapconMode;

    invoke-virtual {v1}, Lcom/sec/epdg/data/Constants/MapconConstants$MapconMode;->toString()Ljava/lang/String;

    move-result-object v1

    invoke-static {v1}, Lcom/sec/epdg/data/Constants/MapconConstants$MapconMode;->getIntValue(Ljava/lang/String;)I

    move-result v1

    invoke-static {v1}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;

    move-result-object v1

    invoke-interface {p2, v0, v1}, Ljava/util/List;->set(ILjava/lang/Object;)Ljava/lang/Object;

    :cond_done
    return-void
.end method

.method public static requestWeak(Lcom/sec/epdg/EpdgSubScription;I)Z
    .locals 3

    invoke-virtual {p0}, Lcom/sec/epdg/EpdgSubScription;->getEpdgServiceContext()Landroid/content/Context;

    move-result-object v0

    invoke-static {p1}, Lcom/sec/epdg/EpdgUtils;->getInstance(I)Lcom/sec/epdg/EpdgUtils;

    move-result-object v1

    invoke-virtual {v1, p1}, Lcom/sec/epdg/EpdgUtils;->getSubId(I)I

    move-result v1

    invoke-static {v0, p0, p1, v1}, Lcom/sec/epdg/M11qW2LTrial;->eligible(Landroid/content/Context;Lcom/sec/epdg/EpdgSubScription;II)Z

    move-result v2

    if-eqz v2, :cond_fail

    const-string v2, "weak-rssi:ap-assist"

    invoke-static {p1, v2}, Lcom/sec/epdg/M11qW2LTrial;->logState(ILjava/lang/String;)V

    const/4 v2, 0x0

    invoke-static {p0, p1, v2}, Lcom/sec/epdg/M11qW2LTrial;->trigger(Lcom/sec/epdg/EpdgSubScription;IZ)Z

    move-result v0

    return v0

    :cond_fail
    const/4 v0, 0x0

    return v0
.end method

.method public static onW2MEnter(Lcom/sec/epdg/IPSecDataConnSM;)V
    .locals 6

    const/4 v4, 0x0

    invoke-static {p0}, Lcom/sec/epdg/IPSecDataConnSM;->access$700(Lcom/sec/epdg/IPSecDataConnSM;)I

    move-result v0

    if-ltz v0, :cond_done

    const/4 v1, 0x4

    if-ge v0, v1, :cond_done

    invoke-static {p0}, Lcom/sec/epdg/IPSecDataConnSM;->access$1000(Lcom/sec/epdg/IPSecDataConnSM;)Lcom/sec/epdg/EpdgSubScription;

    move-result-object v2

    invoke-static {v2, v0}, Lcom/sec/epdg/M11qW2LTrial;->stillEligible(Lcom/sec/epdg/EpdgSubScription;I)Z

    move-result v1

    if-eqz v1, :cond_done

    invoke-virtual {p0}, Lcom/sec/epdg/IPSecDataConnSM;->getmRilCid()I

    move-result v1

    if-lez v1, :cond_done

    invoke-virtual {p0}, Lcom/sec/epdg/IPSecDataConnSM;->getApnType()Ljava/lang/String;

    move-result-object v1

    const-string v3, "ims"

    invoke-virtual {v3, v1}, Ljava/lang/String;->equalsIgnoreCase(Ljava/lang/String;)Z

    move-result v1

    if-eqz v1, :cond_done

    sget-object v5, Lcom/sec/epdg/M11qW2LTrial;->LOCK:Ljava/lang/Object;

    monitor-enter v5

    :try_start_0

    sget-object v1, Lcom/sec/epdg/M11qW2LTrial;->active:[Z

    aget-boolean v1, v1, v0

    if-eqz v1, :cond_unlock

    sget-object v1, Lcom/sec/epdg/M11qW2LTrial;->subscriptions:[Lcom/sec/epdg/EpdgSubScription;

    aget-object v1, v1, v0

    if-ne v1, v2, :cond_unlock

    sget-object v1, Lcom/sec/epdg/M11qW2LTrial;->stateMachines:[Lcom/sec/epdg/IPSecDataConnSM;

    aget-object v2, v1, v0

    if-ne v2, p0, :cond_unlock

    sget-object v1, Lcom/sec/epdg/M11qW2LTrial;->cid:[I

    aget v1, v1, v0

    invoke-virtual {p0}, Lcom/sec/epdg/IPSecDataConnSM;->getmRilCid()I

    move-result v2

    if-ne v1, v2, :cond_unlock

    sget-object v1, Lcom/sec/epdg/M11qW2LTrial;->attached:[Z

    aget-boolean v2, v1, v0

    if-nez v2, :cond_unlock

    :cond_attach
    const/4 v2, 0x1

    aput-boolean v2, v1, v0

    invoke-virtual {p0}, Lcom/sec/epdg/IPSecDataConnSM;->getmRilCid()I

    move-result v1

    sget-object v3, Lcom/sec/epdg/M11qW2LTrial;->cid:[I

    aput v1, v3, v0

    const/4 v4, 0x1

    :cond_unlock
    monitor-exit v5
    :try_end_0

    if-eqz v4, :cond_done

    const-string v1, "w2m-enter:attached"

    invoke-static {v0, v1}, Lcom/sec/epdg/M11qW2LTrial;->logState(ILjava/lang/String;)V

    :cond_done
    return-void

    :catchall_0
    move-exception v0

    monitor-exit v5

    throw v0

    .catchall {:try_start_0 .. :try_end_0} :catchall_0
.end method

.method public static deferDecision(Lcom/sec/epdg/IPSecDataConnSM;Landroid/os/Message;)I
    .locals 7

    iget v0, p1, Landroid/os/Message;->what:I

    const/4 v1, 0x7

    if-ne v0, v1, :cond_no

    invoke-static {p0}, Lcom/sec/epdg/IPSecDataConnSM;->access$700(Lcom/sec/epdg/IPSecDataConnSM;)I

    move-result v0

    if-ltz v0, :cond_no

    const/4 v1, 0x4

    if-ge v0, v1, :cond_no

    invoke-static {p0}, Lcom/sec/epdg/IPSecDataConnSM;->access$1000(Lcom/sec/epdg/IPSecDataConnSM;)Lcom/sec/epdg/EpdgSubScription;

    move-result-object v1

    invoke-static {v1, v0}, Lcom/sec/epdg/M11qW2LTrial;->stillEligible(Lcom/sec/epdg/EpdgSubScription;I)Z

    move-result v2

    if-eqz v2, :cond_no

    sget-object v6, Lcom/sec/epdg/M11qW2LTrial;->LOCK:Ljava/lang/Object;

    monitor-enter v6

    :try_start_0
    sget-object v2, Lcom/sec/epdg/M11qW2LTrial;->active:[Z

    aget-boolean v2, v2, v0

    if-eqz v2, :cond_unlock_no

    sget-object v2, Lcom/sec/epdg/M11qW2LTrial;->attached:[Z

    aget-boolean v2, v2, v0

    if-eqz v2, :cond_unlock_no

    sget-object v2, Lcom/sec/epdg/M11qW2LTrial;->subscriptions:[Lcom/sec/epdg/EpdgSubScription;

    aget-object v2, v2, v0

    if-ne v2, v1, :cond_unlock_no

    sget-object v2, Lcom/sec/epdg/M11qW2LTrial;->stateMachines:[Lcom/sec/epdg/IPSecDataConnSM;

    aget-object v2, v2, v0

    if-ne v2, p0, :cond_unlock_no

    sget-object v2, Lcom/sec/epdg/M11qW2LTrial;->cid:[I

    aget v2, v2, v0

    iget v3, p1, Landroid/os/Message;->arg1:I

    if-ne v2, v3, :cond_unlock_no

    sget-object v2, Lcom/sec/epdg/M11qW2LTrial;->deferred:[Z

    aget-boolean v3, v2, v0

    if-eqz v3, :cond_first

    monitor-exit v6
    :try_end_0

    const-string v4, "msg7:duplicate-consumed"

    invoke-static {v0, v4}, Lcom/sec/epdg/M11qW2LTrial;->logState(ILjava/lang/String;)V

    const/4 v0, 0x2

    return v0

    :cond_first
    const/4 v3, 0x1

    aput-boolean v3, v2, v0

    monitor-exit v6
    :try_end_1

    const-string v4, "msg7:deferred-once"

    invoke-static {v0, v4}, Lcom/sec/epdg/M11qW2LTrial;->logState(ILjava/lang/String;)V

    return v3

    :cond_unlock_no
    monitor-exit v6
    :try_end_2

    :cond_no
    const/4 v0, 0x0

    return v0

    :catchall_0
    move-exception v0

    monitor-exit v6

    throw v0

    .catchall {:try_start_0 .. :try_end_0} :catchall_0
    .catchall {:cond_first .. :try_end_1} :catchall_0
    .catchall {:cond_unlock_no .. :try_end_2} :catchall_0
.end method

.method public static onW2MExit(Lcom/sec/epdg/IPSecDataConnSM;)V
    .locals 6

    const/4 v4, 0x0

    invoke-static {p0}, Lcom/sec/epdg/IPSecDataConnSM;->access$700(Lcom/sec/epdg/IPSecDataConnSM;)I

    move-result v0

    if-ltz v0, :cond_done

    const/4 v1, 0x4

    if-ge v0, v1, :cond_done

    invoke-virtual {p0}, Lcom/sec/epdg/IPSecDataConnSM;->getApnType()Ljava/lang/String;

    move-result-object v1

    const-string v2, "ims"

    invoke-virtual {v2, v1}, Ljava/lang/String;->equalsIgnoreCase(Ljava/lang/String;)Z

    move-result v1

    if-eqz v1, :cond_done

    sget-object v5, Lcom/sec/epdg/M11qW2LTrial;->LOCK:Ljava/lang/Object;

    monitor-enter v5

    :try_start_0
    sget-object v1, Lcom/sec/epdg/M11qW2LTrial;->attached:[Z

    aget-boolean v1, v1, v0

    if-eqz v1, :cond_unlock

    sget-object v1, Lcom/sec/epdg/M11qW2LTrial;->stateMachines:[Lcom/sec/epdg/IPSecDataConnSM;

    aget-object v1, v1, v0

    if-ne v1, p0, :cond_unlock

    sget-object v1, Lcom/sec/epdg/M11qW2LTrial;->cid:[I

    aget v1, v1, v0

    invoke-virtual {p0}, Lcom/sec/epdg/IPSecDataConnSM;->getmRilCid()I

    move-result v2

    if-ne v1, v2, :cond_unlock

    sget-object v1, Lcom/sec/epdg/M11qW2LTrial;->generation:[I

    aget v4, v1, v0

    const/4 v3, 0x1

    goto :goto_unlock

    :cond_unlock
    const/4 v3, 0x0

    :goto_unlock
    monitor-exit v5
    :try_end_0

    if-eqz v3, :cond_done

    const-string v1, "state-exit"

    invoke-static {v0, v1, v4}, Lcom/sec/epdg/M11qW2LTrial;->cleanup(ILjava/lang/String;I)V

    :cond_done
    return-void

    :catchall_0
    move-exception v0

    monitor-exit v5

    throw v0

    .catchall {:try_start_0 .. :try_end_0} :catchall_0
.end method

.method public static onFrameworkCancel(II)V
    .locals 5

    const/4 v2, 0x0

    if-ltz p0, :cond_done

    const/4 v0, 0x4

    if-ge p0, v0, :cond_done

    sget-object v4, Lcom/sec/epdg/M11qW2LTrial;->LOCK:Ljava/lang/Object;

    monitor-enter v4

    :try_start_0
    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->active:[Z

    aget-boolean v0, v0, p0

    if-eqz v0, :cond_no

    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->cid:[I

    aget v0, v0, p0

    if-ne v0, p1, :cond_no

    sget-object v0, Lcom/sec/epdg/M11qW2LTrial;->generation:[I

    aget v2, v0, p0

    :cond_yes
    const/4 v1, 0x1

    goto :goto_unlock

    :cond_no
    const/4 v1, 0x0

    :goto_unlock
    monitor-exit v4
    :try_end_0

    if-eqz v1, :cond_done

    const-string v0, "framework-cancel"

    invoke-static {p0, v0, v2}, Lcom/sec/epdg/M11qW2LTrial;->cleanup(ILjava/lang/String;I)V

    :cond_done
    return-void

    :catchall_0
    move-exception v0

    monitor-exit v4

    throw v0

    .catchall {:try_start_0 .. :try_end_0} :catchall_0
.end method

.method public static onCallIdle(Lcom/sec/epdg/EpdgSubScription;I)V
    .locals 2

    if-ltz p1, :cond_done

    const/4 v0, 0x4

    if-ge p1, v0, :cond_done

    const-string v0, "call-idle"

    invoke-static {p0, p1, v0}, Lcom/sec/epdg/M11qW2LTrial;->abort(Lcom/sec/epdg/EpdgSubScription;ILjava/lang/String;)V

    :cond_done
    return-void
.end method
