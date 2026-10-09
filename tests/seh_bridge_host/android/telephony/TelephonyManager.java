package android.telephony;

import java.util.HashMap;
import java.util.Map;

public final class TelephonyManager {
    public static final int NETWORK_TYPE_LTE = 13;
    private final Map<Integer, String> operators;
    private final int subId;
    public TelephonyManager() { this(new HashMap<>(), -1); }
    private TelephonyManager(Map<Integer, String> operators, int subId) {
        this.operators = operators;
        this.subId = subId;
    }
    public TelephonyManager createForSubscriptionId(int value) {
        return new TelephonyManager(operators, value);
    }
    public String getSimOperator() { return operators.getOrDefault(subId, ""); }
    public void setSimOperator(int value, String operator) { operators.put(value, operator); }
}
