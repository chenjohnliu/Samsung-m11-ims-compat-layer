package android.telephony;

import android.content.Context;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class SubscriptionManager {
    private static final Map<Integer, Integer> PHONES = new HashMap<>();
    private List<SubscriptionInfo> active = Collections.emptyList();
    public static SubscriptionManager from(Context context) {
        return context.getSystemService(SubscriptionManager.class);
    }
    public List<SubscriptionInfo> getActiveSubscriptionInfoList() {
        return new ArrayList<>(active);
    }
    public void setActive(SubscriptionInfo... info) {
        active = new ArrayList<>();
        Collections.addAll(active, info);
        PHONES.clear();
        for (SubscriptionInfo value : info) {
            PHONES.put(value.getSubscriptionId(), value.getSimSlotIndex());
        }
    }
    public static int getPhoneId(int subId) { return PHONES.getOrDefault(subId, -1); }
    public static boolean isValidSubscriptionId(int subId) { return subId >= 0; }
}
