package android.telephony.data;

public final class ApnSetting {
    public static final int TYPE_DEFAULT = 1;
    public static final int TYPE_IMS = 64;
    private final String apn, user, password;
    private final int types, protocol, roamingProtocol, authType;
    private final boolean enabled, lte;
    public ApnSetting(String apn, int types, boolean enabled, boolean lte, int protocol,
            int roamingProtocol, String user, String password, int authType) {
        this.apn = apn;
        this.types = types;
        this.enabled = enabled;
        this.lte = lte;
        this.protocol = protocol;
        this.roamingProtocol = roamingProtocol;
        this.user = user;
        this.password = password;
        this.authType = authType;
    }
    public boolean canHandleType(int type) { return (types & type) != 0; }
    public int getApnTypeBitmask() { return types; }
    public boolean isEnabled() { return enabled; }
    public boolean canSupportNetworkType(int networkType) { return lte; }
    public String getApnName() { return apn; }
    public int getProtocol() { return protocol; }
    public int getRoamingProtocol() { return roamingProtocol; }
    public String getUser() { return user; }
    public String getPassword() { return password; }
    public int getAuthType() { return authType; }
    public static String getProtocolStringFromInt(int protocol) {
        if (protocol == 0) return "IP";
        if (protocol == 1) return "IPV6";
        if (protocol == 2) return "IPV4V6";
        return "UNKNOWN";
    }
}
