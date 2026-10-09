package android.telephony.data;

public final class DataProfile {
    private final ApnSetting apn;
    public DataProfile(ApnSetting apn) { this.apn = apn; }
    public ApnSetting getApnSetting() { return apn; }
}
