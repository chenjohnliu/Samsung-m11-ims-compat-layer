package android.telephony;

public final class SubscriptionInfo {
    private final int subscriptionId;
    private final int slot;
    public SubscriptionInfo(int subscriptionId, int slot) {
        this.subscriptionId = subscriptionId;
        this.slot = slot;
    }
    public int getSubscriptionId() { return subscriptionId; }
    public int getSimSlotIndex() { return slot; }
}
